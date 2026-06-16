import logging
import os
from datetime import date
from typing import Any

import requests
from dateutil.parser import parse as parse_date

LOGGER = logging.getLogger(__name__)
SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"


def _in_date_window(value: str, start_date: date, end_date: date) -> bool:
    if not value:
        return False
    try:
        parsed = parse_date(value).date()
    except (TypeError, ValueError, OverflowError):
        return False
    return start_date <= parsed <= end_date


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    title = entry.get("dc:title") or ""
    creator = entry.get("dc:creator") or ""
    authors = [creator] if creator else []
    doi = entry.get("prism:doi") or ""
    return {
        "source": "Elsevier Scopus",
        "title": title,
        "authors": authors,
        "venue": entry.get("prism:publicationName") or "",
        "published_date": entry.get("prism:coverDate") or "",
        "doi": doi,
        "url": entry.get("prism:url") or (f"https://doi.org/{doi}" if doi else ""),
        "abstract": entry.get("dc:description") or "",
        "citation_count": int(entry.get("citedby-count") or 0),
        "paper_id": entry.get("eid") or doi or entry.get("prism:url") or title,
        "keywords": [entry.get("subtypeDescription", "")] if entry.get("subtypeDescription") else [],
    }


def search_elsevier(
    config: dict[str, Any],
    start_date: date,
    end_date: date,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    api_key = os.getenv("ELSEVIER_API_KEY", "")
    if not api_key:
        LOGGER.info("ELSEVIER_API_KEY is not set; skipping Elsevier Scopus search.")
        return []

    session = session or requests.Session()
    timeout = config.get("search", {}).get("request_timeout", 20)
    max_results = int(config.get("search", {}).get("max_results_per_source", 80))
    keywords = config.get("keywords", {}).get("include", [])
    per_query = max(5, min(25, max_results // max(1, len(keywords)) + 1))
    headers = {
        "Accept": "application/json",
        "X-ELS-APIKey": api_key,
    }
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for query in keywords:
        params = {
            "query": f'TITLE-ABS-KEY("{query}")',
            "date": str(end_date.year),
            "count": per_query,
            "sort": "-coverDate",
            "field": ",".join(
                [
                    "dc:title",
                    "dc:creator",
                    "prism:publicationName",
                    "prism:coverDate",
                    "prism:doi",
                    "prism:url",
                    "dc:description",
                    "citedby-count",
                    "eid",
                    "subtypeDescription",
                ]
            ),
        }
        try:
            response = session.get(SCOPUS_SEARCH_URL, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            entries = response.json().get("search-results", {}).get("entry", [])
            for entry in entries:
                if not _in_date_window(entry.get("prism:coverDate", ""), start_date, end_date):
                    continue
                entry_id = entry.get("eid") or entry.get("prism:doi") or entry.get("dc:title")
                if entry_id and entry_id not in seen_ids:
                    seen_ids.add(entry_id)
                    results.append(_normalize_entry(entry))
                if len(results) >= max_results:
                    return results
        except requests.RequestException as exc:
            LOGGER.warning("Elsevier Scopus query failed for %r: %s", query, exc)
        except ValueError as exc:
            LOGGER.warning("Elsevier Scopus returned invalid JSON for %r: %s", query, exc)
    return results
