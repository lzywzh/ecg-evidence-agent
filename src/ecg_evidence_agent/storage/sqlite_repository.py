from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ecg_evidence_agent.domain.models import (
    ChunkDraft,
    ImportResult,
    SourceMetadata,
    StoredChunk,
)
from ecg_evidence_agent.errors import SourceConflictError, StorageError


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    institution TEXT NOT NULL,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    version TEXT,
    published_date TEXT,
    source_uri TEXT,
    retrieved_at TEXT NOT NULL,
    scope TEXT NOT NULL,
    usage_terms TEXT NOT NULL,
    redistributable INTEGER NOT NULL CHECK (redistributable IN (0, 1)),
    is_synthetic INTEGER NOT NULL CHECK (is_synthetic IN (0, 1))
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    original_name TEXT NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('txt', 'md', 'json')),
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (source_id, sha256)
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    locator TEXT NOT NULL,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    UNIQUE (document_id, ordinal)
);
"""

REQUIRED_TABLES = {"sources", "documents", "chunks"}
SOURCE_CONFLICT_FIELDS = (
    "institution",
    "title",
    "source_type",
    "version",
    "published_date",
    "source_uri",
    "scope",
    "usage_terms",
    "redistributable",
    "is_synthetic",
)


class SQLiteRepository:
    def __init__(self, database_path: Path, busy_timeout_ms: int = 2000) -> None:
        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                connection.executescript(SCHEMA_SQL)
                connection.commit()
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("database initialization failed") from exc

    def ping(self) -> bool:
        if not self._database_path.is_file():
            return False
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = ?",
                    ("table",),
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("database operation failed") from exc
        return REQUIRED_TABLES.issubset({row["name"] for row in rows})

    def import_document(
        self,
        *,
        source: SourceMetadata,
        original_name: str,
        document_format: Literal["txt", "md", "json"],
        sha256: str,
        chunks: list[ChunkDraft],
        imported_at: datetime,
    ) -> ImportResult:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN")
                source_id = self._get_or_insert_source(connection, source)
                existing = connection.execute(
                    "SELECT id FROM documents WHERE source_id = ? AND sha256 = ?",
                    (source_id, sha256),
                ).fetchone()
                if existing is not None:
                    document_id = int(existing["id"])
                    count_row = connection.execute(
                        "SELECT count(*) AS count FROM chunks WHERE document_id = ?",
                        (document_id,),
                    ).fetchone()
                    connection.commit()
                    return ImportResult(
                        source_id=source_id,
                        document_id=document_id,
                        chunks_imported=int(count_row["count"]),
                        created=False,
                    )

                cursor = connection.execute(
                    """
                    INSERT INTO documents (source_id, original_name, format, sha256, imported_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        original_name,
                        document_format,
                        sha256,
                        imported_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
                document_id = int(cursor.lastrowid)
                for chunk in chunks:
                    text_sha256 = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
                    connection.execute(
                        """
                        INSERT INTO chunks (document_id, ordinal, locator, text, text_sha256)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (document_id, chunk.ordinal, chunk.locator, chunk.text, text_sha256),
                    )
                connection.commit()
                return ImportResult(
                    source_id=source_id,
                    document_id=document_id,
                    chunks_imported=len(chunks),
                    created=True,
                )
        except SourceConflictError:
            raise
        except sqlite3.Error as exc:
            raise StorageError("database operation failed") from exc

    def _get_or_insert_source(
        self,
        connection: sqlite3.Connection,
        source: SourceMetadata,
    ) -> int:
        existing = connection.execute(
            "SELECT * FROM sources WHERE source_key = ?",
            (source.source_key,),
        ).fetchone()
        if existing is not None:
            self._raise_on_source_conflict(existing, source)
            return int(existing["id"])

        cursor = connection.execute(
            """
            INSERT INTO sources (
                source_key, institution, title, source_type, version,
                published_date, source_uri, retrieved_at, scope, usage_terms,
                redistributable, is_synthetic
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.source_key,
                source.institution,
                source.title,
                source.source_type.value,
                source.version,
                source.published_date.isoformat() if source.published_date else None,
                source.source_uri,
                source.retrieved_at.isoformat(),
                source.scope,
                source.usage_terms,
                int(source.redistributable),
                int(source.is_synthetic),
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _raise_on_source_conflict(
        existing: sqlite3.Row,
        source: SourceMetadata,
    ) -> None:
        normalized = {
            "institution": source.institution,
            "title": source.title,
            "source_type": source.source_type.value,
            "version": source.version,
            "published_date": (
                source.published_date.isoformat() if source.published_date else None
            ),
            "source_uri": source.source_uri,
            "scope": source.scope,
            "usage_terms": source.usage_terms,
            "redistributable": int(source.redistributable),
            "is_synthetic": int(source.is_synthetic),
        }
        conflicting = [
            field for field in SOURCE_CONFLICT_FIELDS if existing[field] != normalized[field]
        ]
        if conflicting:
            fields = ", ".join(conflicting)
            raise SourceConflictError(
                f"source_key {source.source_key!r} conflicts on fields: {fields}"
            )

    def list_search_candidates(self) -> list[StoredChunk]:
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT
                        c.id AS chunk_id,
                        c.document_id,
                        c.ordinal,
                        c.locator,
                        c.text,
                        s.id AS source_id,
                        s.source_key,
                        s.institution,
                        s.title,
                        s.source_type,
                        s.version,
                        s.published_date,
                        s.source_uri,
                        s.retrieved_at,
                        s.scope,
                        s.usage_terms,
                        s.redistributable,
                        s.is_synthetic
                    FROM chunks AS c
                    JOIN documents AS d ON d.id = c.document_id
                    JOIN sources AS s ON s.id = d.source_id
                    ORDER BY s.id, d.id, c.ordinal
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("database operation failed") from exc

        return [self._row_to_stored_chunk(row) for row in rows]

    @staticmethod
    def _row_to_stored_chunk(row: sqlite3.Row) -> StoredChunk:
        source = SourceMetadata.model_validate(
            {
                "source_key": row["source_key"],
                "institution": row["institution"],
                "title": row["title"],
                "source_type": row["source_type"],
                "version": row["version"],
                "published_date": row["published_date"],
                "source_uri": row["source_uri"],
                "retrieved_at": row["retrieved_at"],
                "scope": row["scope"],
                "usage_terms": row["usage_terms"],
                "redistributable": bool(row["redistributable"]),
                "is_synthetic": bool(row["is_synthetic"]),
            }
        )
        return StoredChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            ordinal=row["ordinal"],
            locator=row["locator"],
            text=row["text"],
            source_id=row["source_id"],
            source=source,
        )
