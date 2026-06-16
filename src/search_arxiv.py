import logging
from datetime import date
from typing import Any
from urllib.parse import quote_plus

import feedparser
import requests
from dateutil.parser import parse as parse_date

LOGGER = logging.getLogger(__name__)
ARXIV_URL = "https://export.arxiv.org/api/query"


def _in_date_window(value: str, start_date: date, end_date: date) -> bool:
    try:
        parsed = parse_date(value).date()
    except (TypeError, ValueError, OverflowError):
        return False
    return start_date <= parsed <= end_date


def _normalize_entry(entry: Any) -> dict[str, Any]:
    doi = ""
    for link in entry.get("links", []):
        if link.get("title") == "doi":
            doi = link.get("href", "").replace("https://doi.org/", "")
    return {
        "source": "arXiv",
        "title": entry.get("title", "").replace("\n", " ").strip(),
        "authors": [a.get("name", "") for a in entry.get("authors", []) if a.get("name")],
        "venue": "arXiv",
        "published_date": entry.get("published", "")[:10],
        "doi": doi,
        "url": entry.get("link", ""),
        "abstract": entry.get("summary", "").replace("\n", " ").strip(),
        "citation_count": 0,
        "paper_id": entry.get("id", ""),
        "keywords": [tag.get("term", "") for tag in entry.get("tags", []) if tag.get("term")],
    }


def search_arxiv(
    config: dict[str, Any],
    start_date: date,
    end_date: date,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    session = session or requests.Session()
    timeout = config.get("search", {}).get("request_timeout", 20)
    max_results = int(config.get("search", {}).get("max_results_per_source", 80))
    keywords = config.get("keywords", {}).get("include", [])
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    per_query = max(5, min(30, max_results // max(1, len(keywords)) + 1))

    for query in keywords:
        search_query = quote_plus(f'all:"{query}"')
        url = f"{ARXIV_URL}?search_query={search_query}&start=0&max_results={per_query}&sortBy=submittedDate&sortOrder=descending"
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            for entry in feed.entries:
                if not _in_date_window(entry.get("published", ""), start_date, end_date):
                    continue
                entry_id = entry.get("id") or entry.get("title")
                if entry_id and entry_id not in seen_ids:
                    seen_ids.add(entry_id)
                    results.append(_normalize_entry(entry))
                if len(results) >= max_results:
                    return results
        except requests.RequestException as exc:
            LOGGER.warning("arXiv query failed for %r: %s", query, exc)
    return results
