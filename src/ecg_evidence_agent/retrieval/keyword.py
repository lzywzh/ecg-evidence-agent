import re
import unicodedata

from ecg_evidence_agent.domain.models import EvidenceHit, StoredChunk


TOKEN_RE = re.compile(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*|[\u3400-\u9fff]+")
CJK_RE = re.compile(r"^[\u3400-\u9fff]+$")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def _terms(text: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_RE.findall(normalize_text(text))))


def _term_count(term: str, normalized_text: str, text_tokens: list[str]) -> int:
    if CJK_RE.fullmatch(term):
        return normalized_text.count(term)
    return text_tokens.count(term)


def keyword_score(query: str, text: str) -> float:
    normalized_query = normalize_text(query)
    normalized_text = normalize_text(text)
    query_terms = _terms(query)
    text_tokens = TOKEN_RE.findall(normalized_text)
    if not query_terms:
        return 0.0

    counts = [
        _term_count(term, normalized_text, text_tokens) for term in query_terms
    ]
    matched_count = sum(count > 0 for count in counts)
    if matched_count == 0:
        return 0.0

    coverage = matched_count / len(query_terms)
    frequency = sum(min(count, 3) for count in counts)
    phrase_bonus = (
        2.0
        if matched_count == len(query_terms) and normalized_query in normalized_text
        else 0.0
    )
    return round(phrase_bonus + 2.0 * coverage + 0.1 * frequency, 6)


def rank_candidates(
    query: str,
    candidates: list[StoredChunk],
    top_k: int,
) -> list[EvidenceHit]:
    ranked: list[tuple[EvidenceHit, int]] = []
    for candidate in candidates:
        score = keyword_score(query, candidate.text)
        if score == 0:
            continue
        source = candidate.source
        hit = EvidenceHit(
            chunk_id=candidate.chunk_id,
            text=candidate.text,
            score=score,
            locator=candidate.locator,
            source_id=candidate.source_id,
            source_key=source.source_key,
            institution=source.institution,
            title=source.title,
            version=source.version,
            published_date=source.published_date,
            source_uri=source.source_uri,
            scope=source.scope,
            is_synthetic=source.is_synthetic,
        )
        ranked.append((hit, candidate.ordinal))

    ranked.sort(
        key=lambda pair: (
            -pair[0].score,
            pair[0].source_id,
            pair[1],
            pair[0].chunk_id,
        )
    )
    return [hit for hit, _ordinal in ranked[:top_k]]
