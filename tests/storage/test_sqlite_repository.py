import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ecg_evidence_agent.domain.models import ChunkDraft, SourceMetadata
from ecg_evidence_agent.errors import SourceConflictError, StorageError
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


NOW = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)


def import_one(
    repository: SQLiteRepository,
    source: SourceMetadata,
    *,
    digest: str = "a" * 64,
    chunks: list[ChunkDraft] | None = None,
):
    return repository.import_document(
        source=source,
        original_name="terms.md",
        document_format="md",
        sha256=digest,
        chunks=chunks
        or [ChunkDraft(ordinal=0, locator="heading:QT@line:1", text="# QT\nfield-qt")],
        imported_at=NOW,
    )


def test_data_survives_repository_reopen(
    repository: SQLiteRepository,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    import_one(repository, source_factory())
    reopened = SQLiteRepository(tmp_path / "test.db")
    candidates = reopened.list_search_candidates()
    assert candidates[0].text == "# QT\nfield-qt"
    assert candidates[0].source.source_key == "synthetic.ecg-terms.v1"


def test_duplicate_document_returns_created_false(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    first = import_one(repository, source_factory())
    second = import_one(repository, source_factory())
    assert first.created is True
    assert second == first.model_copy(update={"created": False})


def test_conflicting_source_metadata_is_rejected(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    import_one(repository, source_factory())
    with pytest.raises(SourceConflictError, match="source_key"):
        import_one(repository, source_factory(title="冲突标题"), digest="b" * 64)


def test_failed_chunk_insert_rolls_back_source_and_document(
    repository: SQLiteRepository,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    duplicate_ordinals = [
        ChunkDraft(ordinal=0, locator="a", text="first"),
        ChunkDraft(ordinal=0, locator="b", text="second"),
    ]
    with pytest.raises(StorageError):
        import_one(repository, source_factory(), chunks=duplicate_ordinals)
    with sqlite3.connect(tmp_path / "test.db") as connection:
        assert connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0


def test_sql_metacharacters_are_stored_as_data(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    source = source_factory(title="x'); DROP TABLE sources; --")
    import_one(repository, source)
    candidates = repository.list_search_candidates()
    assert candidates[0].source.title == "x'); DROP TABLE sources; --"
    assert repository.ping() is True


def test_list_search_candidates_returns_source_metadata(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    import_one(repository, source_factory())
    candidate = repository.list_search_candidates()[0]
    assert candidate.locator == "heading:QT@line:1"
    assert candidate.source.institution == "合成数据实验室"


def test_ping_returns_true_for_initialized_database(repository: SQLiteRepository) -> None:
    assert repository.ping() is True
