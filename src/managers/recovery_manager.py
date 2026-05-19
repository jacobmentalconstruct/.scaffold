"""
FILE: src/managers/recovery_manager.py
ROLE: Normalized recovery classification + operator hint derivation.
WHAT IT DOES: Maps runtime/tool/approval failures into a finite taxonomy
              used consistently by runtime trace persistence, projections,
              CLI inspection, UI display, and smoke assertions.
"""

from __future__ import annotations

from dataclasses import dataclass


RECOVERY_CLASSES = (
    "model_transport_error",
    "malformed_tool_call",
    "schema_error",
    "tool_failure",
    "approval_stop",
    "approval_denied",
    "max_round_exhaustion",
    "contract_denial",
    "validation_failure",
    "operator_stop",
    "runtime_exception",
    "unknown_failure",
)


@dataclass(frozen=True)
class RecoveryInfo:
    recovery_class: str
    severity: str
    retryable: bool
    operator_hint: str
    suggested_next_action: str


_RECOVERY_MAP: dict[str, RecoveryInfo] = {
    "model_transport_error": RecoveryInfo(
        "model_transport_error", "error", True,
        "Retry the run after checking Ollama availability or model selection.",
        "retry_same_run",
    ),
    "malformed_tool_call": RecoveryInfo(
        "malformed_tool_call", "warn", True,
        "Inspect the malformed tool payload and retry after correcting the action shape.",
        "inspect_failed_tool_output",
    ),
    "schema_error": RecoveryInfo(
        "schema_error", "error", True,
        "Inspect the schema mismatch and retry after correcting the payload or response contract.",
        "repair_malformed_payload",
    ),
    "tool_failure": RecoveryInfo(
        "tool_failure", "warn", True,
        "Inspect the failed tool output or touched path details before retrying.",
        "inspect_failed_tool_output",
    ),
    "approval_stop": RecoveryInfo(
        "approval_stop", "info", True,
        "Approval is still pending; either grant it or retry later.",
        "request_approval",
    ),
    "approval_denied": RecoveryInfo(
        "approval_denied", "warn", False,
        "Authority was denied. Review the scope and create a narrower request or park as blocked.",
        "park_as_blocked",
    ),
    "max_round_exhaustion": RecoveryInfo(
        "max_round_exhaustion", "warn", True,
        "The agent exhausted its rounds. Retry with a clearer prompt or inspect the last good round.",
        "retry_same_run",
    ),
    "contract_denial": RecoveryInfo(
        "contract_denial", "error", False,
        "The contract gate denied the action. Review authority and path boundaries before retrying.",
        "inspect_contract_denial",
    ),
    "validation_failure": RecoveryInfo(
        "validation_failure", "warn", True,
        "Validation failed. Inspect the validation result before retrying.",
        "run_validation_manually",
    ),
    "operator_stop": RecoveryInfo(
        "operator_stop", "info", True,
        "The run was stopped by an operator and may be retried explicitly.",
        "retry_same_run",
    ),
    "runtime_exception": RecoveryInfo(
        "runtime_exception", "error", True,
        "Inspect the runtime event stream and stack summary before retrying.",
        "inspect_runtime_events",
    ),
    "unknown_failure": RecoveryInfo(
        "unknown_failure", "error", True,
        "Inspect the trace details and runtime events before retrying.",
        "inspect_runtime_events",
    ),
}


class RecoveryManager:
    def classify(self, *, recovery_class: str = "", message: str = "", status: str = "") -> RecoveryInfo:
        normalized = self._normalize(recovery_class=recovery_class, message=message, status=status)
        return _RECOVERY_MAP[normalized]

    def _normalize(self, *, recovery_class: str = "", message: str = "", status: str = "") -> str:
        raw = (recovery_class or "").strip()
        if raw in _RECOVERY_MAP:
            return raw

        text = f"{raw} {message} {status}".lower()
        if "ollama" in text or "transport" in text or "connection" in text or "model not available" in text:
            return "model_transport_error"
        if "valid json" in text or "missing action object" in text or "tool_call.arguments" in text:
            return "malformed_tool_call"
        if "schema" in text:
            return "schema_error"
        if "validation failed" in text:
            return "validation_failure"
        if "approval requested" in text or "awaiting approval" in text:
            return "approval_stop"
        if "denied" in text and "approval" in text:
            return "approval_denied"
        if "contract" in text and "denied" in text:
            return "contract_denial"
        if "max rounds exhausted" in text:
            return "max_round_exhaustion"
        if "stop requested" in text or "operator stop" in text:
            return "operator_stop"
        if "tool" in text and ("failed" in text or "error" in text):
            return "tool_failure"
        if text.strip():
            return "runtime_exception"
        return "unknown_failure"
