"""
FILE: src/components/blob_store.py
ROLE: Content-addressed storage layer (CAS). All large content flows here.
WHAT IT DOES: SHA-256-keyed put/get/exists/iter/verify. Text and JSON helpers.
              Used by every manager that stores body content.
"""

from __future__ import annotations

import json
from typing import Iterable

from src.components.sqlite_store import Store
from src.lib.common import now_iso, sha256_hex
from src.lib.logging_setup import get_logger


log = get_logger("components.blob_store")


class BlobNotFound(KeyError):
    """Raised when a blob hash is requested but not stored."""


class BlobStore:
    def __init__(self, store: Store):
        self._store = store

    # --- write ---------------------------------------------------------

    def put(self, content: bytes, content_type: str = "application/octet-stream") -> str:
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError(f"content must be bytes, got {type(content).__name__}")
        hash_hex = sha256_hex(bytes(content))
        existing = self._store.query_one(
            "SELECT hash FROM blob_store WHERE hash = ?;", (hash_hex,)
        )
        if existing:
            return hash_hex
        self._store.execute(
            "INSERT INTO blob_store(hash, size_bytes, content_type, body, created_at) "
            "VALUES (?, ?, ?, ?, ?);",
            (hash_hex, len(content), content_type, bytes(content), now_iso()),
        )
        return hash_hex

    def put_text(self, text: str, content_type: str = "text/plain") -> str:
        return self.put(text.encode("utf-8"), content_type=content_type)

    def put_json(self, obj, content_type: str = "application/json") -> str:
        return self.put_text(json.dumps(obj, sort_keys=False), content_type=content_type)

    # --- read ----------------------------------------------------------

    def get(self, hash_hex: str) -> bytes:
        row = self._store.query_one(
            "SELECT body FROM blob_store WHERE hash = ?;", (hash_hex,)
        )
        if row is None:
            raise BlobNotFound(hash_hex)
        return bytes(row["body"])

    def get_text(self, hash_hex: str) -> str:
        return self.get(hash_hex).decode("utf-8")

    def get_json(self, hash_hex: str):
        return json.loads(self.get_text(hash_hex))

    def exists(self, hash_hex: str) -> bool:
        row = self._store.query_one(
            "SELECT 1 FROM blob_store WHERE hash = ?;", (hash_hex,)
        )
        return row is not None

    def metadata(self, hash_hex: str) -> dict:
        row = self._store.query_one(
            "SELECT hash, size_bytes, content_type, created_at FROM blob_store WHERE hash = ?;",
            (hash_hex,),
        )
        if row is None:
            raise BlobNotFound(hash_hex)
        return {
            "hash": row["hash"],
            "size_bytes": row["size_bytes"],
            "content_type": row["content_type"],
            "created_at": row["created_at"],
        }

    def iter_hashes(self) -> Iterable[str]:
        rows = self._store.query("SELECT hash FROM blob_store ORDER BY hash;")
        return [r["hash"] for r in rows]

    # --- integrity -----------------------------------------------------

    def verify(self, hash_hex: str) -> bool:
        body = self.get(hash_hex)
        return sha256_hex(body) == hash_hex

    def merkle_root(self) -> str:
        hashes = sorted(self.iter_hashes())
        if not hashes:
            return sha256_hex(b"")
        return sha256_hex("".join(hashes).encode("utf-8"))

    def count(self) -> int:
        row = self._store.query_one("SELECT COUNT(*) AS n FROM blob_store;")
        return int(row["n"]) if row else 0
