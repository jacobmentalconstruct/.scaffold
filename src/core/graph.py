"""
FILE: src/core/graph.py
ROLE: Graph — typed relations between objects, derived from events.
WHAT IT DOES: Stores (subject, predicate, object) triples with closed
              predicate set enforcement. Written only by the Router after
              event commit; read by managers and projection builders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from src.components.sqlite_store import Store
from src.lib.common import (
    RELATION_TYPES_CLOSED_SET,
    gen_relation_id,
    now_iso,
    safe_json_dumps,
)
from src.lib.logging_setup import get_logger


log = get_logger("core.graph")


class InvalidRelation(ValueError):
    """Raised when a relation type is outside the closed set."""


@dataclass(frozen=True)
class Relation:
    relation_id: str
    subject_id: str
    subject_type: str
    predicate: str
    object_id: str
    object_type: str
    metadata: dict
    emitted_by: str
    created_at: str


@dataclass(frozen=True)
class GraphStats:
    total: int
    by_predicate: dict[str, int]


class Graph:
    def __init__(self, store: Store):
        self._store = store

    # --- write ---------------------------------------------------------

    def add(
        self,
        subject_id: str,
        subject_type: str,
        predicate: str,
        object_id: str,
        object_type: str,
        emitted_by: str,
        metadata: dict | None = None,
    ) -> Relation:
        if predicate not in RELATION_TYPES_CLOSED_SET:
            raise InvalidRelation(
                f"predicate {predicate!r} not in closed relation set; "
                f"allowed: {RELATION_TYPES_CLOSED_SET}"
            )
        relation_id = gen_relation_id(subject_id, predicate, object_id, emitted_by)
        existing = self._store.query_one(
            "SELECT relation_id FROM relations WHERE relation_id = ?;",
            (relation_id,),
        )
        if existing:
            return self._fetch(relation_id)  # idempotent

        created_at = now_iso()
        meta_json = safe_json_dumps(metadata or {})
        self._store.execute(
            """
            INSERT INTO relations(
                relation_id, subject_id, subject_type, predicate,
                object_id, object_type, metadata_json, emitted_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                relation_id, subject_id, subject_type, predicate,
                object_id, object_type, meta_json, emitted_by, created_at,
            ),
        )
        log.debug(
            "relation added: (%s)-[%s]->(%s) emitted_by=%s",
            subject_id, predicate, object_id, emitted_by,
        )
        return Relation(
            relation_id=relation_id,
            subject_id=subject_id,
            subject_type=subject_type,
            predicate=predicate,
            object_id=object_id,
            object_type=object_type,
            metadata=metadata or {},
            emitted_by=emitted_by,
            created_at=created_at,
        )

    def add_from_envelope(self, envelope, default_emitted_by: str | None = None) -> list[Relation]:
        """Apply all `relation_refs` from an envelope after event commit."""
        results: list[Relation] = []
        emitted_by = default_emitted_by or envelope.event_id
        if not emitted_by:
            raise ValueError("cannot apply relations: emitted_by is empty (event not yet committed?)")
        for rel in envelope.relation_refs:
            if not isinstance(rel, dict) or "predicate" not in rel:
                continue
            results.append(
                self.add(
                    subject_id=rel.get("subject_id", envelope.object_id),
                    subject_type=rel.get("subject_type", envelope.object_type),
                    predicate=rel["predicate"],
                    object_id=rel.get("object_id", ""),
                    object_type=rel.get("object_type", ""),
                    emitted_by=emitted_by,
                    metadata=rel.get("metadata", {}),
                )
            )
        return results

    # --- read ----------------------------------------------------------

    def relations_of(self, subject_id: str, predicate: str | None = None) -> list[Relation]:
        if predicate is None:
            rows = self._store.query(
                "SELECT * FROM relations WHERE subject_id = ?;", (subject_id,)
            )
        else:
            rows = self._store.query(
                "SELECT * FROM relations WHERE subject_id = ? AND predicate = ?;",
                (subject_id, predicate),
            )
        return [self._row_to_relation(r) for r in rows]

    def relations_to(self, object_id: str, predicate: str | None = None) -> list[Relation]:
        if predicate is None:
            rows = self._store.query(
                "SELECT * FROM relations WHERE object_id = ?;", (object_id,)
            )
        else:
            rows = self._store.query(
                "SELECT * FROM relations WHERE object_id = ? AND predicate = ?;",
                (object_id, predicate),
            )
        return [self._row_to_relation(r) for r in rows]

    def find(self, predicate: str | None = None, limit: int | None = None) -> list[Relation]:
        sql = "SELECT * FROM relations"
        params: list = []
        if predicate is not None:
            sql += " WHERE predicate = ?"
            params.append(predicate)
        sql += " ORDER BY created_at ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self._store.query(sql + ";", params)
        return [self._row_to_relation(r) for r in rows]

    def stats(self) -> GraphStats:
        rows = self._store.query(
            "SELECT predicate, COUNT(*) AS n FROM relations GROUP BY predicate;"
        )
        by_pred = {r["predicate"]: int(r["n"]) for r in rows}
        return GraphStats(total=sum(by_pred.values()), by_predicate=by_pred)

    # --- internals -----------------------------------------------------

    def _fetch(self, relation_id: str) -> Relation:
        row = self._store.query_one(
            "SELECT * FROM relations WHERE relation_id = ?;", (relation_id,)
        )
        return self._row_to_relation(row)  # type: ignore[arg-type]

    @staticmethod
    def _row_to_relation(row) -> Relation:
        return Relation(
            relation_id=row["relation_id"],
            subject_id=row["subject_id"],
            subject_type=row["subject_type"],
            predicate=row["predicate"],
            object_id=row["object_id"],
            object_type=row["object_type"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            emitted_by=row["emitted_by"],
            created_at=row["created_at"],
        )
