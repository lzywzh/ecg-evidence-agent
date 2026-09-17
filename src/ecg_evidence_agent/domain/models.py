from datetime import date
from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceType(StrEnum):
    GUIDELINE = "guideline"
    CONSENSUS = "consensus"
    TERMINOLOGY = "terminology"
    SYNTHETIC = "synthetic"


class SearchStatus(StrEnum):
    FOUND = "found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    institution: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: SourceType
    version: str | None = None
    published_date: date | None = None
    source_uri: str | None = None
    retrieved_at: date
    scope: str = Field(min_length=1)
    usage_terms: str = Field(min_length=1)
    redistributable: bool
    is_synthetic: bool

    @model_validator(mode="after")
    def validate_source_kind(self) -> "SourceMetadata":
        if self.is_synthetic != (self.source_type is SourceType.SYNTHETIC):
            raise ValueError("source_type synthetic and is_synthetic must agree")
        if not self.is_synthetic:
            parsed = urlparse(self.source_uri or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("non-synthetic source_uri must be an HTTP(S) URL")
        return self


class ChunkDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ordinal: int = Field(ge=0)
    locator: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_name: str = Field(min_length=1)
    format: Literal["txt", "md", "json"]
    raw_bytes: bytes
    chunks: list[ChunkDraft] = Field(min_length=1)


class ImportResult(BaseModel):
    source_id: int
    document_id: int
    chunks_imported: int
    created: bool


class StoredChunk(BaseModel):
    chunk_id: int
    document_id: int
    ordinal: int
    locator: str
    text: str
    source_id: int
    source: SourceMetadata


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class EvidenceHit(BaseModel):
    chunk_id: int
    text: str
    score: float
    locator: str
    source_id: int
    source_key: str
    institution: str
    title: str
    version: str | None
    published_date: date | None
    source_uri: str | None
    scope: str
    is_synthetic: bool


class SearchResponse(BaseModel):
    query: str
    retrieval_method: Literal["keyword-v1"] = "keyword-v1"
    status: SearchStatus
    hits: list[EvidenceHit]
