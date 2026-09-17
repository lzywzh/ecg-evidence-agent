import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ecg_evidence_agent.domain.models import SourceMetadata
from ecg_evidence_agent.errors import DocumentImportError
from ecg_evidence_agent.ingestion.service import IngestionService
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


FIXED_NOW = datetime(2026, 9, 17, 8, 30, tzinfo=timezone.utc)


def test_import_file_hashes_original_bytes_and_persists_chunks(
    repository: SQLiteRepository,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    path = tmp_path / "terms.txt"
    path.write_text("QT test mapping.\n", encoding="utf-8")
    result = IngestionService(repository, clock=lambda: FIXED_NOW).import_file(
        source_factory(), path
    )
    assert result.created is True
    assert result.chunks_imported == 1
    assert repository.list_search_candidates()[0].text == "QT test mapping."


def test_importing_same_file_twice_is_idempotent(
    repository: SQLiteRepository,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    path = tmp_path / "terms.txt"
    path.write_text("QT test mapping.\n", encoding="utf-8")
    service = IngestionService(repository, clock=lambda: FIXED_NOW)
    first = service.import_file(source_factory(), path)
    second = service.import_file(source_factory(), path)
    assert first.created is True
    assert second.created is False
    assert second.document_id == first.document_id
    assert len(repository.list_search_candidates()) == 1


def test_parser_failure_leaves_database_empty(
    repository: SQLiteRepository,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    path = tmp_path / "empty.md"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(DocumentImportError):
        IngestionService(repository, clock=lambda: FIXED_NOW).import_file(
            source_factory(), path
        )
    assert repository.list_search_candidates() == []


def test_imported_at_comes_from_injected_clock(
    repository: SQLiteRepository,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    path = tmp_path / "terms.txt"
    path.write_text("fixed time", encoding="utf-8")
    IngestionService(repository, clock=lambda: FIXED_NOW).import_file(
        source_factory(), path
    )
    with sqlite3.connect(tmp_path / "test.db") as connection:
        stored = connection.execute("SELECT imported_at FROM documents").fetchone()[0]
    assert stored == FIXED_NOW.isoformat()


def test_rejects_naive_clock_before_writing(
    repository: SQLiteRepository,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    path = tmp_path / "terms.txt"
    path.write_text("fixed time", encoding="utf-8")
    service = IngestionService(repository, clock=lambda: datetime(2026, 9, 17))
    with pytest.raises(ValueError, match="timezone-aware"):
        service.import_file(source_factory(), path)
    assert repository.list_search_candidates() == []
