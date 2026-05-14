"""
FILE: src/orchestrators/closeout_orchestrator.py
ROLE: Close Tranche orchestrator — the "push a button" Park Phase implementation.
WHAT IT DOES (T2.5): Reads the active tranche object + all accumulated decision
      records, validates the checklist, compiles park notes Markdown from
      structured data, writes _docs/T{n}_PARK_NOTES.md, creates and closes
      a tranche journal entry, and seals the active_tranche.

Design intent ("compile-and-seal, not reconstruct-and-write"):
  All the raw data was captured during the tranche:
    - typed DecisionRecords (decision_id, context, rationale, outcome)
    - files_changed list
    - deviations list
    - open_questions list
    - tests_run list (with smoke-pass records)
  close_tranche reads that structured data and derives:
    - the Markdown park notes file (_docs/Tn_PARK_NOTES.md)
    - the blob hash (stored as evidence on the journal entry)
    - the tranche journal entry (kind='tranche', status='closed')
  The 5 Park Phase artifacts (contract §D) are produced atomically:
    (1) _docs/Tn_PARK_NOTES.md written
    (2) park notes in blob_store
    (3) tranche journal entry created + evidence attached
    (4) continuity docs flag set (meta key)
    (5) journal entry closed + active_tranche sealed

Usage:
    python -m src.app cli tranche-close --actor "human:jacob"
    # Or via the T3 Tk UI "Park Tranche" button.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from src.components.ollama_client import OllamaClient
from src.lib.common import now_iso, public_path, public_root_labels, safe_json_dumps
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.blob_store import BlobStore
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState
    from src.managers.journal_manager import JournalManager
    from src.managers.tranche_manager import ActiveTranche, TrancheManager


log = get_logger("orchestrators.closeout")


class CloseoutOrchestrator:
    def __init__(
        self,
        tranche_manager: "TrancheManager",
        journal_manager: "JournalManager",
        blob_store: "BlobStore",
    ):
        self._tranche = tranche_manager
        self._journal = journal_manager
        self._blob = blob_store

    def handle_request_tranche_review(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        tranche = self._tranche.get_active()
        if not tranche:
            raise RuntimeError("No active tranche — only an active tranche can be submitted for review.")

        checklist = self._tranche.build_checklist(state)
        required_failures = [
            c for c in checklist
            if c.required and c.status not in ("pass",)
            and c.item_id not in ("review_approved", "park_notes_written", "journal_entry_closed")
        ]
        if required_failures:
            failure_summary = "; ".join(f"{c.item_id}={c.status}: {c.detail}" for c in required_failures)
            raise RuntimeError(
                f"request_tranche_review blocked — tranche is not ready for review:\n  {failure_summary}"
            )

        decisions = self._tranche.get_decisions(tranche.tranche_id)
        packet = self._compile_review_packet(state, tranche, decisions, checklist)
        packet_refs = self._write_review_packet_files(state, tranche, packet)
        review_id = self._tranche.create_review_packet(
            tranche_id=tranche.tranche_id,
            actor_id=envelope.actor_id,
            review_packet_json_ref=packet_refs["json_blob_ref"],
            review_packet_markdown_ref=packet_refs["markdown_blob_ref"],
            smoke_snapshot=packet.get("verification", {}),
            latest_decision_ids=[d.decision_id for d in decisions],
            latest_test_records=tranche.tests_run[-10:],
            metadata={
                "json_export_path": packet_refs["json_export_path"],
                "markdown_export_path": packet_refs["markdown_export_path"],
                "title": tranche.title,
            },
        )
        response = {
            "status": "review_pending",
            "review_id": review_id,
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "json_export_path": packet_refs["json_export_path"],
            "markdown_export_path": packet_refs["markdown_export_path"],
        }
        response_ref = self._blob.put_json(response)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_return_tranche_review(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        tranche = self._tranche.get_current()
        if not tranche or tranche.status != "review_pending":
            raise RuntimeError("No review_pending tranche — nothing to return to the agent.")
        if not envelope.actor_id.startswith("human:"):
            raise RuntimeError("Only a human actor may return a tranche review.")
        request = self._read_payload(envelope)
        reason = str(request.get("return_reason", "")).strip()
        if not reason:
            raise ValueError("return_tranche_review requires non-empty return_reason.")
        review_id = str(request.get("review_id") or tranche.current_review_id or "").strip()
        if not review_id:
            raise RuntimeError("No review_id available for the pending tranche review.")
        self._tranche.return_review(
            tranche_id=tranche.tranche_id,
            review_id=review_id,
            reviewed_by_actor=envelope.actor_id,
            reason=reason,
        )
        response = {
            "status": "active",
            "review_id": review_id,
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "return_reason": reason,
        }
        return envelope.with_status("completed").with_payload_ref(self._blob.put_json(response))

    def handle_approve_tranche_review(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        tranche = self._tranche.get_current()
        if not tranche or tranche.status != "review_pending":
            raise RuntimeError("No review_pending tranche — nothing to approve for Park Phase.")
        if not envelope.actor_id.startswith("human:"):
            raise RuntimeError("Only a human actor may approve tranche review.")
        request = self._read_payload(envelope)
        review_id = str(request.get("review_id") or tranche.current_review_id or "").strip()
        if not review_id:
            raise RuntimeError("No review_id available for approval.")
        notes = str(request.get("approval_notes", "")).strip()
        self._tranche.approve_review(
            tranche_id=tranche.tranche_id,
            review_id=review_id,
            reviewed_by_actor=envelope.actor_id,
            notes=notes,
        )
        response = {
            "status": "review_approved",
            "review_id": review_id,
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "approval_notes": notes,
            "park_ready": True,
        }
        return envelope.with_status("completed").with_payload_ref(self._blob.put_json(response))

    # ===== envelope handler (called by Router) =========================

    def handle_close_tranche(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        """Handler for close_tranche.

        Payload keys (all optional):
          dry_run (bool) — if True, compile notes + validate checklist but
                           do NOT write files or seal the tranche.
          skip_smoke_check (bool) — if True, skip the smoke_test_passed gate
                                    (useful in CI where smoke is run separately).
          extra_notes (str) — freeform text appended to the park notes.
          use_ollama (bool) — if True, attempt LLM-generated prose park notes via
                              local Ollama; falls back to template compiler on failure.
          ollama_model (str) — Ollama model name (default: qwen3.5:9b).
          ollama_num_predict (int) — max tokens to generate (default: 8192);
                                     caps GPU memory use.
        """
        request = self._read_payload(envelope)
        dry_run = bool(request.get("dry_run", False))
        skip_smoke = bool(request.get("skip_smoke_check", False))
        extra_notes = request.get("extra_notes", "")
        use_ollama = bool(request.get("use_ollama", False))
        ollama_model = request.get("ollama_model", "qwen3.5:9b")
        ollama_num_predict = int(request.get("ollama_num_predict", 8192))

        # --- 1. Get active tranche ----------------------------------------
        tranche = self._tranche.get_current()
        if not tranche:
            raise RuntimeError(
                "No current tranche — run tranche-declare before close_tranche."
            )
        if tranche.status != "review_approved":
            raise RuntimeError(
                f"close_tranche blocked — tranche status is {tranche.status!r}. "
                "Run tranche-review-request, get explicit human approval, then close."
            )

        # --- 2. Validate checklist ----------------------------------------
        checklist = self._tranche.build_checklist(state)
        required_failures = [
            c for c in checklist
            if c.required and c.status not in ("pass",)
            and not (skip_smoke and c.item_id == "smoke_test_passed")
            # park_notes_written and journal_entry_closed are produced BY close_tranche;
            # exclude them from the pre-close gate.
            and c.item_id not in ("park_notes_written", "journal_entry_closed")
        ]
        if required_failures:
            failure_summary = "; ".join(
                f"{c.item_id}={c.status}: {c.detail}" for c in required_failures
            )
            raise RuntimeError(
                f"close_tranche blocked — required checklist items not satisfied:\n"
                f"  {failure_summary}\n"
                f"Fix these before running close_tranche."
            )

        # --- 3. Collect decisions -----------------------------------------
        decisions = self._tranche.get_decisions(tranche.tranche_id)

        # --- 4. Compile park notes Markdown --------------------------------
        # Try LLM generation first if requested; fall back to template compiler.
        notes_text: str | None = None
        ollama_used = False
        if use_ollama:
            notes_text = self._try_ollama_generation(
                tranche, decisions, ollama_model, ollama_num_predict
            )
            if notes_text:
                ollama_used = True
                log.info("park notes: using Ollama-generated prose (model=%s)", ollama_model)
            else:
                log.warning(
                    "park notes: Ollama unavailable or returned nothing — "
                    "falling back to template compiler"
                )
        if not notes_text:
            notes_text = self._compile_park_notes(tranche, decisions, extra_notes)

        # --- 5. Determine output filename ---------------------------------
        docs_dir = Path(state.sidecar_root) / "_docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        notes_filename = _make_notes_filename(tranche.title)
        notes_path = docs_dir / notes_filename
        _, sidecar_root_label = public_root_labels(state.sidecar_root, state.project_root)
        notes_public_path = public_path(notes_path, state.sidecar_root, sidecar_root_label)

        if dry_run:
            # Return the compiled text without writing anything.
            preview_ref = self._blob.put_text(notes_text, content_type="text/markdown")
            response = {
                "dry_run": True,
                "tranche_id": tranche.tranche_id,
                "title": tranche.title,
                "notes_filename": notes_filename,
                "notes_preview_ref": preview_ref,
                "checklist_summary": [
                    {"item_id": c.item_id, "status": c.status, "detail": c.detail}
                    for c in checklist
                ],
                "decisions_count": len(decisions),
                "would_write": notes_public_path,
            }
            response_ref = self._blob.put_json(response)
            log.info("close_tranche dry-run: tranche=%s", tranche.tranche_id)
            return envelope.with_status("completed").with_payload_ref(response_ref)

        # --- 6. Write park notes file -------------------------------------
        notes_path.write_text(notes_text, encoding="utf-8")
        log.info("park notes written: %s", notes_public_path)

        # --- 7. Store park notes in blob_store ----------------------------
        park_notes_ref = self._blob.put_text(notes_text, content_type="text/markdown")
        log.info("park notes blob: ref=%s", park_notes_ref[:16])

        # --- 8. Create tranche journal entry (direct write) ---------------
        journal_body = self._build_journal_body(tranche, decisions, park_notes_ref)
        evidence_refs = [{"hash": park_notes_ref, "kind": "park_notes"}]
        # Include any evidence refs accumulated during the tranche.
        for ref in (tranche.evidence_refs or []):
            if isinstance(ref, dict) and ref.get("hash"):
                evidence_refs.append(ref)

        entry_uid = self._journal.create_direct(
            kind="tranche",
            title=tranche.title,
            body=journal_body,
            actor_id=envelope.actor_id,
            importance=9,
            tags=["park_phase", "tranche"],
            evidence_refs=evidence_refs,
            event_id=envelope.event_id or "DIRECT",
            metadata={
                "tranche_id": tranche.tranche_id,
                "park_notes_blob_ref": park_notes_ref,
                "decisions_count": len(decisions),
                "files_changed_count": len(tranche.files_changed),
            },
        )

        # --- 9. Close the journal entry -----------------------------------
        self._journal.close_direct(entry_uid, event_id=envelope.event_id)

        # --- 10. Seal the active tranche ----------------------------------
        self._tranche.seal(tranche.tranche_id, park_notes_ref, entry_uid)

        # --- 11. Set continuity docs flag in meta -------------------------
        state.store.set_meta("last_park_phase_at", now_iso())
        state.store.set_meta("last_park_phase_tranche", tranche.title)
        closeout_metadata = derive_closeout_metadata(state, entry_uid)
        write_closeout_metadata_files(state, closeout_metadata)

        log.info(
            "close_tranche complete: tranche=%s title=%r entry_uid=%s park_notes=%s",
            tranche.tranche_id, tranche.title, entry_uid, notes_filename,
        )

        response = {
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "park_notes_path": notes_public_path,
            "park_notes_blob_ref": park_notes_ref,
            "journal_entry_uid": entry_uid,
            "decisions_count": len(decisions),
            "files_changed_count": len(tranche.files_changed),
            "checklist_pass_count": sum(1 for c in checklist if c.status == "pass"),
            "checklist_total": len(checklist),
            "notes_filename": notes_filename,
            "ollama_used": ollama_used,
            "ollama_model": ollama_model if ollama_used else None,
            "closeout_metadata_json_path": closeout_metadata.get("latest_json_path", ""),
        }
        response_ref = self._blob.put_json(response)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    # ===== Ollama-assisted notes generation ============================

    def _try_ollama_generation(
        self,
        tranche: "ActiveTranche",
        decisions: list,
        model: str,
        num_predict: int = 8192,
    ) -> str | None:
        """Attempt to generate park notes via a local Ollama model.

        Returns the generated Markdown string, or None if Ollama is
        unavailable or returns an unusable response.  The caller falls
        back to _compile_park_notes() on None.
        """
        client = OllamaClient()
        if not client.is_available(model):
            log.warning("_try_ollama_generation: model %r not available", model)
            return None

        system = (
            "You are a technical documentation writer for a software project. "
            "Write concise, clear Markdown park notes for a development tranche "
            "(a bounded unit of work). Use the structured JSON data provided to "
            "produce well-formed prose. Keep section headings. Be factual and brief."
        )
        prompt = self._build_ollama_prompt(tranche, decisions)
        return client.generate(
            model=model, prompt=prompt, system=system, num_predict=num_predict
        )

    def _build_ollama_prompt(
        self,
        tranche: "ActiveTranche",
        decisions: list,
    ) -> str:
        """Build the user prompt for Ollama from structured tranche data."""
        decisions_payload = [
            {
                "title": d.title,
                "impact_area": d.impact_area,
                "context": d.context,
                "rationale": d.rationale,
                "outcome": d.outcome,
                "importance": d.importance,
            }
            for d in decisions
        ]
        tranche_data = {
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "started_at": tranche.started_at,
            "declared_scope": tranche.declared_scope,
            "declared_non_goals": tranche.declared_non_goals,
            "declared_completion_criteria": tranche.declared_completion_criteria,
            "files_changed": tranche.files_changed,
            "tests_run": tranche.tests_run,
            "deviations": tranche.deviations,
            "open_questions": tranche.open_questions,
            "next_tranche_candidate": tranche.next_tranche_candidate,
            "decisions": decisions_payload,
        }
        data_json = json.dumps(tranche_data, indent=2, default=str)
        return (
            f"Write Markdown park notes for the following development tranche.\n\n"
            f"Use these sections (include only sections with content):\n"
            f"- # Park Notes — <title>\n"
            f"- ## Declared Scope\n"
            f"- ## Decisions Recorded  (one ### subsection per decision with context/rationale/outcome)\n"
            f"- ## Files Changed\n"
            f"- ## Tests Run\n"
            f"- ## Deviations  (if any)\n"
            f"- ## Open Questions  (if any)\n"
            f"- ## Next Tranche  (if known)\n"
            f"- A closing italic line crediting closeout_orchestrator\n\n"
            f"Tranche data (JSON):\n"
            f"```json\n{data_json}\n```\n\n"
            f"Write the Markdown now:"
        )

    # ===== Park notes compiler =========================================

    def _compile_review_packet(
        self,
        state: "SidecarState",
        tranche: "ActiveTranche",
        decisions: list,
        checklist: list,
    ) -> dict:
        run_summary = (
            state.run_trace_manager.summary(limit=6)
            if getattr(state, "run_trace_manager", None)
            else {}
        )
        handoff_row = state.store.query_one("SELECT * FROM proj_handoff WHERE id = 1;")
        def _row_value(name: str, default: str) -> str:
            if not handoff_row:
                return default
            try:
                value = handoff_row[name]
            except Exception:
                return default
            return value if value is not None else default
        handoff = {
            "latest_closed_tranche": json.loads(_row_value("latest_closed_tranche_json", "{}")),
            "active_tranche": json.loads(_row_value("active_tranche_json", "{}")),
            "active_horizon": json.loads(_row_value("active_horizon_json", "{}")),
            "open_questions": json.loads(_row_value("open_questions_json", "[]")),
        } if handoff_row else {"latest_closed_tranche": {}, "active_tranche": {}, "active_horizon": {}, "open_questions": []}

        tools = []
        if getattr(state, "tool_registry_manager", None):
            tools = [tool.tool_name for tool in state.tool_registry_manager.list_tools()]

        packet = {
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "status": "review_pending",
            "generated_at": now_iso(),
            "declared_scope": tranche.declared_scope,
            "declared_non_goals": tranche.declared_non_goals,
            "declared_completion_criteria": tranche.declared_completion_criteria,
            "what_landed": {
                "files_changed_count": len(tranche.files_changed),
                "decisions_count": len(decisions),
                "schema_version": state.store.schema_version(),
                "registered_tools_count": len(tools),
                "recent_run_count": len((run_summary or {}).get("recent_runs", [])),
            },
            "decisions": [
                {
                    "decision_id": d.decision_id,
                    "title": d.title,
                    "impact_area": d.impact_area,
                    "rationale": d.rationale,
                    "outcome": d.outcome,
                    "importance": d.importance,
                }
                for d in decisions
            ],
            "files_changed": tranche.files_changed,
            "verification": {
                "tests_run": tranche.tests_run,
                "required_checklist": [
                    {
                        "item_id": c.item_id,
                        "status": c.status,
                        "detail": c.detail,
                        "required": c.required,
                    }
                    for c in checklist
                ],
            },
            "schema_tools_runtime": {
                "schema_version": state.store.schema_version(),
                "tools": tools,
                "runtime_summary": run_summary,
            },
            "out_of_scope": tranche.declared_non_goals,
            "remains_deferred": handoff.get("open_questions", []),
            "proposed_next_horizon": handoff.get("active_horizon", {}),
            "open_questions": tranche.open_questions,
        }
        return packet

    def _write_review_packet_files(
        self,
        state: "SidecarState",
        tranche: "ActiveTranche",
        packet: dict,
    ) -> dict:
        docs_stem = _make_notes_filename(tranche.title).replace("_PARK_NOTES.md", "")
        stamp = now_iso().replace(":", "").replace("-", "").replace(".", "")
        export_dir = Path(state.sidecar_root) / "exports" / "tranche_reviews" / docs_stem
        export_dir.mkdir(parents=True, exist_ok=True)
        json_path = export_dir / f"review_{stamp}.json"
        md_path = export_dir / f"review_{stamp}.md"

        json_text = safe_json_dumps(packet, indent=2) + "\n"
        markdown = self._compile_review_markdown(packet)
        json_path.write_text(json_text, encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        json_blob_ref = self._blob.put_text(json_text, content_type="application/json")
        markdown_blob_ref = self._blob.put_text(markdown, content_type="text/markdown")
        _, sidecar_root_label = public_root_labels(state.sidecar_root, state.project_root)
        return {
            "json_blob_ref": json_blob_ref,
            "markdown_blob_ref": markdown_blob_ref,
            "json_export_path": public_path(json_path, state.sidecar_root, sidecar_root_label),
            "markdown_export_path": public_path(md_path, state.sidecar_root, sidecar_root_label),
        }

    def _compile_review_markdown(self, packet: dict) -> str:
        lines = [
            f"# Tranche Review — {packet.get('title', '')}",
            "",
            f"> Generated: {packet.get('generated_at', '')}",
            f"> tranche_id: {packet.get('tranche_id', '')}",
            "",
            "## Declared Scope",
            packet.get("declared_scope", "") or "_(none)_",
            "",
            "## Explicit Non-goals",
            packet.get("declared_non_goals", "") or "_(none)_",
            "",
            "## Completion Criteria",
            packet.get("declared_completion_criteria", "") or "_(none)_",
            "",
            "## What Landed",
            f"- files_changed_count: {packet.get('what_landed', {}).get('files_changed_count', 0)}",
            f"- decisions_count: {packet.get('what_landed', {}).get('decisions_count', 0)}",
            f"- schema_version: {packet.get('what_landed', {}).get('schema_version', 0)}",
            f"- registered_tools_count: {packet.get('what_landed', {}).get('registered_tools_count', 0)}",
            "",
            "## Decisions Recorded",
        ]
        decisions = packet.get("decisions", [])
        if decisions:
            for item in decisions:
                lines.extend(
                    [
                        f"- {item.get('title', '')}",
                        f"  impact_area: {item.get('impact_area', '')}",
                        f"  outcome: {item.get('outcome', '')}",
                    ]
                )
        else:
            lines.append("_(none)_")
        lines.extend(
            [
                "",
                "## Files Changed",
            ]
        )
        files_changed = packet.get("files_changed", [])
        if files_changed:
            for item in files_changed:
                lines.append(f"- {item.get('path', '')} ({item.get('change_type', 'modified')})")
        else:
            lines.append("_(none tracked)_")
        lines.extend(
            [
                "",
                "## Verification Passed",
            ]
        )
        for item in packet.get("verification", {}).get("required_checklist", []):
            if item.get("required"):
                lines.append(f"- {item.get('item_id')}: {item.get('status')} — {item.get('detail', '')}")
        lines.extend(
            [
                "",
                "## What Was Explicitly Out Of Scope",
                packet.get("out_of_scope", "") or "_(none)_",
                "",
                "## What Remains Deferred",
            ]
        )
        deferred = packet.get("remains_deferred", [])
        if deferred:
            lines.extend([f"- {item}" for item in deferred])
        else:
            lines.append("_(none)_")
        lines.extend(
            [
                "",
                "## Proposed Next Horizon",
                safe_json_dumps(packet.get("proposed_next_horizon", {}), indent=2),
                "",
                "## Open Questions / Doubts Before Park",
            ]
        )
        open_questions = packet.get("open_questions", [])
        if open_questions:
            for item in open_questions:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('question', '')}")
                else:
                    lines.append(f"- {item}")
        else:
            lines.append("_(none)_")
        lines.extend(["", "_Mechanically compiled from active_tranche, decisions, tests, projections, and runtime state._", ""])
        return "\n".join(lines)

    def _compile_park_notes(
        self,
        tranche: "ActiveTranche",
        decisions: list,
        extra_notes: str = "",
    ) -> str:
        """Compile the Markdown park notes from structured tranche data.

        This is the "compile-and-seal" step — all the raw data was captured
        during the tranche; we render it here.
        """
        now = now_iso()
        lines: list[str] = []

        lines.append(f"# Park Notes — {tranche.title}")
        lines.append(f"\n> Generated: {now} | Status: sealed | tranche_id: {tranche.tranche_id}")
        lines.append(f"> Started: {tranche.started_at}")
        if tranche.closed_at:
            lines.append(f"> Closed: {tranche.closed_at}")
        lines.append("")

        # --- Declared scope ---
        lines.append("## Declared Scope")
        if tranche.declared_scope.strip():
            lines.append(textwrap.indent(tranche.declared_scope.strip(), ""))
        else:
            lines.append("_(no scope declared)_")
        lines.append("")

        if tranche.declared_non_goals.strip():
            lines.append("### Non-goals")
            lines.append(tranche.declared_non_goals.strip())
            lines.append("")

        if tranche.declared_completion_criteria.strip():
            lines.append("### Completion Criteria")
            lines.append(tranche.declared_completion_criteria.strip())
            lines.append("")

        # --- Decisions ---
        lines.append("## Decisions Recorded")
        if decisions:
            lines.append(f"_{len(decisions)} decision(s) captured during this tranche._")
            lines.append("")
            for d in decisions:
                lines.append(f"### {d.title}")
                if d.impact_area:
                    lines.append(f"**Impact area:** {d.impact_area}")
                if d.context.strip():
                    lines.append(f"\n**Context:** {d.context.strip()}")
                if d.rationale.strip():
                    lines.append(f"\n**Rationale:** {d.rationale.strip()}")
                if d.outcome.strip():
                    lines.append(f"\n**Outcome:** {d.outcome.strip()}")
                if d.alternatives:
                    lines.append("\n**Alternatives considered:**")
                    for alt in d.alternatives:
                        if isinstance(alt, dict):
                            option = alt.get("option", str(alt))
                            reason = alt.get("reason_rejected", "")
                            lines.append(f"- {option}" + (f" — {reason}" if reason else ""))
                        else:
                            lines.append(f"- {alt}")
                lines.append(f"\n_decision_id: {d.decision_id} | importance: {d.importance}_")
                lines.append("")
        else:
            lines.append("_No typed decisions were recorded for this tranche._")
            lines.append("")

        # --- Files changed ---
        lines.append("## Files Changed")
        if tranche.files_changed:
            for fc in tranche.files_changed:
                if isinstance(fc, dict):
                    path = fc.get("path", str(fc))
                    change = fc.get("change_type", "modified")
                    lines.append(f"- `{path}` ({change})")
                else:
                    lines.append(f"- `{fc}`")
        else:
            lines.append("_No files explicitly tracked. Review git diff for actual changes._")
        lines.append("")

        # --- Tests run ---
        lines.append("## Tests Run")
        if tranche.tests_run:
            for tr in tranche.tests_run:
                if isinstance(tr, dict):
                    name = tr.get("test_name", "?")
                    passed = "PASS" if tr.get("passed") else "FAIL"
                    ran_at = tr.get("ran_at", "?")
                    lines.append(f"- `{name}` → {passed} (at {ran_at})")
                else:
                    lines.append(f"- {tr}")
        else:
            lines.append("_No test records captured._")
        lines.append("")

        # --- Deviations ---
        if tranche.deviations:
            lines.append("## Deviations from Original Scope")
            for dev in tranche.deviations:
                if isinstance(dev, dict):
                    desc = dev.get("description", str(dev))
                    reason = dev.get("reason", "")
                    impact = dev.get("impact", "")
                    lines.append(f"- **{desc}**")
                    if reason:
                        lines.append(f"  - Reason: {reason}")
                    if impact:
                        lines.append(f"  - Impact: {impact}")
                else:
                    lines.append(f"- {dev}")
            lines.append("")

        # --- Open questions ---
        if tranche.open_questions:
            lines.append("## Open Questions (carry forward)")
            for oq in tranche.open_questions:
                if isinstance(oq, dict):
                    q = oq.get("question", str(oq))
                    raised = oq.get("raised_at", "")
                    lines.append(f"- {q}" + (f" _(raised {raised})_" if raised else ""))
                else:
                    lines.append(f"- {oq}")
            lines.append("")

        # --- Evidence refs ---
        if tranche.evidence_refs:
            lines.append("## Evidence Refs")
            for ref in tranche.evidence_refs:
                if isinstance(ref, dict):
                    h = ref.get("hash", "?")
                    kind = ref.get("kind", "")
                    summary = ref.get("summary", "")
                    lines.append(
                        f"- `{h[:32]}...` [{kind}]"
                        + (f" — {summary}" if summary else "")
                    )
                else:
                    lines.append(f"- {ref}")
            lines.append("")

        # --- Next tranche ---
        if tranche.next_tranche_candidate:
            lines.append("## Next Tranche")
            lines.append(tranche.next_tranche_candidate)
            lines.append("")

        # --- Extra notes ---
        if extra_notes.strip():
            lines.append("## Additional Notes")
            lines.append(extra_notes.strip())
            lines.append("")

        lines.append("---")
        lines.append(f"_Park notes auto-compiled by closeout_orchestrator at {now}._")
        lines.append(f"_Source: tranche_id={tranche.tranche_id}_")

        return "\n".join(lines) + "\n"

    def _build_journal_body(
        self,
        tranche: "ActiveTranche",
        decisions: list,
        park_notes_ref: str,
    ) -> str:
        """Short journal body for the tranche entry (summary, not full notes)."""
        dec_titles = [d.title for d in decisions[:5]]
        dec_summary = (
            ", ".join(f'"{t}"' for t in dec_titles)
            + (f", +{len(decisions) - 5} more" if len(decisions) > 5 else "")
        ) if dec_titles else "none"

        return textwrap.dedent(f"""
            Tranche parked: {tranche.title}

            **Scope:** {tranche.declared_scope[:300] or '(not declared)'}

            **Decisions ({len(decisions)}):** {dec_summary}

            **Files changed:** {len(tranche.files_changed)} explicitly tracked

            **Tests run:** {len([t for t in tranche.tests_run if t.get('passed')])} pass / {len(tranche.tests_run)} total

            Park notes blob ref: `{park_notes_ref[:32]}...`
        """).strip()

    @staticmethod
    def _read_payload(envelope: "SidecarEnvelope") -> dict:
        return {}  # payload_ref is optional for close_tranche

    # Overridden below when blob_store is available.
    def _read_payload(self, envelope: "SidecarEnvelope") -> dict:
        if not envelope.payload_ref:
            return {}
        try:
            return self._blob.get_json(envelope.payload_ref)
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_notes_filename(title: str) -> str:
    """Derive a park notes filename from a tranche title.

    'T3 Tk UI' → 'T3_PARK_NOTES.md'
    'T2.5 Active Tranche Ledger' → 'T2_5_PARK_NOTES.md'
    'My Custom Tranche' → 'TRANCHE_PARK_NOTES.md'
    """
    import re
    m = re.match(r"^(T[\d.]+)", title.strip(), re.IGNORECASE)
    if m:
        label = m.group(1).replace(".", "_").upper()
        return f"{label}_PARK_NOTES.md"
    # Fall back to sanitised title.
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", title.strip()).upper()
    return f"{safe[:30]}_PARK_NOTES.md"


def _make_closeout_metadata_filenames(title: str) -> tuple[str, str]:
    notes_name = _make_notes_filename(title)
    stem = notes_name[:-len("_PARK_NOTES.md")] if notes_name.endswith("_PARK_NOTES.md") else notes_name.rsplit(".", 1)[0]
    return (f"{stem}_CLOSEOUT_METADATA.json", f"{stem}_CLOSEOUT_METADATA.md")


def derive_closeout_metadata(state: "SidecarState", journal_entry_uid: str = "") -> dict:
    """Return authoritative derived closeout metadata for one closed tranche."""
    if journal_entry_uid:
        row = state.store.query_one(
            """
            SELECT entry_uid, title, status, created_at, metadata_json
            FROM journal_entries
            WHERE entry_uid = ? AND kind = 'tranche' AND status = 'closed'
            LIMIT 1;
            """,
            (journal_entry_uid,),
        )
    else:
        row = state.store.query_one(
            """
            SELECT entry_uid, title, status, created_at, metadata_json
            FROM journal_entries
            WHERE kind = 'tranche' AND status = 'closed'
            ORDER BY created_at DESC
            LIMIT 1;
            """
        )
    if not row:
        raise RuntimeError("No closed tranche journal entry available for closeout metadata derivation.")

    journal_meta = json.loads(row["metadata_json"] or "{}")
    tranche_id = str(journal_meta.get("tranche_id") or "")
    parked_row = None
    if tranche_id:
        parked_row = state.store.query_one(
            "SELECT * FROM active_tranche WHERE tranche_id = ? LIMIT 1;",
            (tranche_id,),
        )
    if parked_row is None:
        parked_row = state.store.query_one(
            "SELECT * FROM active_tranche WHERE journal_entry_uid = ? LIMIT 1;",
            (row["entry_uid"],),
        )

    title = str(row["title"] or "")
    notes_filename = _make_notes_filename(title)
    per_json_name, per_md_name = _make_closeout_metadata_filenames(title)
    closed_at = row["created_at"]
    decisions_count = int(journal_meta.get("decisions_count", 0) or 0)
    files_changed_count = int(journal_meta.get("files_changed_count", 0) or 0)
    park_notes_blob_ref = str(journal_meta.get("park_notes_blob_ref") or "")

    if parked_row:
        closed_at = parked_row["closed_at"] or closed_at
        if not park_notes_blob_ref:
            park_notes_blob_ref = str(parked_row["park_notes_blob_ref"] or "")
        if not decisions_count:
            decisions_count = int(parked_row["decisions_count"] or 0)
        if not files_changed_count:
            files_changed_count = len(json.loads(parked_row["files_changed_json"] or "[]"))

    return {
        "title": title,
        "tranche_id": tranche_id,
        "journal_entry_uid": row["entry_uid"],
        "journal_created_at": row["created_at"],
        "closed_at": closed_at,
        "status": str(row["status"] or "closed"),
        "park_notes_path": f"_docs/{notes_filename}",
        "park_notes_blob_ref": park_notes_blob_ref,
        "decisions_count": decisions_count,
        "files_changed_count": files_changed_count,
        "per_tranche_json_path": f"_docs/{per_json_name}",
        "per_tranche_markdown_path": f"_docs/{per_md_name}",
        "latest_json_path": "_docs/LATEST_PARKED_TRANCHE.json",
        "latest_markdown_path": "_docs/LATEST_PARKED_TRANCHE.md",
        "generated_at": now_iso(),
        "source": "closeout_orchestrator",
        "note": "park_notes_blob_ref is the sidecar CAS blob ref, not the Git file SHA for the Markdown park-notes file.",
    }


def write_closeout_metadata_files(state: "SidecarState", metadata: dict) -> dict:
    """Write authoritative generated closeout metadata for humans and agents."""
    sidecar_root = Path(state.sidecar_root)
    per_json_path = sidecar_root / metadata["per_tranche_json_path"]
    per_md_path = sidecar_root / metadata["per_tranche_markdown_path"]
    latest_json_path = sidecar_root / metadata["latest_json_path"]
    latest_md_path = sidecar_root / metadata["latest_markdown_path"]

    json_text = safe_json_dumps(metadata, indent=2) + "\n"
    markdown = "\n".join(
        [
            f"# Closeout Metadata — {metadata['title']}",
            "",
            "> Generated from the authoritative closeout state.",
            "> Exact ids and refs here are derived, not hand-copied.",
            "",
            f"- `tranche_id`: `{metadata['tranche_id']}`",
            f"- `journal_entry_uid`: `{metadata['journal_entry_uid']}`",
            f"- `park_notes_path`: `{metadata['park_notes_path']}`",
            f"- `park_notes_blob_ref`: `{metadata['park_notes_blob_ref']}`",
            f"- `closed_at`: `{metadata['closed_at']}`",
            f"- `decisions_count`: {metadata['decisions_count']}",
            f"- `files_changed_count`: {metadata['files_changed_count']}",
            f"- `generated_at`: `{metadata['generated_at']}`",
            "",
            metadata["note"],
            "",
        ]
    )

    per_json_path.write_text(json_text, encoding="utf-8")
    per_md_path.write_text(markdown, encoding="utf-8")
    latest_json_path.write_text(json_text, encoding="utf-8")
    latest_md_path.write_text(markdown, encoding="utf-8")

    state.store.set_meta("latest_closed_tranche_journal_uid", str(metadata["journal_entry_uid"]))
    state.store.set_meta("latest_closed_tranche_title", str(metadata["title"]))
    state.store.set_meta("latest_park_notes_blob_ref", str(metadata["park_notes_blob_ref"]))
    state.store.set_meta("latest_park_notes_path", str(metadata["park_notes_path"]))
    state.store.set_meta("latest_closeout_metadata_json_path", str(metadata["latest_json_path"]))
    state.store.set_meta("latest_closeout_metadata_markdown_path", str(metadata["latest_markdown_path"]))
    return metadata
