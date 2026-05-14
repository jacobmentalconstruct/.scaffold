"""
FILE: src/managers/training_runway_manager.py
ROLE: Teaching Sandbox + Training Runway manager.
WHAT IT DOES: Loads tracked scenario definitions, creates disposable
              sidecar-owned sandboxes, runs deterministic mocked/live
              local-agent scenario attempts, verifies outputs, scores the
              results, exports compact reviewer packets, and links the
              resulting scorecards into T7 traces, evidence, and journal rows.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.lib.common import gen_id, now_iso, public_path, safe_json_dumps


CHECK_STATUSES = ("pass", "partial", "fail", "skipped")
RUN_MODES = ("mocked", "live")


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    scenario_version: str
    scenario_hash: str
    title: str
    description: str
    category: str
    task_card: str
    allowed_tools: list[str]
    expected_artifacts: list[str]
    checks: list[dict[str, Any]]
    seed_files: dict[str, str]
    mock_variants: dict[str, dict[str, Any]]
    live_compatible: bool
    raw: dict[str, Any]


class TrainingRunwayManager:
    def __init__(self, state):
        self._state = state
        self._store = state.store
        self._blob = state.blob_store
        self._scenario_root = Path(state.sidecar_root) / "training_scenarios" / "definitions"
        self._sandbox_root = Path(state.sidecar_root) / "workspaces" / "teaching_sandbox" / "projects"
        self._export_root = Path(state.sidecar_root) / "exports" / "training_runway"

    # ------------------------------------------------------------------
    # Scenario registry
    # ------------------------------------------------------------------

    def list_scenarios(self) -> list[dict[str, Any]]:
        return [self._scenario_to_payload(s) for s in self._load_all_scenarios()]

    def get_scenario(self, scenario_id: str) -> dict[str, Any]:
        return self._scenario_to_payload(self._load_scenario(scenario_id))

    # ------------------------------------------------------------------
    # Sandbox lifecycle
    # ------------------------------------------------------------------

    def create_sandbox(self, scenario_id: str, *, reset: bool = False) -> dict[str, Any]:
        scenario = self._load_scenario(scenario_id)
        sandbox_root = self._sandbox_root / scenario.scenario_id
        if reset and sandbox_root.exists():
            shutil.rmtree(sandbox_root)
        sandbox_root.mkdir(parents=True, exist_ok=True)

        docs_root = sandbox_root / "_docs"
        docs_root.mkdir(parents=True, exist_ok=True)
        docs_root.joinpath("TASK_CARD.md").write_text(scenario.task_card, encoding="utf-8")

        contract_path = Path(self._state.sidecar_root) / "contracts" / "builder_constraint_contract.md"
        if contract_path.is_file():
            docs_root.joinpath("builder_constraint_contract.md").write_text(
                contract_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

        for rel_path, content in scenario.seed_files.items():
            target = sandbox_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        manifest = {
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.scenario_version,
            "scenario_hash": scenario.scenario_hash,
            "category": scenario.category,
            "expected_artifacts": scenario.expected_artifacts,
            "created_at": now_iso(),
            "disposable": True,
        }
        (sandbox_root / ".sandbox_manifest.json").write_text(
            safe_json_dumps(manifest, indent=2),
            encoding="utf-8",
        )
        return {
            "status": "ok",
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.scenario_version,
            "sandbox_root": public_path(sandbox_root, self._state.sidecar_root, "."),
            "task_card_path": public_path(docs_root / "TASK_CARD.md", self._state.sidecar_root, "."),
            "contract_path": public_path(docs_root / "builder_constraint_contract.md", self._state.sidecar_root, "."),
            "seed_file_count": len(scenario.seed_files),
            "reset": reset,
        }

    # ------------------------------------------------------------------
    # Scenario execution
    # ------------------------------------------------------------------

    def run_scenario(
        self,
        scenario_id: str,
        *,
        run_mode: str = "mocked",
        mock_variant: str = "good",
        model: str = "qwen3.5:9b",
        base_url: str = "http://localhost:11434",
        max_rounds: int = 6,
    ) -> dict[str, Any]:
        if run_mode not in RUN_MODES:
            raise ValueError(f"invalid run_mode: {run_mode!r}")
        scenario = self._load_scenario(scenario_id)
        sandbox_result = self.create_sandbox(scenario_id, reset=True)
        sandbox_root = (self._sandbox_root / scenario.scenario_id).resolve()
        scenario_run_id = gen_id("scenario_run_")
        actor_id = f"agent:local:training:{scenario_run_id}"
        variant_payload = scenario.mock_variants.get(mock_variant, {})
        snapshot = {
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.scenario_version,
            "scenario_hash": scenario.scenario_hash,
            "seed_hash": self._seed_hash(scenario),
            "task_card_hash": hashlib.sha256(scenario.task_card.encode("utf-8")).hexdigest(),
            "task_card_text": scenario.task_card,
            "allowed_tools": list(scenario.allowed_tools),
            "verifier_hash": self._verifier_hash(scenario),
            "run_mode": run_mode,
            "model": model if run_mode == "live" else "",
            "sandbox_root": public_path(sandbox_root, self._state.sidecar_root, "."),
            "created_at": now_iso(),
            "max_rounds": max_rounds,
            "mock_variant": mock_variant if run_mode == "mocked" else "",
        }
        started_at = now_iso()
        self._store.execute(
            """
            INSERT INTO teaching_scenario_runs(
                scenario_run_id, scenario_id, scenario_version, scenario_hash,
                run_mode, actor_id, model, sandbox_root, run_status,
                input_snapshot_json, linked_run_ids_json, scorecard_id,
                journal_entry_uid, reviewer_export_ref, started_at, ended_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, '[]', NULL, NULL, NULL, ?, NULL, ?);
            """,
            (
                scenario_run_id,
                scenario.scenario_id,
                scenario.scenario_version,
                scenario.scenario_hash,
                run_mode,
                actor_id,
                model if run_mode == "live" else "mocked-fixture",
                public_path(sandbox_root, self._state.sidecar_root, "."),
                safe_json_dumps(snapshot),
                started_at,
                safe_json_dumps({"mock_variant": mock_variant}),
            ),
        )

        from src.app import boot

        child_state = boot(sidecar_root=Path(self._state.sidecar_root), project_root=sandbox_root)
        self._ensure_training_authority(child_state, actor_id)
        prompt = scenario.task_card
        live_compatible = bool(scenario.live_compatible)
        if run_mode == "live" and not live_compatible:
            raise ValueError(f"scenario is not live-compatible: {scenario.scenario_id}")
        run_metadata = {
            "evaluation_mode": True,
            "target_domain": "project",
            "allow_host_project_write": True,
            "protected_paths": ["_docs/TASK_CARD.md", "_docs/builder_constraint_contract.md"],
            "scenario_run_id": scenario_run_id,
            "scenario_id": scenario.scenario_id,
        }
        mock_responses = list(variant_payload.get("mock_responses", [])) if run_mode == "mocked" else []
        mock_failure = str(variant_payload.get("mock_failure", "")) if run_mode == "mocked" else ""
        run_result = child_state.local_agent_runtime.run(
            prompt=prompt,
            actor_id=actor_id,
            model=model,
            base_url=base_url,
            max_rounds=max_rounds,
            allowed_tools=list(scenario.allowed_tools),
            mock_responses=mock_responses,
            mock_failure=mock_failure,
            ui_attached=False,
            run_metadata=run_metadata,
        )

        linked_run_ids = [str(run_result.get("run_id", ""))] if run_result.get("run_id") else []
        for run_id in linked_run_ids:
            self._store.execute(
                """
                INSERT INTO teaching_scenario_run_trace_links(
                    scenario_run_id, run_id, relation, created_at
                ) VALUES (?, ?, 'primary_attempt', ?);
                """,
                (scenario_run_id, run_id, now_iso()),
            )

        verification = self._verify_scenario(scenario, sandbox_root, linked_run_ids)
        scorecard = self._create_scorecard(
            scenario_run_id=scenario_run_id,
            scenario=scenario,
            run_mode=run_mode,
            verification=verification,
            linked_run_ids=linked_run_ids,
        )
        journal_entry_uid = self._create_run_journal(
            scenario_run_id=scenario_run_id,
            scenario=scenario,
            run_mode=run_mode,
            scorecard=scorecard,
            linked_run_ids=linked_run_ids,
        )
        export_payload = self._export_review_packet(
            scenario_run_id=scenario_run_id,
            scenario=scenario,
            scorecard=scorecard,
            verification=verification,
            linked_run_ids=linked_run_ids,
            journal_entry_uid=journal_entry_uid,
        )
        evidence_ids = self._attach_export_evidence(
            scenario_run_id=scenario_run_id,
            scorecard_id=scorecard["scorecard_id"],
            export_payload=export_payload,
            scenario=scenario,
        )
        scorecard["evidence_refs"] = evidence_ids
        self._store.execute(
            """
            UPDATE teaching_scorecards
            SET evidence_refs_json = ?, reviewer_export_ref = ?, journal_entry_uid = ?
            WHERE scorecard_id = ?;
            """,
            (
                safe_json_dumps(evidence_ids),
                export_payload["markdown_path"],
                journal_entry_uid,
                scorecard["scorecard_id"],
            ),
        )
        ended_at = now_iso()
        self._store.execute(
            """
            UPDATE teaching_scenario_runs
            SET linked_run_ids_json = ?, scorecard_id = ?, journal_entry_uid = ?,
                reviewer_export_ref = ?, run_status = ?, ended_at = ?, metadata_json = ?
            WHERE scenario_run_id = ?;
            """,
            (
                safe_json_dumps(linked_run_ids),
                scorecard["scorecard_id"],
                journal_entry_uid,
                export_payload["markdown_path"],
                scorecard["aggregate_result"],
                ended_at,
                safe_json_dumps({
                    "mock_variant": mock_variant,
                    "evidence_refs": evidence_ids,
                    "run_result_status": run_result.get("status", ""),
                }),
                scenario_run_id,
            ),
        )

        self._refresh_projections()
        return {
            "status": "ok",
            "scenario_run_id": scenario_run_id,
            "scenario_id": scenario.scenario_id,
            "sandbox": sandbox_result,
            "run_result": run_result,
            "scorecard": scorecard,
            "journal_entry_uid": journal_entry_uid,
            "review_export": export_payload,
            "evidence_refs": evidence_ids,
        }

    def verify_scenario_run(self, scenario_run_id: str) -> dict[str, Any]:
        row = self._store.query_one(
            "SELECT scenario_id, sandbox_root FROM teaching_scenario_runs WHERE scenario_run_id = ?;",
            (scenario_run_id,),
        )
        if not row:
            raise KeyError(f"unknown scenario_run_id: {scenario_run_id}")
        scenario = self._load_scenario(row["scenario_id"])
        sandbox_root = (Path(self._state.sidecar_root) / str(row["sandbox_root"]).replace("./", "")).resolve()
        linked_run_ids = [
            item["run_id"]
            for item in self._store.query(
                "SELECT run_id FROM teaching_scenario_run_trace_links WHERE scenario_run_id = ? ORDER BY created_at ASC;",
                (scenario_run_id,),
            )
        ]
        return self._verify_scenario(scenario, sandbox_root, linked_run_ids)

    def get_scorecard(self, *, scorecard_id: str = "", scenario_run_id: str = "") -> dict[str, Any]:
        if not scorecard_id:
            row = self._store.query_one(
                "SELECT scorecard_id FROM teaching_scorecards WHERE scenario_run_id = ? ORDER BY created_at DESC LIMIT 1;",
                (scenario_run_id,),
            )
            if not row:
                raise KeyError(f"no scorecard for scenario_run_id: {scenario_run_id}")
            scorecard_id = row["scorecard_id"]
        row = self._store.query_one("SELECT * FROM teaching_scorecards WHERE scorecard_id = ?;", (scorecard_id,))
        if not row:
            raise KeyError(f"unknown scorecard_id: {scorecard_id}")
        return self._scorecard_row_to_payload(row)

    def export_review(self, *, scenario_run_id: str) -> dict[str, Any]:
        row = self._store.query_one(
            """
            SELECT sr.*, sc.scorecard_id
            FROM teaching_scenario_runs sr
            LEFT JOIN teaching_scorecards sc ON sc.scenario_run_id = sr.scenario_run_id
            WHERE sr.scenario_run_id = ?;
            """,
            (scenario_run_id,),
        )
        if not row:
            raise KeyError(f"unknown scenario_run_id: {scenario_run_id}")
        scenario = self._load_scenario(row["scenario_id"])
        scorecard = self.get_scorecard(scorecard_id=row["scorecard_id"] or "", scenario_run_id=scenario_run_id)
        verification = self.verify_scenario_run(scenario_run_id)
        linked_run_ids = _loads(row["linked_run_ids_json"], [])
        packet = self._export_review_packet(
            scenario_run_id=scenario_run_id,
            scenario=scenario,
            scorecard=scorecard,
            verification=verification,
            linked_run_ids=linked_run_ids,
            journal_entry_uid=row["journal_entry_uid"] or "",
        )
        self._store.execute(
            "UPDATE teaching_scenario_runs SET reviewer_export_ref = ? WHERE scenario_run_id = ?;",
            (packet["markdown_path"], scenario_run_id),
        )
        self._store.execute(
            "UPDATE teaching_scorecards SET reviewer_export_ref = ? WHERE scenario_run_id = ?;",
            (packet["markdown_path"], scenario_run_id),
        )
        self._refresh_projections()
        return packet

    def compare_runs(self, scenario_run_ids: list[str]) -> dict[str, Any]:
        rows = []
        for scenario_run_id in scenario_run_ids:
            try:
                scorecard = self.get_scorecard(scenario_run_id=scenario_run_id)
            except Exception:
                continue
            rows.append({
                "scenario_run_id": scenario_run_id,
                "scenario_id": scorecard.get("scenario_id", ""),
                "aggregate_result": scorecard.get("aggregate_result", ""),
                "total_score": scorecard.get("total_score", 0),
                "failure_classes": scorecard.get("failure_classes", []),
            })
        return {"status": "ok", "runs": rows}

    def summary(self, *, limit: int = 8) -> dict[str, Any]:
        scenarios = self.list_scenarios()
        recent_rows = self._store.query(
            """
            SELECT sr.scenario_run_id, sr.scenario_id, sr.run_mode, sr.model, sr.run_status,
                   sr.started_at, sr.ended_at, sr.reviewer_export_ref,
                   sc.aggregate_result, sc.total_score, sc.failure_classes_json
            FROM teaching_scenario_runs sr
            LEFT JOIN teaching_scorecards sc ON sc.scenario_run_id = sr.scenario_run_id
            ORDER BY sr.started_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        recent_runs = []
        pass_count = 0
        fail_count = 0
        for row in recent_rows:
            payload = {
                "scenario_run_id": row["scenario_run_id"],
                "scenario_id": row["scenario_id"],
                "run_mode": row["run_mode"],
                "model": row["model"],
                "run_status": row["run_status"],
                "aggregate_result": row["aggregate_result"] or "",
                "total_score": int(row["total_score"] or 0),
                "failure_classes": _loads(row["failure_classes_json"], []),
                "reviewer_export_ref": row["reviewer_export_ref"] or "",
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
            }
            recent_runs.append(payload)
            if payload["aggregate_result"] == "pass":
                pass_count += 1
            elif payload["aggregate_result"] == "fail":
                fail_count += 1
        live_row = self._store.query_one(
            """
            SELECT sr.scenario_run_id, sr.scenario_id, sr.model, sr.started_at,
                   sc.aggregate_result, sc.total_score, sr.reviewer_export_ref
            FROM teaching_scenario_runs sr
            LEFT JOIN teaching_scorecards sc ON sc.scenario_run_id = sr.scenario_run_id
            WHERE sr.run_mode = 'live'
            ORDER BY sr.started_at DESC
            LIMIT 1;
            """
        )
        return {
            "scenario_inventory": scenarios,
            "recent_runs": recent_runs,
            "recent_scorecards": [self.get_scorecard(scorecard_id=row["scorecard_id"]) for row in self._store.query(
                "SELECT scorecard_id FROM teaching_scorecards ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            ) if row["scorecard_id"]],
            "pass_fail_counts": {"pass": pass_count, "fail": fail_count},
            "latest_live_proof": dict(live_row) if live_row else {},
            "reviewer_export_handles": [
                row["reviewer_export_ref"]
                for row in recent_rows
                if row["reviewer_export_ref"]
            ][:5],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_all_scenarios(self) -> list[ScenarioDefinition]:
        scenarios: list[ScenarioDefinition] = []
        for path in sorted(self._scenario_root.glob("*.json")):
            scenarios.append(self._parse_scenario(path))
        return scenarios

    def _load_scenario(self, scenario_id: str) -> ScenarioDefinition:
        path = self._scenario_root / f"{scenario_id}.json"
        if not path.is_file():
            raise KeyError(f"unknown scenario: {scenario_id}")
        return self._parse_scenario(path)

    def _parse_scenario(self, path: Path) -> ScenarioDefinition:
        raw = json.loads(path.read_text(encoding="utf-8"))
        normalized = safe_json_dumps(raw, indent=2)
        scenario_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return ScenarioDefinition(
            scenario_id=str(raw["scenario_id"]),
            scenario_version=str(raw.get("scenario_version", "1")),
            scenario_hash=scenario_hash,
            title=str(raw.get("title", raw["scenario_id"])),
            description=str(raw.get("description", "")),
            category=str(raw.get("category", "training")),
            task_card=str(raw.get("task_card", "")),
            allowed_tools=[str(item) for item in raw.get("allowed_tools", [])],
            expected_artifacts=[str(item) for item in raw.get("expected_artifacts", [])],
            checks=list(raw.get("checks", [])),
            seed_files={str(k): str(v) for k, v in (raw.get("seed_files") or {}).items()},
            mock_variants=dict(raw.get("mock_variants", {})),
            live_compatible=bool(raw.get("live_compatible", True)),
            raw=raw,
        )

    def _scenario_to_payload(self, scenario: ScenarioDefinition) -> dict[str, Any]:
        return {
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.scenario_version,
            "scenario_hash": scenario.scenario_hash,
            "title": scenario.title,
            "description": scenario.description,
            "category": scenario.category,
            "allowed_tools": list(scenario.allowed_tools),
            "expected_artifacts": list(scenario.expected_artifacts),
            "check_count": len(scenario.checks),
            "live_compatible": scenario.live_compatible,
        }

    def _ensure_training_authority(self, child_state, actor_id: str) -> None:
        row = child_state.store.query_one(
            "SELECT actor_id FROM authorities WHERE actor_id = ?;",
            (actor_id,),
        )
        if row:
            child_state.store.execute(
                """
                UPDATE authorities
                SET base_level = 'Apply', granted_by = 'system:training_runway', effective_from = ?
                WHERE actor_id = ?;
                """,
                (now_iso(), actor_id),
            )
            return
        child_state.store.execute(
            """
            INSERT INTO authorities(actor_id, base_level, granted_by, effective_from, effective_until)
            VALUES (?, 'Apply', 'system:training_runway', ?, NULL);
            """,
            (actor_id, now_iso()),
        )

    def _verify_scenario(self, scenario: ScenarioDefinition, sandbox_root: Path, linked_run_ids: list[str]) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        for check in scenario.checks:
            checks.append(self._run_check(check, sandbox_root))
        run_id = linked_run_ids[0] if linked_run_ids else ""
        run = self._state.run_trace_manager.get_run(run_id) if run_id and getattr(self._state, "run_trace_manager", None) else None
        touched_paths = self._state.run_trace_manager.get_run_touched_paths(run_id) if run_id and getattr(self._state, "run_trace_manager", None) else []
        grounding = self._state.run_trace_manager.get_run_grounding(run_id) if run_id and getattr(self._state, "run_trace_manager", None) else []
        tool_events = self._state.run_trace_manager.get_run_events(run_id, limit=200) if run_id and getattr(self._state, "run_trace_manager", None) else []
        task_card_read = any(str(item.get("path", "")) == "_docs/TASK_CARD.md" and item.get("touch_type") == "read" for item in touched_paths)
        summary = {
            "checks": checks,
            "run_status": run.status if run else "",
            "recovery_class": run.recovery_class if run else "",
            "touched_paths": touched_paths,
            "grounding": grounding,
            "tool_events": tool_events,
            "task_card_read": task_card_read,
        }
        return summary

    def _run_check(self, check: dict[str, Any], sandbox_root: Path) -> dict[str, Any]:
        check_id = str(check.get("check_id", gen_id("check_")))
        check_name = str(check.get("check_name", check_id))
        weight = int(check.get("weight", 0))
        points_possible = int(check.get("points_possible", weight or 10))
        points_awarded = 0
        status = "fail"
        message = ""
        artifact_ref = ""
        rel_path = str(check.get("path", ""))
        target = (sandbox_root / rel_path).resolve() if rel_path else sandbox_root
        kind = str(check.get("type", "file_exists"))
        if kind == "file_exists":
            ok = target.is_file()
            status = "pass" if ok else "fail"
            points_awarded = points_possible if ok else 0
            message = "file exists" if ok else "file missing"
            artifact_ref = rel_path
        elif kind == "contains_all":
            if target.is_file():
                text = target.read_text(encoding="utf-8")
                needles = [str(item) for item in check.get("contains", [])]
                missing = [item for item in needles if item not in text]
                ok = not missing
                status = "pass" if ok else "fail"
                points_awarded = points_possible if ok else 0
                message = "all required text present" if ok else f"missing tokens: {missing}"
                artifact_ref = rel_path
            else:
                message = "file missing"
        elif kind == "contains_any":
            if target.is_file():
                text = target.read_text(encoding="utf-8")
                needles = [str(item) for item in check.get("contains", [])]
                hits = [item for item in needles if item in text]
                ok = bool(hits)
                status = "pass" if ok else "fail"
                points_awarded = points_possible if ok else 0
                message = f"matched {hits}" if ok else "no required tokens present"
                artifact_ref = rel_path
            else:
                message = "file missing"
        else:
            status = "skipped"
            message = f"unsupported check type: {kind}"
        return {
            "check_id": check_id,
            "check_name": check_name,
            "status": status,
            "weight": weight,
            "points_possible": points_possible,
            "points_awarded": points_awarded,
            "message": message,
            "artifact_ref": artifact_ref,
            "dimension": str(check.get("dimension", "artifact_correctness")),
        }

    def _create_scorecard(
        self,
        *,
        scenario_run_id: str,
        scenario: ScenarioDefinition,
        run_mode: str,
        verification: dict[str, Any],
        linked_run_ids: list[str],
    ) -> dict[str, Any]:
        scorecard_id = gen_id("scorecard_")
        checks = list(verification.get("checks", []))
        total_possible = sum(int(check.get("points_possible", 0)) for check in checks)
        total_awarded = sum(int(check.get("points_awarded", 0)) for check in checks)
        dimension_scores: dict[str, dict[str, int]] = {}
        for check in checks:
            dim = str(check.get("dimension", "artifact_correctness"))
            bucket = dimension_scores.setdefault(dim, {"points_awarded": 0, "points_possible": 0})
            bucket["points_awarded"] += int(check.get("points_awarded", 0))
            bucket["points_possible"] += int(check.get("points_possible", 0))
        touched_paths = list(verification.get("touched_paths", []))
        grounding = list(verification.get("grounding", []))
        tool_events = list(verification.get("tool_events", []))
        task_card_read = bool(verification.get("task_card_read"))
        orientation_bonus = 10 if task_card_read else 0
        tool_use_bonus = 10 if any(evt.get("event_type") == "tool_call_completed" for evt in tool_events) else 0
        grounding_bonus = 10 if grounding else 0
        recovery_bonus = 10 if verification.get("run_status") in {"completed", "failed", "stopped"} else 0
        journal_bonus = 10
        for dim_name, bonus in (
            ("orientation", orientation_bonus),
            ("tool_use", tool_use_bonus),
            ("grounding", grounding_bonus),
            ("recovery_behavior", recovery_bonus),
            ("documentation_or_journal_quality", journal_bonus),
        ):
            bucket = dimension_scores.setdefault(dim_name, {"points_awarded": 0, "points_possible": 10})
            bucket["points_awarded"] += bonus
            bucket["points_possible"] = max(bucket["points_possible"], 10)
        total_score = min(100, total_awarded + orientation_bonus + tool_use_bonus + grounding_bonus + recovery_bonus + journal_bonus)
        critical_failed = any(check["status"] == "fail" and check["points_possible"] >= 15 for check in checks)
        aggregate_result = "pass" if total_score >= 80 and not critical_failed else "partial" if total_score >= 60 else "fail"
        failure_classes = []
        if verification.get("recovery_class"):
            failure_classes.append(str(verification["recovery_class"]))
        if critical_failed:
            failure_classes.append("verification_failure")
        touched_path_summary = self._summarize_touched_paths(touched_paths)
        self._store.execute(
            """
            INSERT INTO teaching_scorecards(
                scorecard_id, scenario_run_id, scenario_id, run_mode,
                aggregate_result, pass_fail_state, total_score, max_score,
                linked_run_ids_json, dimension_scores_json, checks_json,
                failure_classes_json, touched_path_summary_json, evidence_refs_json,
                journal_entry_uid, reviewer_export_ref, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 100, ?, ?, ?, ?, ?, '[]', NULL, '', ?, ?);
            """,
            (
                scorecard_id,
                scenario_run_id,
                scenario.scenario_id,
                run_mode,
                aggregate_result,
                "pass" if aggregate_result == "pass" else "fail",
                total_score,
                safe_json_dumps(linked_run_ids),
                safe_json_dumps(dimension_scores),
                safe_json_dumps(checks),
                safe_json_dumps(failure_classes),
                safe_json_dumps(touched_path_summary),
                now_iso(),
                safe_json_dumps({"scenario_version": scenario.scenario_version}),
            ),
        )
        return {
            "scorecard_id": scorecard_id,
            "scenario_run_id": scenario_run_id,
            "scenario_id": scenario.scenario_id,
            "aggregate_result": aggregate_result,
            "pass_fail_state": "pass" if aggregate_result == "pass" else "fail",
            "total_score": total_score,
            "max_score": 100,
            "linked_run_ids": linked_run_ids,
            "dimension_scores": dimension_scores,
            "checks": checks,
            "failure_classes": failure_classes,
            "touched_path_summary": touched_path_summary,
            "evidence_refs": [],
            "journal_entry_uid": "",
            "reviewer_export_ref": "",
            "run_mode": run_mode,
        }

    def _create_run_journal(
        self,
        *,
        scenario_run_id: str,
        scenario: ScenarioDefinition,
        run_mode: str,
        scorecard: dict[str, Any],
        linked_run_ids: list[str],
    ) -> str:
        body = "\n".join(
            [
                f"Scenario run: `{scenario_run_id}`",
                f"Scenario: `{scenario.scenario_id}` v`{scenario.scenario_version}`",
                f"Run mode: `{run_mode}`",
                f"Aggregate result: `{scorecard['aggregate_result']}`",
                f"Score: `{scorecard['total_score']}` / `{scorecard['max_score']}`",
                f"Linked run ids: `{', '.join(linked_run_ids)}`",
                "",
                "Checks:",
                *[
                    f"- `{check['status']}` {check['check_name']}: {check['message']}"
                    for check in scorecard["checks"]
                ],
            ]
        )
        return self._state.journal_manager.create_direct(
            kind="log",
            title=f"T8 scenario run {scenario.scenario_id} ({run_mode})",
            body=body,
            actor_id="system:training_runway",
            importance=6,
            tags=["t8", "training_runway", scenario.scenario_id, run_mode],
            metadata={
                "scenario_run_id": scenario_run_id,
                "scenario_version": scenario.scenario_version,
                "linked_run_ids": linked_run_ids,
            },
        )

    def _export_review_packet(
        self,
        *,
        scenario_run_id: str,
        scenario: ScenarioDefinition,
        scorecard: dict[str, Any],
        verification: dict[str, Any],
        linked_run_ids: list[str],
        journal_entry_uid: str,
    ) -> dict[str, Any]:
        self._export_root.mkdir(parents=True, exist_ok=True)
        stamp = now_iso().replace(":", "").replace("-", "").replace(".", "")
        md_path = self._export_root / f"training_review_{scenario.scenario_id}_{stamp}.md"
        json_path = self._export_root / f"training_review_{scenario.scenario_id}_{stamp}.json"
        checks = scorecard["checks"]
        markdown = "\n".join(
            [
                f"# Training Review — {scenario.title}",
                "",
                f"- scenario_run_id: `{scenario_run_id}`",
                f"- scenario_id: `{scenario.scenario_id}`",
                f"- scenario_version: `{scenario.scenario_version}`",
                f"- aggregate_result: `{scorecard['aggregate_result']}`",
                f"- total_score: `{scorecard['total_score']}` / `{scorecard['max_score']}`",
                f"- linked_run_ids: `{', '.join(linked_run_ids)}`",
                f"- journal_entry_uid: `{journal_entry_uid}`",
                "",
                "## Checks",
                *[
                    f"- `{check['status']}` {check['check_name']} ({check['points_awarded']}/{check['points_possible']}): {check['message']}"
                    for check in checks
                ],
                "",
                "## Failure Classes",
                *([f"- {item}" for item in scorecard["failure_classes"]] if scorecard["failure_classes"] else ["- none"]),
            ]
        )
        payload = {
            "scenario_run_id": scenario_run_id,
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.scenario_version,
            "scorecard": scorecard,
            "verification_summary": {
                "run_status": verification.get("run_status", ""),
                "recovery_class": verification.get("recovery_class", ""),
                "task_card_read": verification.get("task_card_read", False),
                "touched_path_count": len(verification.get("touched_paths", [])),
                "grounding_count": len(verification.get("grounding", [])),
            },
            "linked_run_ids": linked_run_ids,
            "journal_entry_uid": journal_entry_uid,
        }
        md_path.write_text(markdown, encoding="utf-8")
        json_path.write_text(safe_json_dumps(payload, indent=2), encoding="utf-8")
        self._store.execute(
            """
            INSERT INTO teaching_reviewer_exports(
                export_id, scenario_run_id, scorecard_id, format, blob_ref,
                export_path, created_at, metadata_json
            ) VALUES (?, ?, ?, 'markdown', ?, ?, ?, ?);
            """,
            (
                gen_id("review_export_"),
                scenario_run_id,
                scorecard["scorecard_id"],
                self._blob.put_text(markdown, content_type="text/markdown"),
                public_path(md_path, self._state.sidecar_root, "."),
                now_iso(),
                safe_json_dumps({"json_path": public_path(json_path, self._state.sidecar_root, ".")}),
            ),
        )
        return {
            "markdown_path": public_path(md_path, self._state.sidecar_root, "."),
            "json_path": public_path(json_path, self._state.sidecar_root, "."),
        }

    def _attach_export_evidence(
        self,
        *,
        scenario_run_id: str,
        scorecard_id: str,
        export_payload: dict[str, Any],
        scenario: ScenarioDefinition,
    ) -> list[str]:
        ids: list[str] = []
        md_rel = str(export_payload["markdown_path"]).replace("./", "")
        md_abs = Path(self._state.sidecar_root) / md_rel
        if md_abs.is_file():
            body_hash = self._blob.put_text(md_abs.read_text(encoding="utf-8"), content_type="text/markdown")
            evidence_id = gen_id("evd_")
            self._store.execute(
                """
                INSERT INTO evidence(
                    evidence_id, hash, kind, summary, source_event, source_path,
                    source_line_range, attached_to_object, attached_to_type,
                    status, created_at, verified_at, actor_id
                ) VALUES (?, ?, 'tool_output', ?, NULL, ?, NULL, ?, 'scenario_run', 'attached', ?, NULL, ?);
                """,
                (
                    evidence_id,
                    body_hash,
                    f"T8 reviewer export for {scenario.scenario_id}",
                    md_rel,
                    scenario_run_id,
                    now_iso(),
                    "system:training_runway",
                ),
            )
            ids.append(evidence_id)
        return ids

    def _seed_hash(self, scenario: ScenarioDefinition) -> str:
        return hashlib.sha256(
            safe_json_dumps(scenario.seed_files, indent=2).encode("utf-8")
        ).hexdigest()

    def _verifier_hash(self, scenario: ScenarioDefinition) -> str:
        return hashlib.sha256(
            safe_json_dumps(scenario.checks, indent=2).encode("utf-8")
        ).hexdigest()

    def _summarize_touched_paths(self, touched_paths: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for row in touched_paths:
            touch_type = str(row.get("touch_type", "unknown"))
            counts[touch_type] = counts.get(touch_type, 0) + 1
        return {"counts": counts, "paths": [row.get("path", "") for row in touched_paths[:12]]}

    def _scorecard_row_to_payload(self, row) -> dict[str, Any]:
        return {
            "scorecard_id": row["scorecard_id"],
            "scenario_run_id": row["scenario_run_id"],
            "scenario_id": row["scenario_id"],
            "run_mode": row["run_mode"],
            "aggregate_result": row["aggregate_result"],
            "pass_fail_state": row["pass_fail_state"],
            "total_score": int(row["total_score"] or 0),
            "max_score": int(row["max_score"] or 0),
            "linked_run_ids": _loads(row["linked_run_ids_json"], []),
            "dimension_scores": _loads(row["dimension_scores_json"], {}),
            "checks": _loads(row["checks_json"], []),
            "failure_classes": _loads(row["failure_classes_json"], []),
            "touched_path_summary": _loads(row["touched_path_summary_json"], {}),
            "evidence_refs": _loads(row["evidence_refs_json"], []),
            "journal_entry_uid": row["journal_entry_uid"] or "",
            "reviewer_export_ref": row["reviewer_export_ref"] or "",
            "created_at": row["created_at"],
            "metadata": _loads(row["metadata_json"], {}),
        }

    def _refresh_projections(self) -> None:
        for name in ("training_runway", "viewport_state", "handoff"):
            try:
                self._state.projections.refresh(name)
            except Exception:
                continue


def _loads(text: str | None, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default
