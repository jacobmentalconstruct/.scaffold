"""
FILE: src/managers/constraint_manager.py
ROLE: Owner of the constraint registry — atomic constraint units and task
      profiles that the ContractAuthority gate consults.
WHAT IT DOES: CRUD on constraint_units + task_profiles tables. Seeds a
              minimal hand-curated constraint set from the binding contract
              on first install. Provides query API for ContractAuthority.

T1 SEED STRATEGY: hand-curated minimal constraints (~12 units, 6 profiles)
covering the load-bearing rules from the binding contract. A full
markdown-decomposition pass is a Tranche 6+ concern.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.components.blob_store import BlobStore
from src.components.sqlite_store import Store
from src.lib.common import gen_constraint_uid, now_iso, sha256_hex
from src.lib.logging_setup import get_logger
from src.schemas.contract_schema import (
    SEVERITY_LEVELS,
    TIER_LEVELS,
)


log = get_logger("managers.constraint_manager")


CONTRACT_ID = "builder_constraint"
CONTRACT_VERSION = "1.0.0"


@dataclass(frozen=True)
class ConstraintUnit:
    constraint_uid: str
    section: str
    title: str
    domain_tags: list[str]
    severity: str
    tier: str
    instruction: str
    full_text: str
    contract_id: str
    contract_version: str
    created_at: str


@dataclass(frozen=True)
class TaskProfile:
    profile_id: str
    description: str
    constraint_uids: list[str]
    created_at: str


# ---------------------------------------------------------------------------
# T1 hand-curated seed constraints. Each tuple is:
#   (section, title, domain_tags, severity, tier, instruction, full_text)
# ---------------------------------------------------------------------------

_SEED_CONSTRAINTS: tuple[tuple, ...] = (
    (
        "Pledge.1",
        "Isolation",
        ["isolation", "boundary"],
        "HARD_BLOCK",
        "gate",
        "No external runtime dependencies beyond Python stdlib + explicitly declared packages.",
        "Pledge 1: Isolation. Keep the sidecar package portable and self-contained.",
    ),
    (
        "Pledge.2",
        "Single Store",
        ["storage", "boundary"],
        "HARD_BLOCK",
        "gate",
        "All DB access flows through src/components/sqlite_store.py and src/managers/journal_manager.py. Nothing else opens the DB.",
        "Pledge 2: Single Store. Exactly one code path to the database.",
    ),
    (
        "Pledge.3",
        "Schema Stability",
        ["storage", "schema"],
        "PUSHBACK",
        "letter",
        "Prefer additive schema changes (new columns/tables) over destructive ones; destructive changes require a migration plan.",
        "Pledge 3: Schema Stability. The SQLite schema is explicit and versioned.",
    ),
    (
        "Pledge.4",
        "CAS Integrity",
        ["storage", "evidence"],
        "HARD_BLOCK",
        "letter",
        "Large or content-addressed payloads flow through blob_store via SHA-256 hashes.",
        "Pledge 4: CAS Integrity. The body_hash is the additive integrity layer.",
    ),
    (
        "Pledge.6",
        "Spine Discipline",
        ["spine", "routing"],
        "HARD_BLOCK",
        "gate",
        "Every state mutation flows: Interface -> Envelope -> Router -> ContractCheck -> Orchestrator -> Manager -> Event -> derived views. No sideways calls.",
        "Pledge 6: Spine Discipline. The envelope is the only currency.",
    ),
    (
        "Pledge.7",
        "Envelope Lightness",
        ["spine", "envelope"],
        "HARD_BLOCK",
        "letter",
        "Envelopes route and identify; heavy content (diffs, vectors, ASTs, screenshots, large bodies) lives in blob_store and is referenced via payload_ref or evidence_refs.",
        "Pledge 7: Envelope Lightness. Envelopes do not embed large bodies.",
    ),
    (
        "1.1",
        "Sandbox Root",
        ["boundary", "filesystem"],
        "HARD_BLOCK",
        "gate",
        "Read-only from .parts/. Writes only inside .scaffold/ subtree.",
        "Sandbox root rule: builder may read .parts/ but writes only inside the active project folder.",
    ),
    (
        "1.2",
        "External boundary restrictions",
        ["boundary", "imports"],
        "HARD_BLOCK",
        "gate",
        "No runtime imports from outside .scaffold/. The host project's application code never imports from .scaffold/.",
        "Section 1.2: External boundary restrictions.",
    ),
    (
        "1.4",
        "Sidecar storage discipline",
        ["boundary", "filesystem", "authority"],
        "HARD_BLOCK",
        "gate",
        "All sidecar runtime data lives under .scaffold/<folder>/. No writes to host project tree without Apply authority + recorded human approval.",
        "Section 1.4: Sidecar storage discipline.",
    ),
    (
        "2.1",
        "Logging instead of print",
        ["logging", "code-quality"],
        "PUSHBACK",
        "letter",
        "Use logging infrastructure (src/lib/logging_setup.py). print() is prohibited in application core.",
        "Section 2.1: Logging instead of print rule.",
    ),
    (
        "2.2",
        "Graceful failure",
        ["error-handling", "code-quality"],
        "ADVISORY",
        "spirit",
        "Failures handled via controlled boundaries, meaningful logs, safe shutdown paths.",
        "Section 2.2: Graceful failure rule.",
    ),
    (
        "4.relations",
        "Closed relation set",
        ["graph", "schema"],
        "HARD_BLOCK",
        "letter",
        "Only relation predicates from the closed set may be added: belongs_to, observes, derives_from, supersedes, cites, modifies, validates, requires, emitted_by, approved_by, failed_due_to, produces.",
        "Prohibited: creating relations of type related_to or any type not in the closed set.",
    ),
)


# Profile → list of (section,title) tuples. Resolved to UIDs after seed.
_SEED_PROFILES: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "core_implementation",
        "Building spine, managers, components, schemas.",
        (
            ("Pledge.1", "Isolation"),
            ("Pledge.2", "Single Store"),
            ("Pledge.3", "Schema Stability"),
            ("Pledge.4", "CAS Integrity"),
            ("Pledge.6", "Spine Discipline"),
            ("Pledge.7", "Envelope Lightness"),
            ("1.4", "Sidecar storage discipline"),
            ("2.1", "Logging instead of print"),
            ("2.2", "Graceful failure"),
            ("4.relations", "Closed relation set"),
        ),
    ),
    (
        "ui_implementation",
        "Building Tkinter UI panels.",
        (
            ("Pledge.6", "Spine Discipline"),
            ("Pledge.7", "Envelope Lightness"),
            ("2.1", "Logging instead of print"),
            ("2.2", "Graceful failure"),
        ),
    ),
    (
        "tool_creation",
        "Authoring tools under src/tools/.",
        (
            ("Pledge.6", "Spine Discipline"),
            ("Pledge.7", "Envelope Lightness"),
            ("Pledge.2", "Single Store"),
            ("1.4", "Sidecar storage discipline"),
            ("2.1", "Logging instead of print"),
        ),
    ),
    (
        "scaffolding",
        "Scaffold operations (workspace or host project).",
        (
            ("1.1", "Sandbox Root"),
            ("1.2", "External boundary restrictions"),
            ("1.4", "Sidecar storage discipline"),
            ("Pledge.6", "Spine Discipline"),
        ),
    ),
    (
        "documentation",
        "Authoring docs and journal entries.",
        (
            ("2.1", "Logging instead of print"),
            ("2.2", "Graceful failure"),
        ),
    ),
    (
        "cleanup",
        "Removing or archiving content.",
        (
            ("Pledge.3", "Schema Stability"),
            ("1.4", "Sidecar storage discipline"),
        ),
    ),
)


# Mapping from operation_intent to relevant constraint sections.
# T1 baseline; expanded as more intents land.
_INTENT_CONSTRAINT_SECTIONS: dict[str, tuple[str, ...]] = {
    "acknowledge_contract": ("Pledge.6",),
    "install": ("Pledge.6", "1.4"),
    "scan": ("1.1", "Pledge.6"),
    "create_journal_entry": ("Pledge.6", "Pledge.2", "2.1"),
    "attach_evidence": ("Pledge.4", "Pledge.6"),
    "register_tool": ("Pledge.6", "Pledge.2"),
    "register_constraint": ("Pledge.3",),
    "register_profile": ("Pledge.3",),
    "seed_constraints": ("Pledge.6",),
}


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ConstraintManager:
    def __init__(self, store: Store, blob_store: BlobStore):
        self._store = store
        self._blob = blob_store

    # --- read API consumed by ContractAuthority -----------------------

    def query_for_intent(self, operation_intent: str) -> list[ConstraintUnit]:
        sections = _INTENT_CONSTRAINT_SECTIONS.get(operation_intent, ())
        if not sections:
            # Fallback: return all gate-tier HARD_BLOCK constraints.
            return self.query_by_severity_tier("HARD_BLOCK", "gate")
        results: list[ConstraintUnit] = []
        for section in sections:
            rows = self._store.query(
                "SELECT * FROM constraint_units WHERE section = ?;", (section,)
            )
            for r in rows:
                results.append(self._row_to_unit(r))
        return results

    def query_for_profile(self, profile_id: str) -> list[ConstraintUnit]:
        profile = self.get_profile(profile_id)
        if profile is None:
            return []
        if not profile.constraint_uids:
            return []
        placeholders = ",".join(["?"] * len(profile.constraint_uids))
        rows = self._store.query(
            f"SELECT * FROM constraint_units WHERE constraint_uid IN ({placeholders});",
            profile.constraint_uids,
        )
        return [self._row_to_unit(r) for r in rows]

    def query_by_severity(self, severity: str) -> list[ConstraintUnit]:
        if severity not in SEVERITY_LEVELS:
            raise ValueError(f"invalid severity: {severity!r}")
        rows = self._store.query(
            "SELECT * FROM constraint_units WHERE severity = ?;", (severity,)
        )
        return [self._row_to_unit(r) for r in rows]

    def query_by_severity_tier(self, severity: str, tier: str) -> list[ConstraintUnit]:
        if severity not in SEVERITY_LEVELS or tier not in TIER_LEVELS:
            raise ValueError(f"invalid severity/tier: {severity!r}/{tier!r}")
        rows = self._store.query(
            "SELECT * FROM constraint_units WHERE severity = ? AND tier = ?;",
            (severity, tier),
        )
        return [self._row_to_unit(r) for r in rows]

    def get(self, constraint_uid: str) -> ConstraintUnit | None:
        row = self._store.query_one(
            "SELECT * FROM constraint_units WHERE constraint_uid = ?;",
            (constraint_uid,),
        )
        return self._row_to_unit(row) if row else None

    def get_profile(self, profile_id: str) -> TaskProfile | None:
        row = self._store.query_one(
            "SELECT * FROM task_profiles WHERE profile_id = ?;", (profile_id,)
        )
        if row is None:
            return None
        return TaskProfile(
            profile_id=row["profile_id"],
            description=row["description"] or "",
            constraint_uids=json.loads(row["constraint_uids"]) if row["constraint_uids"] else [],
            created_at=row["created_at"],
        )

    def list_profiles(self) -> list[TaskProfile]:
        rows = self._store.query("SELECT * FROM task_profiles ORDER BY profile_id;")
        return [
            TaskProfile(
                profile_id=r["profile_id"],
                description=r["description"] or "",
                constraint_uids=json.loads(r["constraint_uids"]) if r["constraint_uids"] else [],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def stats(self) -> dict:
        total = self._store.query_one("SELECT COUNT(*) AS n FROM constraint_units;")
        rows = self._store.query(
            "SELECT severity, COUNT(*) AS n FROM constraint_units GROUP BY severity;"
        )
        by_severity = {r["severity"]: int(r["n"]) for r in rows}
        rows = self._store.query(
            "SELECT tier, COUNT(*) AS n FROM constraint_units GROUP BY tier;"
        )
        by_tier = {r["tier"]: int(r["n"]) for r in rows}
        profile_count = self._store.query_one("SELECT COUNT(*) AS n FROM task_profiles;")
        return {
            "constraint_count": int(total["n"]) if total else 0,
            "by_severity": by_severity,
            "by_tier": by_tier,
            "profile_count": int(profile_count["n"]) if profile_count else 0,
        }

    # --- write API ----------------------------------------------------

    def register_constraint(self, unit: ConstraintUnit) -> None:
        self._store.execute(
            """
            INSERT INTO constraint_units(
                constraint_uid, section, title, domain_tags, severity, tier,
                instruction, full_text, contract_id, contract_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(constraint_uid) DO UPDATE SET
                section=excluded.section,
                title=excluded.title,
                domain_tags=excluded.domain_tags,
                severity=excluded.severity,
                tier=excluded.tier,
                instruction=excluded.instruction,
                full_text=excluded.full_text,
                contract_id=excluded.contract_id,
                contract_version=excluded.contract_version;
            """,
            (
                unit.constraint_uid,
                unit.section,
                unit.title,
                json.dumps(unit.domain_tags),
                unit.severity,
                unit.tier,
                unit.instruction,
                unit.full_text,
                unit.contract_id,
                unit.contract_version,
                unit.created_at,
            ),
        )

    def register_profile(self, profile: TaskProfile) -> None:
        self._store.execute(
            """
            INSERT INTO task_profiles(profile_id, description, constraint_uids, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                description=excluded.description,
                constraint_uids=excluded.constraint_uids;
            """,
            (
                profile.profile_id,
                profile.description,
                json.dumps(profile.constraint_uids),
                profile.created_at,
            ),
        )

    def seed_from_contract(self, contract_path: Path) -> dict:
        """Seed constraints + profiles. Idempotent.

        Reads the contract markdown to compute its hash and store it; the
        actual constraint decomposition is hand-curated for T1 (see
        _SEED_CONSTRAINTS at module level).
        """
        contract_path = Path(contract_path)
        if not contract_path.is_file():
            raise FileNotFoundError(f"contract not found: {contract_path}")

        contract_bytes = contract_path.read_bytes()
        text_hash = sha256_hex(contract_bytes)
        text_blob_ref = self._blob.put(contract_bytes, content_type="text/markdown")

        # Upsert contract record.
        introduced_at = now_iso()
        self._store.execute(
            """
            INSERT INTO contracts(
                contract_id, version, text_hash, text_blob_ref,
                section_index_json, introduced_at, superseded_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(contract_id) DO UPDATE SET
                version=excluded.version,
                text_hash=excluded.text_hash,
                text_blob_ref=excluded.text_blob_ref;
            """,
            (
                CONTRACT_ID,
                CONTRACT_VERSION,
                text_hash,
                text_blob_ref,
                None,
                introduced_at,
            ),
        )

        # Seed constraint units.
        section_to_uid: dict[tuple[str, str], str] = {}
        with self._store.transaction():
            now = now_iso()
            for (section, title, tags, severity, tier, instruction, full_text) in _SEED_CONSTRAINTS:
                uid = gen_constraint_uid(section, title)
                section_to_uid[(section, title)] = uid
                self.register_constraint(ConstraintUnit(
                    constraint_uid=uid,
                    section=section,
                    title=title,
                    domain_tags=list(tags),
                    severity=severity,
                    tier=tier,
                    instruction=instruction,
                    full_text=full_text,
                    contract_id=CONTRACT_ID,
                    contract_version=CONTRACT_VERSION,
                    created_at=now,
                ))

            # Seed task profiles.
            for (profile_id, description, member_keys) in _SEED_PROFILES:
                uids = [section_to_uid[k] for k in member_keys if k in section_to_uid]
                self.register_profile(TaskProfile(
                    profile_id=profile_id,
                    description=description,
                    constraint_uids=uids,
                    created_at=now,
                ))

        log.info("seeded constraint registry: %s constraints, %s profiles",
                 len(_SEED_CONSTRAINTS), len(_SEED_PROFILES))

        return {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "text_hash": text_hash,
            "text_blob_ref": text_blob_ref,
            "constraint_count": len(_SEED_CONSTRAINTS),
            "profile_count": len(_SEED_PROFILES),
        }

    # --- internals -----------------------------------------------------

    @staticmethod
    def _row_to_unit(row) -> ConstraintUnit:
        return ConstraintUnit(
            constraint_uid=row["constraint_uid"],
            section=row["section"] or "",
            title=row["title"],
            domain_tags=json.loads(row["domain_tags"]) if row["domain_tags"] else [],
            severity=row["severity"],
            tier=row["tier"],
            instruction=row["instruction"],
            full_text=row["full_text"] or "",
            contract_id=row["contract_id"],
            contract_version=row["contract_version"],
            created_at=row["created_at"],
        )
