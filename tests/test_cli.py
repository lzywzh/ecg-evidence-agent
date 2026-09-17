import json
from collections.abc import Callable
from pathlib import Path

from ecg_evidence_agent.cli import main
from ecg_evidence_agent.domain.models import SourceMetadata
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


def set_database(monkeypatch, path: Path) -> None:
    monkeypatch.setenv("ECG_AGENT_DB_PATH", str(path))


def test_init_db_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "cli.db"
    set_database(monkeypatch, database)
    assert main(["init-db"]) == 0
    assert main(["init-db"]) == 0
    assert SQLiteRepository(database).ping() is True


def test_import_command_persists_manifest_and_file(
    monkeypatch,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    database = tmp_path / "cli.db"
    manifest = tmp_path / "source.json"
    document = tmp_path / "terms.txt"
    set_database(monkeypatch, database)
    manifest.write_text(source_factory().model_dump_json(), encoding="utf-8")
    document.write_text("QT synthetic mapping", encoding="utf-8")
    assert main(["init-db"]) == 0
    assert (
        main(["import", "--manifest", str(manifest), "--file", str(document)])
        == 0
    )
    assert (
        SQLiteRepository(database).list_search_candidates()[0].text
        == "QT synthetic mapping"
    )


def test_seed_synthetic_is_idempotent(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    database = tmp_path / "cli.db"
    set_database(monkeypatch, database)
    assert main(["init-db"]) == 0
    assert main(["seed-synthetic"]) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert main(["seed-synthetic"]) == 0
    second = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert first["created"] is True
    assert second["created"] is False


def test_invalid_manifest_returns_exit_code_two(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    database = tmp_path / "cli.db"
    manifest = tmp_path / "bad.json"
    document = tmp_path / "terms.txt"
    set_database(monkeypatch, database)
    manifest.write_text("{}", encoding="utf-8")
    document.write_text("text", encoding="utf-8")
    assert main(["init-db"]) == 0
    assert (
        main(["import", "--manifest", str(manifest), "--file", str(document)])
        == 2
    )
    assert "validation" in capsys.readouterr().err.lower()


def test_missing_file_returns_exit_code_two(
    monkeypatch,
    tmp_path: Path,
    source_factory: Callable[..., SourceMetadata],
    capsys,
) -> None:
    database = tmp_path / "cli.db"
    manifest = tmp_path / "source.json"
    set_database(monkeypatch, database)
    manifest.write_text(source_factory().model_dump_json(), encoding="utf-8")
    assert main(["init-db"]) == 0
    assert (
        main(
            [
                "import",
                "--manifest",
                str(manifest),
                "--file",
                str(tmp_path / "missing.md"),
            ]
        )
        == 2
    )
    assert "file" in capsys.readouterr().err.lower()


def test_storage_failure_returns_exit_code_three_without_path(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    set_database(monkeypatch, tmp_path)
    assert main(["init-db"]) == 3
    error = capsys.readouterr().err
    assert "storage" in error.lower()
    assert str(tmp_path) not in error
