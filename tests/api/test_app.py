from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ecg_evidence_agent.api.app import create_app
from ecg_evidence_agent.config import Settings, load_settings
from ecg_evidence_agent.domain.models import ChunkDraft, SourceMetadata
from ecg_evidence_agent.errors import StorageError
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


def seed(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    repository.import_document(
        source=source_factory(),
        original_name="terms.md",
        document_format="md",
        sha256="d" * 64,
        chunks=[
            ChunkDraft(
                ordinal=0,
                locator="heading:QTc@line:1",
                text="# QTc\nfield-qtc",
            )
        ],
        imported_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )


def test_load_settings_uses_default_database_path(monkeypatch) -> None:
    monkeypatch.delenv("ECG_AGENT_DB_PATH", raising=False)
    monkeypatch.delenv("ECG_AGENT_DB_BUSY_TIMEOUT_MS", raising=False)
    assert load_settings() == Settings(
        database_path=Path("var/ecg_evidence.db"),
        busy_timeout_ms=2000,
    )


def test_load_settings_reads_database_path_from_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    expected = tmp_path / "custom.db"
    monkeypatch.setenv("ECG_AGENT_DB_PATH", str(expected))
    monkeypatch.setenv("ECG_AGENT_DB_BUSY_TIMEOUT_MS", "1500")
    assert load_settings() == Settings(database_path=expected, busy_timeout_ms=1500)


@pytest.mark.parametrize("value", ["99", "30001", "not-an-integer"])
def test_load_settings_rejects_invalid_busy_timeout(monkeypatch, value: str) -> None:
    monkeypatch.setenv("ECG_AGENT_DB_BUSY_TIMEOUT_MS", value)
    with pytest.raises(ValueError, match="ECG_AGENT_DB_BUSY_TIMEOUT_MS"):
        load_settings()


def test_health_reports_database_ok(repository: SQLiteRepository) -> None:
    response = TestClient(create_app(repository=repository)).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_create_app_does_not_create_database(tmp_path: Path) -> None:
    database = tmp_path / "not-created.db"
    create_app(settings=Settings(database_path=database))
    assert database.exists() is False


def test_uninitialized_database_health_returns_503_without_creating_file(
    tmp_path: Path,
) -> None:
    database = tmp_path / "not-created.db"
    response = TestClient(
        create_app(repository=SQLiteRepository(database))
    ).get("/health")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "storage_unavailable"
    assert database.exists() is False


def test_search_returns_evidence_with_source_fields(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    seed(repository, source_factory)
    response = TestClient(create_app(repository=repository)).post(
        "/v1/evidence/search",
        json={"query": "QTc", "top_k": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "found"
    assert body["hits"][0]["source_key"] == "synthetic.ecg-terms.v1"
    assert body["hits"][0]["is_synthetic"] is True


def test_search_returns_insufficient_evidence(repository: SQLiteRepository) -> None:
    response = TestClient(create_app(repository=repository)).post(
        "/v1/evidence/search",
        json={"query": "unseen", "top_k": 3},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert response.json()["hits"] == []


def test_empty_query_returns_422(repository: SQLiteRepository) -> None:
    response = TestClient(create_app(repository=repository)).post(
        "/v1/evidence/search",
        json={"query": "   ", "top_k": 3},
    )
    assert response.status_code == 422


def test_out_of_range_top_k_returns_422(repository: SQLiteRepository) -> None:
    response = TestClient(create_app(repository=repository)).post(
        "/v1/evidence/search",
        json={"query": "QTc", "top_k": 21},
    )
    assert response.status_code == 422


def test_storage_failure_returns_sanitized_503(
    repository: SQLiteRepository,
    monkeypatch,
    tmp_path: Path,
) -> None:
    secret_path = str(tmp_path / "secret.db")

    def fail():
        raise StorageError(f"failed at {secret_path}: SELECT * FROM chunks")

    monkeypatch.setattr(repository, "list_search_candidates", fail)
    response = TestClient(create_app(repository=repository)).post(
        "/v1/evidence/search",
        json={"query": "QTc", "top_k": 3},
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "storage_unavailable",
            "message": "Evidence storage is temporarily unavailable.",
        }
    }
    assert secret_path not in response.text
    assert "SELECT" not in response.text
