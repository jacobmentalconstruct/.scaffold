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
        tranche = self._tranche.get_active()
        if not tranche:
            raise RuntimeError(
                "No active tranche — run tranche-declare before close_tranche."
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
