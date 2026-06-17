import logging
from datetime import date
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
CROSSREF_URL = "https://api.crossref.org/works"


def _first(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return ""


def _date_from_parts(parts: list[list[int]] | None) -> str:
    if not parts:
        return ""
    values = parts[0]
    if len(values) >= 3:
        return f"{values[0]:04d}-{values[1]:02d}-{values[2]:02d}"
    if len(values) == 2:
        return f"{values[0]:04d}-{values[1]:02d}-01"
    if len(values) == 1:
        return f"{values[0]:04d}-01-01"
    return ""


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in item.get("author", []):
        name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
        if name:
            authors.append(name)
    published = item.get("published-online") or item.get("published-print") or item.get("created") or {}
    return {
        "source": "Crossref",
        "title": _first(item.get("title")),
        "authors": authors,
        "venue": _first(item.get("container-title")),
        "published_date": _date_from_parts(published.get("date-parts")),
        "doi": item.get("DOI") or "",
        "url": item.get("URL") or "",
        "abstract": item.get("abstract") or "",
        "citation_count": item.get("is-referenced-by-count") or 0,
        "paper_id": item.get("DOI") or item.get("URL") or _first(item.get("title")),
        "keywords": item.get("subject") or [],
    }


def search_crossref(
    config: dict[str, Any],
    start_date: date,
    end_date: date,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    session = session or requests.Session()
    timeout = config.get("search", {}).get("request_timeout", 20)
    max_results = int(config.get("search", {}).get("max_results_per_source", 80))
    keywords = config.get("keywords", {}).get("include", [])
    email = config.get("profile", {}).get("email_to", "")
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    successful_requests = 0
    failed_requests = 0

    def finish() -> list[dict[str, Any]]:
        search_crossref.last_status = {
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
        }
        return results

    per_query = max(5, min(40, max_results // max(1, len(keywords)) + 1))

    for query in keywords:
        params = {
            "query.bibliographic": query,
            "rows": per_query,
            "filter": f"from-pub-date:{start_date.isoformat()},until-pub-date:{end_date.isoformat()},type:journal-article",
            "sort": "published",
            "order": "desc",
        }
        if email and "@" in email and "example.com" not in email:
            params["mailto"] = email
        try:
            response = session.get(CROSSREF_URL, params=params, timeout=timeout)
            response.raise_for_status()
            successful_requests += 1
            for item in response.json().get("message", {}).get("items", []):
                item_id = item.get("DOI") or item.get("URL") or _first(item.get("title"))
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    results.append(_normalize_item(item))
                if len(results) >= max_results:
                    return finish()
        except requests.RequestException as exc:
            failed_requests += 1
            LOGGER.warning("Crossref query failed for %r: %s", query, exc)
        except ValueError as exc:
            failed_requests += 1
            LOGGER.warning("Crossref returned invalid JSON for %r: %s", query, exc)
    return finish()
