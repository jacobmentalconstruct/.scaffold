"""
FILE: src/managers/tool_registry_manager.py
ROLE: Owner of tool_registry + tool_invocations. Discovers tools under
      src/tools/ on boot, validates FILE_METADATA, registers them.
      Handles tool_invoked envelopes by calling the tool's run() function
      and recording the invocation.
WHAT IT DOES (T2.3): discover, register, invoke, query. Tools follow the
                     Standard Tool Contract (FILE_METADATA + run).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, TYPE_CHECKING

from src.lib.common import (
    authority_at_least,
    gen_id,
    now_iso,
    safe_json_dumps,
    sha256_hex,
)
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.blob_store import BlobStore
    from src.components.sqlite_store import Store
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState


log = get_logger("managers.tool_registry")


REQUIRED_METADATA_FIELDS = (
    "tool_name", "version", "entrypoint", "category",
    "summary", "mcp_name", "required_authority", "input_schema",
)


@dataclass(frozen=True)
class RegisteredTool:
    tool_name: str
    version: str
    entrypoint: str
    category: str
    summary: str
    mcp_name: str
    required_authority: str
    input_schema: dict
    source_hash: str
    registered_at: str
    module: ModuleType | None = None  # in-memory module reference
    run_fn: Callable | None = None    # in-memory run function


class ToolValidationError(ValueError):
    pass


class ToolRegistryManager:
    def __init__(self, store: "Store", blob_store: "BlobStore", tools_dir: Path):
        self._store = store
        self._blob = blob_store
        self._tools_dir = Path(tools_dir)
        self._in_memory: dict[str, RegisteredTool] = {}

    # ===== discovery ===================================================

    def discover_all(self) -> list[RegisteredTool]:
        """Walk src/tools/, import each *.py (excluding __init__ and _*),
        validate FILE_METADATA, register in DB + in-memory."""
        discovered: list[RegisteredTool] = []
        if not self._tools_dir.is_dir():
            log.warning("tools dir not found: %s", self._tools_dir)
            return discovered
        for path in sorted(self._tools_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                tool = self._import_and_register(path)
                if tool is not None:
                    discovered.append(tool)
            except Exception as e:
                log.error("failed to register tool %s: %s", path.name, e)
        log.info("discovered %d tool(s) in %s", len(discovered), self._tools_dir)
        return discovered

    def _import_and_register(self, path: Path) -> RegisteredTool | None:
        module_name = f"src.tools.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ToolValidationError(f"could not load spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        metadata = getattr(module, "FILE_METADATA", None)
        run_fn = getattr(module, "run", None)
        if not isinstance(metadata, dict):
            raise ToolValidationError(f"{path.name}: missing FILE_METADATA dict")
        if not callable(run_fn):
            raise ToolValidationError(f"{path.name}: missing run() function")
        missing = [k for k in REQUIRED_METADATA_FIELDS if k not in metadata]
        if missing:
            raise ToolValidationError(f"{path.name}: missing FILE_METADATA fields: {missing}")

        source_bytes = path.read_bytes()
        source_hash = sha256_hex(source_bytes)
        now = now_iso()

        existing = self._store.query_one(
            "SELECT source_hash FROM tool_registry WHERE tool_name = ?;",
            (metadata["tool_name"],),
        )
        self._store.execute(
            """
            INSERT INTO tool_registry(
                tool_name, version, entrypoint, category, summary,
                mcp_name, required_authority, input_schema_json,
                source_hash, registered_at, last_invoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(tool_name) DO UPDATE SET
                version=excluded.version,
                entrypoint=excluded.entrypoint,
                category=excluded.category,
                summary=excluded.summary,
                mcp_name=excluded.mcp_name,
                required_authority=excluded.required_authority,
                input_schema_json=excluded.input_schema_json,
                source_hash=excluded.source_hash;
            """,
            (
                metadata["tool_name"], metadata["version"], metadata["entrypoint"],
                metadata["category"], metadata.get("summary", ""),
                metadata["mcp_name"], metadata["required_authority"],
                safe_json_dumps(metadata["input_schema"]),
                source_hash, now,
            ),
        )

        registered = RegisteredTool(
            tool_name=metadata["tool_name"],
            version=metadata["version"],
            entrypoint=metadata["entrypoint"],
            category=metadata["category"],
            summary=metadata.get("summary", ""),
            mcp_name=metadata["mcp_name"],
            required_authority=metadata["required_authority"],
            input_schema=dict(metadata["input_schema"]),
            source_hash=source_hash,
            registered_at=now,
            module=module,
            run_fn=run_fn,
        )
        self._in_memory[metadata["tool_name"]] = registered
        if existing is None or existing["source_hash"] != source_hash:
            log.info("tool registered: %s (%s)", metadata["tool_name"], metadata["category"])
        return registered

    # ===== invocation handler ==========================================

    def handle_invoke(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        """Handler for tool_invoked.

        Payload: {tool_name, arguments}.
        Checks the actor has the tool's required_authority. Calls the tool's
        run() with (arguments, state). Records the invocation. Returns
        envelope with response payload.
        """
        request = self._blob.get_json(envelope.payload_ref) if envelope.payload_ref else {}
        tool_name = request.get("tool_name")
        arguments = request.get("arguments") or {}
        if not tool_name:
            raise ValueError("tool_invoked requires tool_name in payload")

        tool = self._in_memory.get(tool_name)
        if tool is None:
            raise KeyError(f"unknown tool: {tool_name}")

        # Authority check.
        actor_auth = state.contract_authority._actor_authority(envelope.actor_id)
        if not authority_at_least(actor_auth, tool.required_authority):
            raise PermissionError(
                f"actor {envelope.actor_id!r} has authority {actor_auth!r} "
                f"but tool {tool_name!r} requires {tool.required_authority!r}"
            )

        invocation_id = gen_id("inv_")
        started_at = now_iso()
        args_ref = self._blob.put_json({"tool_name": tool_name, "arguments": arguments})
        self._store.execute(
            """
            INSERT INTO tool_invocations(
                invocation_id, tool_name, envelope_id, event_id,
                actor_id, arguments_ref, result_ref, status, started_at,
                finished_at, error_summary
            ) VALUES (?, ?, ?, NULL, ?, ?, NULL, 'running', ?, NULL, NULL);
            """,
            (invocation_id, tool_name, envelope.object_id, envelope.actor_id,
             args_ref, started_at),
        )

        try:
            result = tool.run_fn(arguments, state)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            finished_at = now_iso()
            self._store.execute(
                "UPDATE tool_invocations SET status='failed', finished_at=?, error_summary=? "
                "WHERE invocation_id = ?;",
                (finished_at, error, invocation_id),
            )
            log.error("tool %s failed: %s", tool_name, error)
            error_blob = self._blob.put_json({"error": error, "tool_name": tool_name})
            return envelope.with_status("failed").with_payload_ref(error_blob)

        finished_at = now_iso()
        result_ref = self._blob.put_json(result)
        self._store.execute(
            "UPDATE tool_invocations SET status='completed', finished_at=?, result_ref=? "
            "WHERE invocation_id = ?;",
            (finished_at, result_ref, invocation_id),
        )
        self._store.execute(
            "UPDATE tool_registry SET last_invoked_at = ? WHERE tool_name = ?;",
            (finished_at, tool_name),
        )
        log.info("tool %s ok inv_id=%s", tool_name, invocation_id)
        return envelope.with_status("completed").with_payload_ref(result_ref)

    def finalize_invocation_event_id(self, sealed_envelope: "SidecarEnvelope") -> None:
        """Bind tool_invocations.event_id from the sealed envelope."""
        self._store.execute(
            "UPDATE tool_invocations SET event_id = ? "
            "WHERE envelope_id = ? AND event_id IS NULL;",
            (sealed_envelope.event_id, sealed_envelope.object_id),
        )

    # ===== reads =======================================================

    def list_tools(self) -> list[RegisteredTool]:
        return list(self._in_memory.values())

    def get(self, tool_name: str) -> RegisteredTool | None:
        return self._in_memory.get(tool_name)

    def by_mcp_name(self, mcp_name: str) -> RegisteredTool | None:
        for t in self._in_memory.values():
            if t.mcp_name == mcp_name:
                return t
        return None

    def count(self) -> int:
        return len(self._in_memory)

    def stats(self) -> dict:
        by_category: dict[str, int] = {}
        for t in self._in_memory.values():
            by_category[t.category] = by_category.get(t.category, 0) + 1
        return {"tool_count": len(self._in_memory), "by_category": by_category}
