from collections.abc import Callable
from datetime import datetime, timezone

from ecg_evidence_agent.domain.models import (
    ChunkDraft,
    SearchRequest,
    SearchStatus,
    SourceMetadata,
)
from ecg_evidence_agent.services.evidence_search import EvidenceSearchService
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


def seed(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    repository.import_document(
        source=source_factory(),
        original_name="terms.md",
        document_format="md",
        sha256="c" * 64,
        chunks=[
            ChunkDraft(
                ordinal=0,
                locator="heading:QTc@line:1",
                text="# QTc\nfield-qtc",
            )
        ],
        imported_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )


def test_search_returns_found_with_traceable_source(
    repository: SQLiteRepository,
    source_factory: Callable[..., SourceMetadata],
) -> None:
    seed(repository, source_factory)
    response = EvidenceSearchService(repository).search(SearchRequest(query="QTc"))
    assert response.status is SearchStatus.FOUND
    assert response.hits[0].source_key == "synthetic.ecg-terms.v1"
    assert response.hits[0].locator == "heading:QTc@line:1"


def test_search_returns_insufficient_evidence_without_hits(
    repository: SQLiteRepository,
) -> None:
    response = EvidenceSearchService(repository).search(SearchRequest(query="unseen"))
    assert response.status is SearchStatus.INSUFFICIENT_EVIDENCE
    assert response.hits == []


def test_search_preserves_validated_trimmed_query_in_response(
    repository: SQLiteRepository,
) -> None:
    response = EvidenceSearchService(repository).search(
        SearchRequest(query="  unseen  ")
    )
    assert response.query == "unseen"


def test_search_uses_keyword_v1_method(repository: SQLiteRepository) -> None:
    response = EvidenceSearchService(repository).search(SearchRequest(query="unseen"))
    assert response.retrieval_method == "keyword-v1"
