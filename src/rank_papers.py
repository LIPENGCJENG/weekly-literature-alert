import hashlib
import json
import logging
import re
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from dateutil.parser import parse as parse_date

LOGGER = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://doi\.org/", "", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_term(text: str, term: str) -> bool:
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    if len(normalized_term) <= 3:
        return re.search(rf"(^|\s){re.escape(normalized_term)}($|\s)", text) is not None
    return normalized_term in text


def normalize_doi(doi: str) -> str:
    return normalize_text(doi).replace(" ", "")


def paper_fingerprint(paper: dict[str, Any]) -> str:
    doi = normalize_doi(paper.get("doi", ""))
    if doi:
        return f"doi:{doi}"
    title = normalize_text(paper.get("title", ""))
    if title:
        return f"title:{hashlib.sha1(title.encode('utf-8')).hexdigest()}"
    return f"url:{paper.get('url', '')}"


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        LOGGER.warning("Could not load seen file %s: %s", path, exc)
        return set()
    if isinstance(payload, dict):
        return {str(item) for item in payload.get("items", [])}
    if isinstance(payload, list):
        return {str(item) for item in payload}
    return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": sorted(seen)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def deduplicate_papers(papers: list[dict[str, Any]], title_threshold: float = 0.93) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    doi_index: set[str] = set()
    url_index: set[str] = set()

    for paper in papers:
        doi = normalize_doi(paper.get("doi", ""))
        url = paper.get("url", "").strip().lower()
        title = paper.get("title", "")
        if doi and doi in doi_index:
            continue
        if url and url in url_index:
            continue
        if title and any(title_similarity(title, existing.get("title", "")) >= title_threshold for existing in deduped):
            continue

        if doi:
            doi_index.add(doi)
        if url:
            url_index.add(url)
        deduped.append(paper)
    return deduped


def filter_seen(papers: list[dict[str, Any]], seen: set[str]) -> list[dict[str, Any]]:
    return [paper for paper in papers if paper_fingerprint(paper) not in seen]


def _combined_text(paper: dict[str, Any]) -> str:
    parts = [
        paper.get("title", ""),
        paper.get("abstract", ""),
        " ".join(paper.get("keywords", []) or []),
        paper.get("venue", ""),
    ]
    return normalize_text(" ".join(parts))


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return parse_date(str(value)).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _keyword_score(text: str, config: dict[str, Any]) -> float:
    include = config.get("keywords", {}).get("include", [])
    exclude = config.get("keywords", {}).get("exclude", [])
    boost_terms = config.get("ranking", {}).get("doctoral_boost_terms", [])
    matched_include = sum(1 for term in include if contains_term(text, term))
    if matched_include == 0:
        return 0.0
    matched_boost = sum(1 for term in boost_terms if contains_term(text, term))
    matched_exclude = sum(1 for term in exclude if contains_term(text, term))

    include_score = min(1.0, matched_include / 4)
    boost_score = min(0.35, matched_boost * 0.05)
    penalty = min(0.6, matched_exclude * 0.2)
    return max(0.0, min(1.0, include_score + boost_score - penalty))


def _venue_score(venue: str, config: dict[str, Any]) -> float:
    normalized_venue = normalize_text(venue)
    whitelist = config.get("venues", {}).get("whitelist", [])
    for index, name in enumerate(whitelist):
        if normalize_text(name) in normalized_venue or normalized_venue in normalize_text(name):
            return max(0.65, 1.0 - index * 0.015)
    return 0.35


def _recency_score(published_date: str, end_date: date, days_back: int) -> float:
    parsed = _parse_date(published_date)
    if not parsed:
        return 0.35
    age = max(0, (end_date - parsed).days)
    return max(0.0, 1.0 - age / max(1, days_back))


def _citation_score(paper: dict[str, Any]) -> float:
    citations = int(paper.get("citation_count") or 0)
    influential = int(paper.get("influential_citation_count") or 0)
    return min(1.0, (citations + influential * 2) / 50)


def score_paper(paper: dict[str, Any], config: dict[str, Any], end_date: date | None = None) -> dict[str, Any]:
    end_date = end_date or date.today()
    days_back = int(config.get("search", {}).get("days_back", 10))
    weights = config.get("ranking", {})
    text = _combined_text(paper)

    relevance = _keyword_score(text, config)
    venue = _venue_score(paper.get("venue", ""), config)
    recency = _recency_score(paper.get("published_date", ""), end_date, days_back)
    citation = _citation_score(paper)

    score = (
        relevance * float(weights.get("weight_relevance", 0.45))
        + venue * float(weights.get("weight_venue", 0.30))
        + recency * float(weights.get("weight_recency", 0.15))
        + citation * float(weights.get("weight_citation_signal", 0.10))
    )
    enriched = dict(paper)
    enriched["score"] = round(score * 10, 2)
    enriched["score_breakdown"] = {
        "relevance": round(relevance, 3),
        "venue": round(venue, 3),
        "recency": round(recency, 3),
        "citation_signal": round(citation, 3),
    }
    return enriched


def rank_papers(papers: list[dict[str, Any]], config: dict[str, Any], end_date: date | None = None) -> list[dict[str, Any]]:
    scored = [score_paper(paper, config, end_date=end_date) for paper in papers if paper.get("title")]
    filtered = [paper for paper in scored if paper["score_breakdown"]["relevance"] > 0]
    return sorted(filtered, key=lambda paper: paper.get("score", 0), reverse=True)
