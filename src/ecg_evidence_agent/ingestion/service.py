from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from ecg_evidence_agent.domain.models import ImportResult, SourceMetadata
from ecg_evidence_agent.ingestion.parsers import load_and_parse
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionService:
    def __init__(
        self,
        repository: SQLiteRepository,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def import_file(self, source: SourceMetadata, path: Path) -> ImportResult:
        parsed = load_and_parse(path)
        imported_at = self._clock()
        if imported_at.tzinfo is None or imported_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        digest = sha256(parsed.raw_bytes).hexdigest()
        return self._repository.import_document(
            source=source,
            original_name=parsed.original_name,
            document_format=parsed.format,
            sha256=digest,
            chunks=parsed.chunks,
            imported_at=imported_at,
        )
