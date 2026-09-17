from fastapi import FastAPI, HTTPException

from ecg_evidence_agent.config import Settings, load_settings
from ecg_evidence_agent.domain.models import SearchRequest, SearchResponse
from ecg_evidence_agent.errors import StorageError
from ecg_evidence_agent.services.evidence_search import EvidenceSearchService
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


STORAGE_DETAIL = {
    "code": "storage_unavailable",
    "message": "Evidence storage is temporarily unavailable.",
}


def create_app(
    settings: Settings | None = None,
    repository: SQLiteRepository | None = None,
) -> FastAPI:
    active_settings = settings or load_settings()
    active_repository = repository or SQLiteRepository(
        active_settings.database_path,
        busy_timeout_ms=active_settings.busy_timeout_ms,
    )
    application = FastAPI(
        title="ECG Evidence Retrieval Teaching API",
        version="0.1.0",
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        try:
            if not active_repository.ping():
                raise StorageError("required tables are unavailable")
        except StorageError as exc:
            raise HTTPException(status_code=503, detail=STORAGE_DETAIL) from exc
        return {"status": "ok", "database": "ok"}

    @application.post("/v1/evidence/search", response_model=SearchResponse)
    def search_evidence(request: SearchRequest) -> SearchResponse:
        try:
            return EvidenceSearchService(active_repository).search(request)
        except StorageError as exc:
            raise HTTPException(status_code=503, detail=STORAGE_DETAIL) from exc

    return application


app = create_app()
