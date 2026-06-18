import logging
import os
import re
import time
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
EASYSCHOLAR_RANK_URL = "https://www.easyscholar.cc/open/getPublicationRank"


def _normalize_venue(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _float_from_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _is_impact_factor_key(key: str) -> bool:
    normalized = key.lower().replace("_", "").replace("-", "")
    return any(
        token in normalized
        for token in [
            "sciif",
            "impactfactor",
            "impact",
            "影响因子",
        ]
    ) or normalized in {"if", "jif"}


def _is_jcr_key(key: str) -> bool:
    normalized = key.lower().replace("_", "").replace("-", "")
    return "jcr" in normalized or "分区" in normalized or "quartile" in normalized


def _walk_values(payload: Any, parent_key: str = "") -> list[tuple[str, Any]]:
    if isinstance(payload, dict):
        values: list[tuple[str, Any]] = []
        for key, value in payload.items():
            values.extend(_walk_values(value, str(key)))
        return values
    if isinstance(payload, list):
        values = []
        for item in payload:
            values.extend(_walk_values(item, parent_key))
        return values
    return [(parent_key, payload)]


def _extract_impact_factor(payload: dict[str, Any]) -> float | None:
    candidates: list[float] = []
    for key, value in _walk_values(payload):
        if not _is_impact_factor_key(key):
            continue
        parsed = _float_from_value(value)
        if parsed is not None:
            candidates.append(parsed)
    return max(candidates) if candidates else None


def _extract_jcr_quartile(payload: dict[str, Any]) -> str:
    for key, value in _walk_values(payload):
        if not _is_jcr_key(key):
            continue
        text = str(value).strip()
        match = re.search(r"Q[1-4]", text, flags=re.IGNORECASE)
        if match:
            return match.group(0).upper()
        match = re.search(r"[1-4]\s*[区區]", text)
        if match:
            return "Q" + match.group(0)[0]
    for _, value in _walk_values(payload):
        text = str(value).strip()
        match = re.search(r"\bQ[1-4]\b", text, flags=re.IGNORECASE)
        if match:
            return match.group(0).upper()
        match = re.search(r"[1-4]\s*[区區]", text)
        if match:
            return "Q" + match.group(0)[0]
    return ""


def _extract_payload(response_payload: dict[str, Any]) -> dict[str, Any]:
    data = response_payload.get("data")
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else response_payload
    if isinstance(data, dict):
        return data
    return response_payload


def query_publication_rank(
    publication_name: str,
    config: dict[str, Any],
    session: requests.Session | None = None,
) -> dict[str, Any]:
    secret_key = os.getenv("EASYSCHOLAR_SECRET_KEY", "")
    if not secret_key or not publication_name:
        return {}

    session = session or requests.Session()
    timeout = config.get("search", {}).get("request_timeout", 20)
    response = session.get(
        EASYSCHOLAR_RANK_URL,
        params={"secretKey": secret_key, "publicationName": publication_name},
        timeout=timeout,
    )
    response.raise_for_status()
    raw_payload = response.json()
    payload = _extract_payload(raw_payload if isinstance(raw_payload, dict) else {})
    impact_factor = _extract_impact_factor(payload)
    return {
        "venue": publication_name,
        "impact_factor": impact_factor,
        "jcr_quartile": _extract_jcr_quartile(payload),
        "impact_factor_source": "EasyScholar",
        "raw": raw_payload,
    }


def enrich_papers_with_journal_metrics(
    papers: list[dict[str, Any]],
    config: dict[str, Any],
    session: requests.Session | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    secret_key = os.getenv("EASYSCHOLAR_SECRET_KEY", "")
    if not secret_key:
        return (
            papers,
            {
                "source": "EasyScholar JCR",
                "status": "未调用",
                "queried_count": 0,
                "matched_count": 0,
                "note": "缺少 EASYSCHOLAR_SECRET_KEY，使用配置表影响因子作为备用值",
            },
        )

    session = session or requests.Session()
    settings = config.get("easyscholar", {})
    min_interval = float(settings.get("min_interval_seconds", 0.2))
    cache: dict[str, dict[str, Any]] = {}
    successful_requests = 0
    failed_requests = 0
    matched_count = 0
    last_request_at = 0.0

    for paper in papers:
        venue = paper.get("venue") or ""
        normalized = _normalize_venue(venue)
        if not normalized:
            continue
        if normalized not in cache:
            elapsed = time.monotonic() - last_request_at
            if last_request_at and elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            try:
                cache[normalized] = query_publication_rank(venue, config, session=session)
                successful_requests += 1
            except (requests.RequestException, ValueError, TypeError) as exc:
                failed_requests += 1
                cache[normalized] = {}
                LOGGER.warning("EasyScholar query failed for %r: %s", venue, exc)
            last_request_at = time.monotonic()

        metrics = cache.get(normalized) or {}
        impact_factor = metrics.get("impact_factor")
        if impact_factor is None:
            continue
        paper["impact_factor"] = impact_factor
        paper["impact_factor_source"] = metrics.get("impact_factor_source", "EasyScholar")
        paper["jcr_quartile"] = metrics.get("jcr_quartile", "")
        matched_count += 1

    if failed_requests and successful_requests:
        status = "部分成功"
    elif failed_requests:
        status = "失败"
    else:
        status = "成功"
    return (
        papers,
        {
            "source": "EasyScholar JCR",
            "status": status,
            "queried_count": len(cache),
            "matched_count": matched_count,
            "note": f"API 已调用，{successful_requests} 次成功，{failed_requests} 次失败；{matched_count} 篇论文匹配到影响因子",
        },
    )
