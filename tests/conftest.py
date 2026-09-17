from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from ecg_evidence_agent.domain.models import SourceMetadata
from ecg_evidence_agent.storage.sqlite_repository import SQLiteRepository


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "test.db")
    repo.initialize()
    return repo


@pytest.fixture
def source_factory() -> Callable[..., SourceMetadata]:
    def make_source(**overrides: object) -> SourceMetadata:
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

    return make_source
