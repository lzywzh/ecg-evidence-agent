from ecg_evidence_agent.domain.models import (
    SearchRequest,
    SearchResponse,
    SearchStatus,
)
from ecg_evidence_agent.retrieval.keyword import rank_candidates
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


class EvidenceSearchService:
    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def search(self, request: SearchRequest) -> SearchResponse:
        candidates = self._repository.list_search_candidates()
        hits = rank_candidates(request.query, candidates, request.top_k)
        status = (
            SearchStatus.FOUND if hits else SearchStatus.INSUFFICIENT_EVIDENCE
        )
        return SearchResponse(query=request.query, status=status, hits=hits)
