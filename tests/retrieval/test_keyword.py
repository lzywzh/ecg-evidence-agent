from collections.abc import Callable

from ecg_evidence_agent.domain.models import SourceMetadata, StoredChunk
from ecg_evidence_agent.retrieval.keyword import (
    keyword_score,
    normalize_text,
    rank_candidates,
)


def candidate(
    source: SourceMetadata,
    *,
    chunk_id: int,
    source_id: int = 1,
    ordinal: int = 0,
    text: str = "QT",
) -> StoredChunk:
    return StoredChunk(
        chunk_id=chunk_id,
        document_id=1,
        ordinal=ordinal,
        locator=f"chunk:{chunk_id}",
        text=text,
        source_id=source_id,
        source=source,
    )


def test_nfkc_case_and_whitespace_normalization() -> None:
    assert normalize_text("  ＱＴＣ\t420  ") == "qtc 420"


def test_exact_phrase_scores_above_partial_term_match() -> None:
    exact = keyword_score("qt interval", "qt interval appears here")
    partial = keyword_score("qt interval", "qt value and interval appear separately")
    assert exact > partial > 0


def test_qt_and_qtc_are_not_treated_as_equal() -> None:
    assert keyword_score("qt", "only qtc appears") == 0


def test_cjk_phrase_can_match_as_substring() -> None:
    assert keyword_score("否定表达", "这里包含否定表达样例") > 0


def test_no_term_match_returns_zero() -> None:
    assert keyword_score("unseen-term", "completely different text") == 0


def test_frequency_is_capped_at_three_per_term() -> None:
    assert keyword_score("qt", "qt qt qt") == keyword_score("qt", "qt qt qt qt qt")


def test_rank_excludes_zero_score_candidates(
    source_factory: Callable[..., SourceMetadata],
) -> None:
    source = source_factory()
    ranked = rank_candidates(
        "qt",
        [
            candidate(source, chunk_id=1, text="qtc only"),
            candidate(source, chunk_id=2, text="qt exact"),
        ],
        top_k=5,
    )
    assert [hit.chunk_id for hit in ranked] == [2]


def test_rank_uses_source_and_chunk_order_as_stable_tie_breakers(
    source_factory: Callable[..., SourceMetadata],
) -> None:
    source = source_factory()
    ranked = rank_candidates(
        "qt",
        [
            candidate(source, chunk_id=4, source_id=2, ordinal=0, text="qt"),
            candidate(source, chunk_id=3, source_id=1, ordinal=1, text="qt"),
            candidate(source, chunk_id=2, source_id=1, ordinal=0, text="qt"),
        ],
        top_k=5,
    )
    assert [hit.chunk_id for hit in ranked] == [2, 3, 4]


def test_rank_respects_top_k(
    source_factory: Callable[..., SourceMetadata],
) -> None:
    source = source_factory()
    ranked = rank_candidates(
        "qt",
        [candidate(source, chunk_id=index, text="qt") for index in range(1, 4)],
        top_k=2,
    )
    assert len(ranked) == 2
