import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from ecg_evidence_agent.config import load_settings
from ecg_evidence_agent.domain.models import SourceMetadata
from ecg_evidence_agent.errors import (
    DocumentImportError,
    SourceConflictError,
    StorageError,
)
from ecg_evidence_agent.ingestion.service import IngestionService
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ecg-evidence",
        description="Synthetic-data evidence retrieval teaching CLI",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="initialize the SQLite schema")

    import_parser = commands.add_parser("import", help="import a local evidence file")
    import_parser.add_argument("--manifest", type=Path, required=True)
    import_parser.add_argument("--file", type=Path, required=True)

    commands.add_parser(
        "seed-synthetic",
        help="import the committed non-clinical synthetic sample",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        settings = load_settings()
        repository = SQLiteRepository(
            settings.database_path,
            busy_timeout_ms=settings.busy_timeout_ms,
        )
        if arguments.command == "init-db":
            repository.initialize()
            print('{"status":"initialized"}')
            return 0

        if arguments.command == "seed-synthetic":
            project_root = Path(__file__).resolve().parents[2]
            manifest_path = project_root / "data" / "synthetic" / "source.json"
            document_path = project_root / "data" / "synthetic" / "terminology.md"
        else:
            manifest_path = arguments.manifest
            document_path = arguments.file

        source = SourceMetadata.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        result = IngestionService(repository).import_file(source, document_path)
        print(result.model_dump_json())
        return 0
    except ValidationError:
        print("validation: input does not match the source schema", file=sys.stderr)
        return 2
    except DocumentImportError as exc:
        print(f"import: {exc}", file=sys.stderr)
        return 2
    except SourceConflictError as exc:
        print(f"conflict: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("file: input could not be read", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"configuration: {exc}", file=sys.stderr)
        return 2
    except StorageError:
        print("storage: database operation failed", file=sys.stderr)
        return 3
