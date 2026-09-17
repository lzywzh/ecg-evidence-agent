from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ecg_evidence_agent.domain.models import ChunkDraft, ParsedDocument
from ecg_evidence_agent.errors import DocumentImportError


SUPPORTED_FORMATS = {"txt", "md", "json"}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class _JsonSection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    locator: str = Field(min_length=1)
    text: str = Field(min_length=1)


class _StructuredDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[_JsonSection] = Field(min_length=1)


def load_and_parse(path: Path) -> ParsedDocument:
    document_path = Path(path)
    document_format = document_path.suffix.lower().lstrip(".")
    if document_format not in SUPPORTED_FORMATS:
        raise DocumentImportError("unsupported document format")

    raw_bytes = document_path.read_bytes()
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentImportError("document is not valid UTF-8") from exc

    chunks = _parse_by_format(document_format, text)
    if not chunks:
        raise DocumentImportError("document has no importable text")
    return ParsedDocument(
        original_name=document_path.name,
        format=document_format,
        raw_bytes=raw_bytes,
        chunks=chunks,
    )


def _parse_by_format(
    document_format: str,
    text: str,
) -> list[ChunkDraft]:
    if document_format == "txt":
        return _parse_text(text)
    if document_format == "md":
        return _parse_markdown(text)
    if document_format == "json":
        return _parse_json(text)
    raise DocumentImportError("unsupported document format")


def _parse_text(text: str) -> list[ChunkDraft]:
    return _paragraph_chunks(text.splitlines(), first_line=1)


def _paragraph_chunks(
    lines: list[str],
    *,
    first_line: int,
) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    buffer: list[str] = []
    start_line = first_line

    def flush(end_line: int) -> None:
        nonlocal buffer, start_line
        paragraph = "\n".join(buffer).strip()
        if paragraph:
            chunks.append(
                ChunkDraft(
                    ordinal=len(chunks),
                    locator=f"lines:{start_line}-{end_line}",
                    text=paragraph,
                )
            )
        buffer = []

    for offset, line in enumerate(lines):
        line_number = first_line + offset
        if line.strip():
            if not buffer:
                start_line = line_number
            buffer.append(line)
        elif buffer:
            flush(line_number - 1)
    if buffer:
        flush(first_line + len(lines) - 1)
    return chunks


def _parse_markdown(text: str) -> list[ChunkDraft]:
    lines = text.splitlines()
    chunks: list[ChunkDraft] = []
    current_heading: tuple[str, int] | None = None
    current_lines: list[str] = []
    current_start = 1

    def flush() -> None:
        nonlocal current_lines
        if current_heading is None:
            preamble = _paragraph_chunks(current_lines, first_line=current_start)
            for chunk in preamble:
                chunks.append(chunk.model_copy(update={"ordinal": len(chunks)}))
        else:
            section_text = "\n".join(current_lines).strip()
            if section_text:
                title, heading_line = current_heading
                chunks.append(
                    ChunkDraft(
                        ordinal=len(chunks),
                        locator=f"heading:{title}@line:{heading_line}",
                        text=section_text,
                    )
                )
        current_lines = []

    for line_number, line in enumerate(lines, start=1):
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            current_heading = (heading.group(2).strip(), line_number)
            current_start = line_number
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()
    return chunks


def _parse_json(text: str) -> list[ChunkDraft]:
    try:
        document = _StructuredDocument.model_validate_json(text)
    except ValidationError as exc:
        raise DocumentImportError("invalid structured document") from exc
    return [
        ChunkDraft(
            ordinal=index,
            locator=f"json:sections[{index}]:{section.locator}",
            text=section.text,
        )
        for index, section in enumerate(document.sections)
    ]
