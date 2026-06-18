import hashlib
import json
import logging
import re
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

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


def _title_relevance_score(title: str, config: dict[str, Any]) -> float:
    text = normalize_text(title)
    include = config.get("keywords", {}).get("include", [])
    exclude = config.get("keywords", {}).get("exclude", [])
    matched_include = sum(1 for term in include if contains_term(text, term))
    if matched_include == 0:
        return 0.0
    matched_exclude = sum(1 for term in exclude if contains_term(text, term))

    include_score = min(1.0, matched_include / 3)
    penalty = min(0.8, matched_exclude * 0.3)
    return max(0.0, min(1.0, include_score - penalty))


def _configured_impact_factor(venue: str, config: dict[str, Any]) -> float:
    normalized_venue = normalize_text(venue)
    impact_factors = config.get("venues", {}).get("impact_factors", {})
    for name, value in impact_factors.items():
        normalized_name = normalize_text(str(name))
        if normalized_name and (normalized_name in normalized_venue or normalized_venue in normalized_name):
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                return 0.0
    return float(config.get("ranking", {}).get("default_impact_factor", 1.0))


def _paper_impact_factor(paper: dict[str, Any], config: dict[str, Any]) -> tuple[float, str]:
    try:
        if paper.get("impact_factor") is not None:
            return max(0.0, float(paper["impact_factor"])), str(paper.get("impact_factor_source") or "EasyScholar")
    except (TypeError, ValueError):
        pass
    return _configured_impact_factor(paper.get("venue", ""), config), "配置表"


def _impact_factor_score(paper: dict[str, Any], config: dict[str, Any]) -> tuple[float, float, str]:
    impact_factor, impact_factor_source = _paper_impact_factor(paper, config)
    max_impact_factor = max(1.0, float(config.get("ranking", {}).get("max_impact_factor", 80.0)))
    return min(1.0, impact_factor / max_impact_factor), impact_factor, impact_factor_source


def score_paper(paper: dict[str, Any], config: dict[str, Any], end_date: date | None = None) -> dict[str, Any]:
    weights = config.get("ranking", {})
    title_relevance = _title_relevance_score(paper.get("title", ""), config)
    impact_factor, impact_factor_value, impact_factor_source = _impact_factor_score(paper, config)

    score = (
        title_relevance * float(weights.get("weight_title_relevance", 0.70))
        + impact_factor * float(weights.get("weight_impact_factor", 0.30))
    )
    enriched = dict(paper)
    enriched["score"] = round(score * 10, 2)
    enriched["impact_factor"] = round(impact_factor_value, 3)
    enriched["impact_factor_source"] = impact_factor_source
    enriched["score_breakdown"] = {
        "title_relevance": round(title_relevance, 3),
        "impact_factor": round(impact_factor, 3),
        "impact_factor_value": round(impact_factor_value, 3),
    }
    return enriched


def rank_papers(papers: list[dict[str, Any]], config: dict[str, Any], end_date: date | None = None) -> list[dict[str, Any]]:
    scored = [score_paper(paper, config, end_date=end_date) for paper in papers if paper.get("title")]
    filtered = [paper for paper in scored if paper["score_breakdown"]["title_relevance"] > 0]
    return sorted(filtered, key=lambda paper: paper.get("score", 0), reverse=True)
