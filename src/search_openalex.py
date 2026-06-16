import logging
from datetime import date
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
OPENALEX_URL = "https://api.openalex.org/works"


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((position, word))
    return " ".join(word for _, word in sorted(words))


def _best_open_url(work: dict[str, Any]) -> str:
    open_access = work.get("open_access") or {}
    primary = work.get("primary_location") or {}
    landing = primary.get("landing_page_url") or primary.get("pdf_url")
    return open_access.get("oa_url") or landing or work.get("doi") or work.get("id") or ""


def _normalize_work(work: dict[str, Any]) -> dict[str, Any]:
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    authorships = work.get("authorships") or []
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in authorships
        if (a.get("author") or {}).get("display_name")
    ]
    return {
        "source": "OpenAlex",
        "title": work.get("title") or "",
        "authors": authors,
        "venue": source.get("display_name") or "",
        "published_date": work.get("publication_date") or "",
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "url": _best_open_url(work),
        "abstract": _abstract_from_inverted_index(work.get("abstract_inverted_index")),
        "citation_count": work.get("cited_by_count") or 0,
        "paper_id": work.get("id") or "",
        "keywords": [k.get("display_name", "") for k in work.get("keywords", []) if k.get("display_name")],
    }


def search_openalex(
    config: dict[str, Any],
    start_date: date,
    end_date: date,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    session = session or requests.Session()
    timeout = config.get("search", {}).get("request_timeout", 20)
    max_results = int(config.get("search", {}).get("max_results_per_source", 80))
    keywords = config.get("keywords", {}).get("include", [])
    email = config.get("profile", {}).get("email_to")
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    per_query = max(5, min(50, max_results // max(1, len(keywords)) + 1))
    for query in keywords:
        params = {
            "search": query,
            "per-page": per_query,
            "filter": f"from_publication_date:{start_date.isoformat()},to_publication_date:{end_date.isoformat()}",
            "sort": "publication_date:desc",
        }
        if email and "@" in email and "example.com" not in email:
            params["mailto"] = email
        try:
            response = session.get(OPENALEX_URL, params=params, timeout=timeout)
            response.raise_for_status()
            for work in response.json().get("results", []):
                work_id = work.get("id") or work.get("doi") or work.get("title")
                if work_id and work_id not in seen_ids:
                    seen_ids.add(work_id)
                    results.append(_normalize_work(work))
                if len(results) >= max_results:
                    return results
        except requests.RequestException as exc:
            LOGGER.warning("OpenAlex query failed for %r: %s", query, exc)
        except ValueError as exc:
            LOGGER.warning("OpenAlex returned invalid JSON for %r: %s", query, exc)
    return results
