"""
FILE: src/interfaces/mcp_interface.py
ROLE: MCP server (read-only in T2.3). Agent-facing surface.
WHAT IT DOES: JSON-RPC 2.0 over stdio. Exposes registered tools and
              projections. Tool calls become envelopes routed through
              the spine (no bypass of the gate or event log).

T2.3 SCOPE:
- initialize
- tools/list  → from tool_registry_manager
- tools/call  → dispatches a tool_invoked envelope via Router
- resources/list  → projection://<name> URIs
- resources/read  → reads a projection's rows

The handler class (MCPHandler) is testable without stdio. The serve_stdio
function wraps it in a newline-JSON loop on sys.stdin/sys.stdout.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

from src.core.envelope import SidecarEnvelope
from src.lib.common import safe_json_dumps
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.core.state import SidecarState


log = get_logger("interfaces.mcp")


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "scaffold-sidecar"
SERVER_VERSION = "0.1.0"


class MCPHandler:
    """Stateless dispatcher for JSON-RPC 2.0 MCP messages."""

    def __init__(self, state: "SidecarState"):
        self._state = state

    # ===== entrypoint ==================================================

    def handle_message(self, message: dict) -> dict | None:
        """Return a JSON-RPC response dict, or None if message is a notification."""
        method = message.get("method")
        params = message.get("params") or {}
        msg_id = message.get("id")
        is_notification = msg_id is None

        try:
            result = self._dispatch(method, params)
        except _MCPError as e:
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": e.code, "message": e.message, "data": e.data}}
        except Exception as e:
            log.exception("MCP unexpected error in %s", method)
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32603, "message": f"internal: {type(e).__name__}: {e}"}}

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _dispatch(self, method: str, params: dict) -> dict:
        if method == "initialize":
            return self._handle_initialize(params)
        if method == "initialized" or method == "notifications/initialized":
            return {}
        if method == "tools/list":
            return self._handle_tools_list(params)
        if method == "tools/call":
            return self._handle_tools_call(params)
        if method == "resources/list":
            return self._handle_resources_list(params)
        if method == "resources/read":
            return self._handle_resources_read(params)
        if method == "ping":
            return {}
        raise _MCPError(-32601, f"method not found: {method}")

    # ===== method handlers =============================================

    def _handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                           "sidecar_id": self._state.sidecar_id},
            "instructions": (
                "Read-only sidecar surface. Tools require contract "
                "acknowledgment by the calling actor (default: agent:mcp). "
                "Read the toolbox_manifest before invoking tools."
            ),
        }

    def _handle_tools_list(self, params: dict) -> dict:
        tools = []
        for t in self._state.tool_registry_manager.list_tools():
            tools.append({
                "name": t.mcp_name,
                "description": t.summary,
                "inputSchema": t.input_schema,
                "_meta": {
                    "tool_name": t.tool_name,
                    "category": t.category,
                    "required_authority": t.required_authority,
                    "version": t.version,
                },
            })
        return {"tools": tools}

    def _handle_tools_call(self, params: dict) -> dict:
        mcp_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not mcp_name:
            raise _MCPError(-32602, "tools/call requires 'name'")

        tool = self._state.tool_registry_manager.by_mcp_name(mcp_name)
        if tool is None:
            raise _MCPError(-32602, f"unknown tool: {mcp_name}")

        actor_id = self._actor_for_session(params)
        payload_ref = self._state.blob_store.put_json(
            {"tool_name": tool.tool_name, "arguments": arguments}
        )
        envelope = SidecarEnvelope.new(
            object_type="tool_invocation",
            actor_id=actor_id,
            operation_intent="tool_invoked",
            payload_ref=payload_ref,
        )
        result_env = self._state.router.dispatch(envelope)

        is_error = result_env.status not in ("accepted", "completed")
        result_data: dict | None = None
        if result_env.payload_ref:
            try:
                result_data = self._state.blob_store.get_json(result_env.payload_ref)
            except Exception as e:
                log.error("could not read result blob: %s", e)

        if is_error:
            err_text = (result_data or {}).get("error") or f"tool call status: {result_env.status}"
            return {
                "isError": True,
                "content": [{"type": "text", "text": str(err_text)}],
            }

        text_summary = safe_json_dumps(
            (result_data or {}).get("result", result_data),
            indent=2,
        )
        return {
            "isError": False,
            "content": [{"type": "text", "text": text_summary}],
            "_meta": {
                "tool_name": tool.tool_name,
                "event_id": result_env.event_id,
                "status": result_env.status,
            },
        }

    def _handle_resources_list(self, params: dict) -> dict:
        resources = []
        for name in self._state.projections.list():
            resources.append({
                "uri": f"projection://{name}",
                "name": name,
                "description": f"Projection: {name}",
                "mimeType": "application/json",
            })
        return {"resources": resources}

    def _handle_resources_read(self, params: dict) -> dict:
        uri = params.get("uri", "")
        if not uri.startswith("projection://"):
            raise _MCPError(-32602, f"unsupported resource uri scheme: {uri!r}")
        name = uri[len("projection://"):]
        if name not in self._state.projections.list():
            raise _MCPError(-32602, f"unknown projection: {name}")
        result = self._state.projections.read(name)
        body = {
            "name": result.name,
            "last_refreshed_at": result.last_refreshed_at,
            "row_count": len(result.rows),
            "rows": result.rows,
        }
        return {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": safe_json_dumps(body),
            }],
        }

    # ===== helpers =====================================================

    def _actor_for_session(self, params: dict) -> str:
        """Resolve the actor id for this MCP session. T2.3: default to agent:mcp."""
        meta = params.get("_meta") or {}
        client_name = meta.get("client_name") or "default"
        return f"agent:mcp:{client_name}"


class _MCPError(Exception):
    def __init__(self, code: int, message: str, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# ===========================================================================
# stdio loop
# ===========================================================================


def serve_stdio(state: "SidecarState") -> int:
    """Newline-delimited JSON-RPC 2.0 over stdin/stdout."""
    handler = MCPHandler(state)
    log.info("MCP stdio server starting; sidecar_id=%s", state.sidecar_id)
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as e:
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": f"parse error: {e}"},
                }) + "\n")
                sys.stdout.flush()
                continue
            response = handler.handle_message(message)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
    except KeyboardInterrupt:
        log.info("MCP stdio server stopped by signal")
    log.info("MCP stdio server exiting")
    return 0
