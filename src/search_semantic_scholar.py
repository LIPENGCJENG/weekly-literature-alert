import logging
import os
import time
from datetime import date
from typing import Any

import requests
from dateutil.parser import parse as parse_date

LOGGER = logging.getLogger(__name__)
SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,venue,publicationDate,year,externalIds,url,abstract,citationCount,influentialCitationCount,fieldsOfStudy"


def _in_date_window(value: str, start_date: date, end_date: date) -> bool:
    if not value:
        return False
    try:
        parsed = parse_date(value).date()
    except (TypeError, ValueError, OverflowError):
        return False
    return start_date <= parsed <= end_date


def _normalize_paper(paper: dict[str, Any]) -> dict[str, Any]:
    external = paper.get("externalIds") or {}
    return {
        "source": "Semantic Scholar",
        "title": paper.get("title") or "",
        "authors": [a.get("name", "") for a in paper.get("authors", []) if a.get("name")],
        "venue": paper.get("venue") or "",
        "published_date": paper.get("publicationDate") or str(paper.get("year") or ""),
        "doi": external.get("DOI") or "",
        "url": paper.get("url") or "",
        "abstract": paper.get("abstract") or "",
        "citation_count": paper.get("citationCount") or 0,
        "influential_citation_count": paper.get("influentialCitationCount") or 0,
        "paper_id": paper.get("paperId") or "",
        "keywords": paper.get("fieldsOfStudy") or [],
    }


def search_semantic_scholar(
    config: dict[str, Any],
    start_date: date,
    end_date: date,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    session = session or requests.Session()
    timeout = config.get("search", {}).get("request_timeout", 20)
    max_results = int(config.get("search", {}).get("max_results_per_source", 80))
    min_interval = float(config.get("search", {}).get("semantic_scholar_min_interval_seconds", 1.1))
    keywords = config.get("keywords", {}).get("include", [])
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if not api_key:
        LOGGER.info("SEMANTIC_SCHOLAR_API_KEY is not set; skipping Semantic Scholar search.")
        return []
    headers = {"x-api-key": api_key}
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    per_query = max(5, min(25, max_results // max(1, len(keywords)) + 1))
    last_request_at = 0.0

    for query in keywords:
        params = {"query": query, "limit": per_query, "fields": FIELDS}
        try:
            elapsed = time.monotonic() - last_request_at
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            response = session.get(SEARCH_URL, params=params, headers=headers, timeout=timeout)
            last_request_at = time.monotonic()
            response.raise_for_status()
            for paper in response.json().get("data", []):
                published = paper.get("publicationDate") or str(paper.get("year") or "")
                if paper.get("publicationDate") and not _in_date_window(published, start_date, end_date):
                    continue
                paper_id = paper.get("paperId") or (paper.get("externalIds") or {}).get("DOI") or paper.get("title")
                if paper_id and paper_id not in seen_ids:
                    seen_ids.add(paper_id)
                    results.append(_normalize_paper(paper))
                if len(results) >= max_results:
                    return results
        except requests.RequestException as exc:
            LOGGER.warning("Semantic Scholar query failed for %r: %s", query, exc)
        except ValueError as exc:
            LOGGER.warning("Semantic Scholar returned invalid JSON for %r: %s", query, exc)
    return results
