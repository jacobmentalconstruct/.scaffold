"""
FILE: src/managers/installed_project_proof_manager.py
ROLE: T9 installed-project proof manager.
WHAT IT DOES: Creates a tiny disposable host project, installs a clean
              `.scaffold` copy into it, runs the proof loop from the
              installed context, verifies the resulting artifact chain,
              and exports a cold-team handoff packet.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from src.lib.common import gen_id, now_iso, public_path, safe_json_dumps


FIXTURE_ID = "tiny_notes_app"
FIXTURE_VERSION = "1"


class InstalledProjectProofManager:
    def __init__(self, state):
        self._state = state
        self._store = state.store
        self._host_root = Path(state.sidecar_root) / "workspaces" / "installed_project_proof" / FIXTURE_ID
        self._installed_sidecar_root = self._host_root / ".scaffold"
        self._export_root = self._installed_sidecar_root / "exports" / "installed_project_proof"

    def create_fixture(self, *, reset: bool = False) -> dict[str, Any]:
        if reset and self._host_root.exists():
            shutil.rmtree(self._host_root)
        self._host_root.mkdir(parents=True, exist_ok=True)
        (self._host_root / "README.md").write_text(
            "# Tiny Notes App\n\nThis disposable host fixture exists to prove `.scaffold` vendability.\n",
            encoding="utf-8",
        )
        (self._host_root / "app.py").write_text(
            "def main() -> str:\n    return 'tiny-notes-app'\n\n\nif __name__ == '__main__':\n    print(main())\n",
            encoding="utf-8",
        )
        (self._host_root / "settings.json").write_text(
            safe_json_dumps({"app": "tiny-notes-app", "proof_ready": True}, indent=2),
            encoding="utf-8",
        )
        (self._host_root / ".gitignore").write_text(".scaffold/\n", encoding="utf-8")
        return {
            "status": "ok",
            "fixture_id": FIXTURE_ID,
            "fixture_version": FIXTURE_VERSION,
            "host_root": public_path(self._host_root, self._state.sidecar_root, "."),
            "installed_sidecar_root": public_path(self._installed_sidecar_root, self._state.sidecar_root, "."),
            "reset": reset,
            "files": ["README.md", "app.py", "settings.json", ".gitignore"],
        }

    def run_proof(self) -> dict[str, Any]:
        fixture = self.create_fixture(reset=True)
        self._install_sidecar_copy()

        proof_run_id = gen_id("proof_run_")
        self._store.execute(
            """
            INSERT INTO installed_project_proofs(
                proof_run_id, fixture_id, fixture_version, host_root, installed_sidecar_root,
                status, install_state_json, verification_summary_json, proposal_summary_json,
                linked_run_ids_json, linked_scorecard_ids_json, linked_evidence_refs_json,
                linked_journal_uids_json, approval_request_id, approval_grant_id, touched_paths_json,
                hunk_refs_json, handoff_packet_ref, supersession_status, started_at, ended_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, 'running', ?, '{}', '{}', '[]', '[]', '[]', '[]', NULL, NULL, '[]', '[]', '', '', ?, NULL, '{}');
            """,
            (
                proof_run_id,
                FIXTURE_ID,
                FIXTURE_VERSION,
                public_path(self._host_root, self._state.sidecar_root, "."),
                public_path(self._installed_sidecar_root, self._state.sidecar_root, "."),
                safe_json_dumps({"fixture": fixture}),
                now_iso(),
            ),
        )

        install_state = self._run_install_state_checks()
        prompt = (
            "Create a bounded host-project proof note named proof_notes.md that states the "
            "installed-project vendability proof succeeded."
        )
        approval_scope = {
            "tool_name": "text_file_writer",
            "target_domain": "project",
            "path": "proof_notes.md",
        }
        run_one = self._run_installed_cli(
            [
                "local-agent-run",
                "--actor", "agent:local:proof",
                "--model", "qwen3.5:9b",
                "--max-rounds", "3",
                "--no-ui",
                "--prompt", prompt,
                "--mock-response", safe_json_dumps({
                    "summary": "Request approval to create the installed-project proof note.",
                    "action": {
                        "type": "request_approval",
                        "requested_level": "Apply",
                        "summary": "Create proof_notes.md inside the installed host project.",
                        "justification": "T9 requires one governed installed-project mutation.",
                        "scope_pattern": approval_scope,
                    },
                }),
            ]
        )
        approval_request_id = str(((run_one.get("approval_request") or {}).get("request_id", "")) or "")

        approval = self._run_installed_cli(
            [
                "approval-approve",
                "--actor", "human:proof:operator",
                "--request-id", approval_request_id,
                "--expires-minutes", "60",
                "--single-use",
                "--decision-reason", "T9 installed-project proof approval.",
            ]
        )
        approval_grant_id = str(approval.get("grant_id", "") or (approval.get("grant") or {}).get("grant_id", "") or "")
        self._store.execute(
            """
            UPDATE installed_project_proofs
            SET approval_request_id = ?, approval_grant_id = ?, metadata_json = ?
            WHERE proof_run_id = ?;
            """,
            (
                approval_request_id or None,
                approval_grant_id or None,
                safe_json_dumps({"approval_step": {"request_id": approval_request_id, "grant_id": approval_grant_id}}),
                proof_run_id,
            ),
        )

        run_two = self._run_installed_cli(
            [
                "local-agent-run",
                "--actor", "agent:local:proof",
                "--model", "qwen3.5:9b",
                "--max-rounds", "3",
                "--no-ui",
                "--prompt", prompt,
                "--mock-response", safe_json_dumps({
                    "summary": "Write the bounded installed-project proof note.",
                    "action": {
                        "type": "tool_call",
                        "tool_name": "text_file_writer",
                        "arguments": {
                            "path": "proof_notes.md",
                            "content": "# Proof Notes\n\nInstalled-project vendability proof completed successfully.\n",
                            "action": "create",
                            "confirm": True,
                            "overwrite": False,
                            "create_dirs": True,
                            "target_domain": "project",
                            "allow_host_project_write": True,
                            "protected_paths": [".scaffold/"],
                        },
                    },
                }),
                "--mock-response", safe_json_dumps({
                    "summary": "Created proof_notes.md in the installed host project.",
                    "action": {
                        "type": "final",
                        "message": "Created proof_notes.md and completed the installed-project vendability proof.",
                    },
                }),
            ]
        )
        linked_run_ids = [
            run_id for run_id in (
                str(run_one.get("run_id", "")),
                str(run_two.get("run_id", "")),
            ) if run_id
        ]

        self._refresh_child_projections()
        verification = self.verify_proof(proof_run_id=proof_run_id, linked_run_ids=linked_run_ids)
        handoff = self.export_handoff_packet(proof_run_id=proof_run_id)
        proposal_summary = {
            "proposal": "Create proof_notes.md in the installed host project.",
            "approval_request_id": approval_request_id,
            "approval_grant_id": approval_grant_id,
            "linked_run_ids": linked_run_ids,
            "mutation_target": "proof_notes.md",
        }

        self._store.execute(
            """
            UPDATE installed_project_proofs
            SET status = ?, install_state_json = ?, verification_summary_json = ?, proposal_summary_json = ?,
                linked_run_ids_json = ?, linked_evidence_refs_json = ?, linked_journal_uids_json = ?,
                approval_request_id = ?, approval_grant_id = ?, touched_paths_json = ?, hunk_refs_json = ?,
                handoff_packet_ref = ?, supersession_status = ?, ended_at = ?, metadata_json = ?
            WHERE proof_run_id = ?;
            """,
            (
                "completed" if verification.get("ok") else "failed",
                safe_json_dumps(install_state),
                safe_json_dumps(verification),
                safe_json_dumps(proposal_summary),
                safe_json_dumps(linked_run_ids),
                safe_json_dumps(verification.get("evidence_refs", [])),
                safe_json_dumps(verification.get("journal_uids", [])),
                approval_request_id or None,
                approval_grant_id or None,
                safe_json_dumps(verification.get("touched_paths", [])),
                safe_json_dumps(verification.get("hunk_refs", [])),
                handoff.get("export_path", ""),
                "superseded_old_experiment" if verification.get("ok") else "proof_incomplete",
                now_iso(),
                safe_json_dumps({
                    "install_commands": install_state.get("commands", []),
                    "ui_launch_check": install_state.get("ui_launch_check", {}),
                    "proof_run_results": [run_one, run_two],
                }),
                proof_run_id,
            ),
        )
        self._refresh_projections()
        return {
            "status": "ok" if verification.get("ok") else "error",
            "proof_run_id": proof_run_id,
            "fixture": fixture,
            "install_state": install_state,
            "proposal_summary": proposal_summary,
            "verification": verification,
            "handoff_packet": handoff,
        }

    def verify_proof(self, *, proof_run_id: str = "", linked_run_ids: list[str] | None = None) -> dict[str, Any]:
        proof = self.get_proof(proof_run_id=proof_run_id) if proof_run_id else {}
        run_ids = linked_run_ids or proof.get("linked_run_ids", [])
        db_path = self._installed_sidecar_root / "data" / "sidecar.db"
        touched_paths: list[dict[str, Any]] = []
        hunk_refs: list[str] = []
        journal_uids: list[str] = []
        evidence_refs: list[str] = []
        approvals: list[dict[str, Any]] = []
        if db_path.is_file():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                for run_id in run_ids:
                    for row in conn.execute(
                        "SELECT path, touch_type, status, linked_hunk_id FROM local_agent_run_touched_paths WHERE run_id = ? ORDER BY created_at ASC;",
                        (run_id,),
                    ).fetchall():
                        touched_paths.append(dict(row))
                        if row["linked_hunk_id"]:
                            hunk_refs.append(str(row["linked_hunk_id"]))
                    for row in conn.execute(
                        "SELECT grounding_kind, grounding_ref FROM local_agent_claim_grounding WHERE run_id = ? ORDER BY created_at ASC;",
                        (run_id,),
                    ).fetchall():
                        if row["grounding_kind"] == "journal":
                            journal_uids.append(str(row["grounding_ref"]))
                        if row["grounding_kind"] == "evidence":
                            evidence_refs.append(str(row["grounding_ref"]))
                request_id = str(proof.get("approval_request_id", "") or "")
                if request_id:
                    approvals = [
                        dict(row) for row in conn.execute(
                            "SELECT request_id, actor_id, requested_level, summary, status FROM approval_requests WHERE request_id = ?;",
                            (request_id,),
                        ).fetchall()
                    ]
            finally:
                conn.close()
        proof_file = self._host_root / "proof_notes.md"
        checks = {
            "installed_sidecar_exists": self._installed_sidecar_root.is_dir(),
            "proof_file_exists": proof_file.is_file(),
            "proof_file_contains_marker": proof_file.is_file() and "vendability proof" in proof_file.read_text(encoding="utf-8").lower(),
            "linked_runs_present": bool(run_ids),
            "touched_paths_present": bool(touched_paths),
            "approval_record_present": bool(approvals),
        }
        return {
            "ok": all(checks.values()),
            "checks": checks,
            "run_ids": run_ids,
            "approval_rows": approvals,
            "touched_paths": touched_paths,
            "hunk_refs": sorted(set(hunk_refs)),
            "journal_uids": sorted(set(journal_uids)),
            "evidence_refs": sorted(set(evidence_refs)),
            "proof_file": public_path(proof_file, self._state.sidecar_root, "."),
        }

    def get_proof(self, *, proof_run_id: str = "") -> dict[str, Any]:
        if proof_run_id:
            row = self._store.query_one(
                "SELECT * FROM installed_project_proofs WHERE proof_run_id = ?;",
                (proof_run_id,),
            )
        else:
            row = self._store.query_one(
                "SELECT * FROM installed_project_proofs ORDER BY started_at DESC LIMIT 1;"
            )
        if row is None:
            raise KeyError("no installed project proof found")
        return self._row_to_payload(row)

    def export_handoff_packet(self, *, proof_run_id: str = "") -> dict[str, Any]:
        proof = self.get_proof(proof_run_id=proof_run_id)
        self._export_root.mkdir(parents=True, exist_ok=True)
        export_path = self._export_root / f"installed_project_proof_{proof['proof_run_id']}.md"
        lines = [
            "# Installed Project Proof Handoff",
            "",
            f"- proof_run_id: `{proof['proof_run_id']}`",
            f"- fixture_id: `{proof['fixture_id']}`",
            f"- host_root: `{proof['host_root']}`",
            f"- installed_sidecar_root: `{proof['installed_sidecar_root']}`",
            f"- status: `{proof['status']}`",
            f"- supersession_status: `{proof['supersession_status']}`",
            "",
            "## Summary",
            "",
            "A fresh tiny host project received a clean `.scaffold` install, booted in the installed context,",
            "acknowledged the contract, scanned the host, submitted a governed proof-note proposal,",
            "received human approval, performed one bounded host mutation, and preserved trace/evidence/journal/projection state.",
            "",
            "## Verification",
            "",
            "```json",
            safe_json_dumps(proof.get("verification_summary", {}), indent=2),
            "```",
            "",
            "## Next",
            "",
            "T9 seals vendability baseline and supersedes the old experiment with this branch.",
        ]
        export_path.write_text("\n".join(lines), encoding="utf-8")
        self._store.execute(
            "UPDATE installed_project_proofs SET handoff_packet_ref = ? WHERE proof_run_id = ?;",
            (public_path(export_path, self._state.sidecar_root, "."), proof["proof_run_id"]),
        )
        return {
            "status": "ok",
            "proof_run_id": proof["proof_run_id"],
            "export_path": public_path(export_path, self._state.sidecar_root, "."),
        }

    def summary(self, *, limit: int = 5) -> dict[str, Any]:
        rows = self._store.query(
            "SELECT * FROM installed_project_proofs ORDER BY started_at DESC LIMIT ?;",
            (limit,),
        )
        recent_proofs = [self._row_to_payload(row) for row in rows]
        latest = recent_proofs[0] if recent_proofs else {}
        return {
            "fixture_summary": {
                "fixture_id": FIXTURE_ID,
                "fixture_version": FIXTURE_VERSION,
                "host_root": public_path(self._host_root, self._state.sidecar_root, "."),
                "installed_sidecar_root": public_path(self._installed_sidecar_root, self._state.sidecar_root, "."),
            },
            "latest_proof": latest,
            "recent_proofs": recent_proofs,
            "verification_result": latest.get("verification_summary", {}) if latest else {},
            "handoff_status": {
                "packet_ref": latest.get("handoff_packet_ref", "") if latest else "",
                "cold_team_ready": bool(latest.get("handoff_packet_ref", "")) if latest else False,
            },
            "supersession_status": {
                "status": latest.get("supersession_status", "") if latest else "",
                "baseline_achieved": latest.get("supersession_status") == "superseded_old_experiment" if latest else False,
            },
        }

    def _install_sidecar_copy(self) -> None:
        if self._installed_sidecar_root.exists():
            shutil.rmtree(self._installed_sidecar_root)
        self._installed_sidecar_root.mkdir(parents=True, exist_ok=True)
        source_root = Path(self._state.sidecar_root)
        include_files = [
            "README.md",
            "ONBOARDING.md",
            "IMPLEMENTATION_ROADMAP.md",
            "ARCHITECTURE.md",
            "DEV_LOG.md",
            "WE_ARE_HERE_NOW.md",
            "NORTHSTARS.md",
            "SOURCE_PROVENANCE.md",
            "TOOLS.md",
            "TRAINING_RUNWAY.md",
            "smoke_test.py",
        ]
        include_dirs = ["src", "contracts", "config", "training_scenarios"]
        for name in include_files:
            source = source_root / name
            if source.is_file():
                shutil.copy2(source, self._installed_sidecar_root / name)
        for name in include_dirs:
            source = source_root / name
            if source.is_dir():
                shutil.copytree(
                    source,
                    self._installed_sidecar_root / name,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.db", "*.sqlite", "*.sqlite3"),
                )
        for name in ("data", "logs", "cache", "exports", "workspaces", "snapshots"):
            (self._installed_sidecar_root / name).mkdir(parents=True, exist_ok=True)
        (self._installed_sidecar_root / ".gitignore").write_text(
            "data/\nlogs/\ncache/\nexports/\nworkspaces/\nsnapshots/\n__pycache__/\n*.pyc\n",
            encoding="utf-8",
        )

    def _run_install_state_checks(self) -> dict[str, Any]:
        commands = []
        for argv in (
            ["version"],
            ["ack-contract", "--actor", "human:proof:operator"],
            ["ack-contract", "--actor", "agent:local:proof"],
            ["scan", "--actor", "human:proof:operator"],
            ["projection", "handoff"],
            ["projection", "agent_bootstrap"],
            ["projection", "runtime_cockpit"],
            ["projection", "training_runway"],
            ["approval-list", "--all"],
            ["local-agent-status"],
            ["local-agent-run-list"],
            ["training-scenario-list"],
        ):
            commands.append({"argv": argv, "result": self._run_installed_cli(list(argv))})
        smoke = self._run_python(["smoke_test.py"])
        ui_launch_check = self._launch_ui_probe()
        return {
            "commands": commands,
            "smoke_test": smoke,
            "ui_launch_check": ui_launch_check,
        }

    def _run_installed_cli(self, argv: list[str]) -> dict[str, Any]:
        return self._run_python(["-m", "src.app", "cli", *argv])

    def _run_python(self, argv: list[str]) -> dict[str, Any]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._installed_sidecar_root) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, *argv],
            cwd=str(self._installed_sidecar_root),
            capture_output=True,
            text=True,
            timeout=240,
            env=env,
        )
        stdout = (proc.stdout or "").strip()
        payload: dict[str, Any] = {}
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = {"stdout": stdout}
        return {
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": (proc.stderr or "").strip(),
            "parsed": payload,
            **payload,
        }

    def _launch_ui_probe(self) -> dict[str, Any]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._installed_sidecar_root) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.app", "ui"],
            cwd=str(self._installed_sidecar_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        time.sleep(4)
        launched = proc.poll() is None
        if launched:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        stdout, stderr = proc.communicate(timeout=10)
        return {
            "launched": launched or proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (stdout or "").strip(),
            "stderr": (stderr or "").strip(),
        }

    def _refresh_child_projections(self) -> None:
        for name in ("handoff", "runtime_cockpit", "training_runway"):
            self._run_installed_cli(["projection", name])

    def _row_to_payload(self, row) -> dict[str, Any]:
        return {
            "proof_run_id": row["proof_run_id"],
            "fixture_id": row["fixture_id"],
            "fixture_version": row["fixture_version"],
            "host_root": row["host_root"],
            "installed_sidecar_root": row["installed_sidecar_root"],
            "status": row["status"],
            "install_state": _loads(row["install_state_json"], {}),
            "verification_summary": _loads(row["verification_summary_json"], {}),
            "proposal_summary": _loads(row["proposal_summary_json"], {}),
            "linked_run_ids": _loads(row["linked_run_ids_json"], []),
            "linked_scorecard_ids": _loads(row["linked_scorecard_ids_json"], []),
            "linked_evidence_refs": _loads(row["linked_evidence_refs_json"], []),
            "linked_journal_uids": _loads(row["linked_journal_uids_json"], []),
            "approval_request_id": row["approval_request_id"] or "",
            "approval_grant_id": row["approval_grant_id"] or "",
            "touched_paths": _loads(row["touched_paths_json"], []),
            "hunk_refs": _loads(row["hunk_refs_json"], []),
            "handoff_packet_ref": row["handoff_packet_ref"] or "",
            "supersession_status": row["supersession_status"] or "",
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "metadata": _loads(row["metadata_json"], {}),
        }

    def _refresh_projections(self) -> None:
        for name in ("installed_project_proof", "handoff", "viewport_state"):
            try:
                self._state.projections.refresh(name)
            except Exception:
                pass


def _loads(raw: str | None, default):
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return default
    return value
