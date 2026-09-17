from datetime import date

import pytest
from pydantic import ValidationError

from ecg_evidence_agent.domain.models import SearchRequest, SourceMetadata


def synthetic_source(**overrides: object) -> SourceMetadata:
    values = {
        "source_key": "synthetic.ecg-terms.v1",
        "institution": "合成数据实验室",
        "title": "合成心电术语检索样例",
        "source_type": "synthetic",
        "version": "1.0",
        "published_date": date(2026, 9, 17),
        "source_uri": "data/synthetic/terminology.md",
        "retrieved_at": date(2026, 9, 17),
        "scope": "仅用于检索流程测试，不表达医学定义",
        "usage_terms": "项目自建合成数据，可随教学代码分发",
        "redistributable": True,
        "is_synthetic": True,
    }
    values.update(overrides)
    return SourceMetadata.model_validate(values)


def test_accepts_synthetic_source() -> None:
    assert synthetic_source().source_key == "synthetic.ecg-terms.v1"


@pytest.mark.parametrize("source_key", ["AB", "Upper.Case", "has space", "../escape"])
def test_rejects_invalid_source_key(source_key: str) -> None:
    with pytest.raises(ValidationError):
        synthetic_source(source_key=source_key)


def test_real_source_requires_http_source_uri() -> None:
    with pytest.raises(ValidationError, match="source_uri"):
        synthetic_source(
            source_key="real.example.v1",
            source_type="guideline",
            is_synthetic=False,
            source_uri=None,
        )


def test_synthetic_flag_and_type_must_agree() -> None:
    with pytest.raises(ValidationError, match="synthetic"):
        synthetic_source(source_type="guideline", is_synthetic=True)


@pytest.mark.parametrize("query", ["", "   ", "x" * 501])
def test_rejects_invalid_search_query(query: str) -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query=query)


@pytest.mark.parametrize("top_k", [0, 21])
def test_rejects_invalid_top_k(top_k: int) -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="QTc", top_k=top_k)
