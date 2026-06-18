import argparse
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import yaml

from easyscholar import enrich_papers_with_journal_metrics
from rank_papers import (
    contains_term,
    deduplicate_papers,
    filter_seen,
    load_seen,
    normalize_text,
    paper_fingerprint,
    rank_papers,
    save_seen,
    score_paper,
)
from search_crossref import search_crossref
from search_elsevier import search_elsevier
from search_openalex import search_openalex
from search_semantic_scholar import search_semantic_scholar
from send_email import send_email
from summarize_papers import enrich_papers_with_summaries, markdown_to_html, render_markdown_report, save_reports

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SearchFunction = Callable[[dict[str, Any], date, date], list[dict[str, Any]]]
SOURCE_DEFINITIONS: list[dict[str, Any]] = [
    {"name": "OpenAlex", "func": search_openalex},
    {"name": "Crossref", "func": search_crossref},
    {"name": "Semantic Scholar", "func": search_semantic_scholar, "required_env": "SEMANTIC_SCHOLAR_API_KEY"},
    {"name": "Elsevier Scopus", "func": search_elsevier, "required_env": "ELSEVIER_API_KEY"},
]


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _source_call_summary(search_func: SearchFunction, returned_count: int) -> dict[str, Any]:
    metadata = getattr(search_func, "last_status", {}) or {}
    successful_requests = int(metadata.get("successful_requests", 1) or 0)
    failed_requests = int(metadata.get("failed_requests", 0) or 0)
    if failed_requests and successful_requests:
        return {
            "status": "部分成功",
            "returned_count": returned_count,
            "note": f"API 已调用，{successful_requests} 次成功，{failed_requests} 次失败",
        }
    if failed_requests:
        return {
            "status": "失败",
            "returned_count": returned_count,
            "note": f"API 调用失败，{failed_requests} 次失败",
        }
    return {
        "status": "成功",
        "returned_count": returned_count,
        "note": f"API 已成功调用，{successful_requests} 次成功",
    }


def _has_excluded_topic(paper: dict[str, Any], config: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("keywords", []) or []),
                paper.get("venue", ""),
            ]
        )
    )
    return any(contains_term(text, term) for term in config.get("keywords", {}).get("exclude", []))


def _has_included_topic(paper: dict[str, Any], config: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("keywords", []) or []),
                paper.get("venue", ""),
            ]
        )
    )
    return any(contains_term(text, term) for term in config.get("keywords", {}).get("include", []))


def _has_domain_fallback_topic(paper: dict[str, Any]) -> bool:
    text = normalize_text(
        " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("keywords", []) or []),
                paper.get("venue", ""),
            ]
        )
    )
    has_electrolyte = contains_term(text, "electrolyte") or contains_term(text, "electrolytes")
    has_battery_context = any(
        contains_term(text, term)
        for term in [
            "lithium",
            "li ion",
            "li",
            "battery",
            "batteries",
            "solid state",
            "solid electrolyte",
            "all solid state",
        ]
    )
    return has_electrolyte and has_battery_context


def select_papers(
    unseen_papers: list[dict[str, Any]],
    ranked_papers: list[dict[str, Any]],
    config: dict[str, Any],
    end_date: date,
) -> list[dict[str, Any]]:
    top_n = int(config.get("search", {}).get("top_n", 10))
    min_recommendations = int(config.get("search", {}).get("min_recommendations", 0))
    target_count = max(top_n, min_recommendations)
    selected = [paper for paper in ranked_papers if not _has_excluded_topic(paper, config)][:target_count]
    if len(selected) >= min_recommendations:
        return selected

    selected_ids = {paper_fingerprint(paper) for paper in selected}
    fallback = []
    for paper in unseen_papers:
        if (
            not paper.get("title")
            or paper_fingerprint(paper) in selected_ids
            or _has_excluded_topic(paper, config)
            or not (_has_included_topic(paper, config) or _has_domain_fallback_topic(paper))
        ):
            continue
        fallback.append(score_paper(paper, config, end_date=end_date))
    fallback.sort(key=lambda paper: paper.get("score", 0), reverse=True)

    for paper in fallback:
        paper_id = paper_fingerprint(paper)
        if paper_id in selected_ids:
            continue
        selected.append(paper)
        selected_ids.add(paper_id)
        if len(selected) >= min_recommendations:
            break
    return selected[:target_count]


def search_all_sources(config: dict[str, Any], start_date: date, end_date: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    papers: list[dict[str, Any]] = []
    source_stats: list[dict[str, Any]] = []
    for source in SOURCE_DEFINITIONS:
        source_name = source["name"]
        search_func: SearchFunction = source["func"]
        required_env = source.get("required_env")
        if required_env and not os.getenv(required_env):
            LOGGER.info("%s was not called because %s is not set.", source_name, required_env)
            source_stats.append(
                {
                    "source": source_name,
                    "status": "未调用",
                    "returned_count": 0,
                    "note": f"缺少 {required_env}",
                }
            )
            continue
        try:
            source_results = search_func(config, start_date, end_date)
            LOGGER.info("%s returned %d papers", search_func.__name__, len(source_results))
            papers.extend(source_results)
            source_stats.append({"source": source_name, **_source_call_summary(search_func, len(source_results))})
        except Exception as exc:
            LOGGER.exception("%s failed and was skipped: %s", search_func.__name__, exc)
            source_stats.append(
                {
                    "source": source_name,
                    "status": "失败",
                    "returned_count": 0,
                    "note": str(exc),
                }
            )
    return papers, source_stats


def run(config_path: Path, dry_run: bool = False) -> dict[str, Any]:
    config = load_config(config_path)
    today = date.today()
    days_back = int(config.get("search", {}).get("days_back", 10))
    start_date = today - timedelta(days=days_back)
    seen_path = PROJECT_ROOT / "data" / "seen.json"
    report_dir = PROJECT_ROOT / "reports"

    LOGGER.info("Searching papers from %s to %s", start_date, today)
    raw_papers, source_stats = search_all_sources(config, start_date, today)
    unique_papers = deduplicate_papers(raw_papers)
    unique_papers, journal_metrics_stats = enrich_papers_with_journal_metrics(unique_papers, config)
    seen = load_seen(seen_path)
    unseen_papers = filter_seen(unique_papers, seen)
    ranked = rank_papers(unseen_papers, config, end_date=today)
    selected = select_papers(unseen_papers, ranked, config, end_date=today)
    min_recommendations = int(config.get("search", {}).get("min_recommendations", 0))
    if len(selected) < min_recommendations:
        LOGGER.info(
            "Only %d unseen papers selected; allowing previously seen papers to reach minimum %d.",
            len(selected),
            min_recommendations,
        )
        ranked_with_seen = rank_papers(unique_papers, config, end_date=today)
        selected = select_papers(unique_papers, ranked_with_seen, config, end_date=today)
    selected = enrich_papers_with_summaries(selected, config)
    run_report = {
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "raw_count": len(raw_papers),
        "unique_count": len(unique_papers),
        "unseen_count": len(unseen_papers),
        "selected_count": len(selected),
        "sources": source_stats,
        "journal_metrics": journal_metrics_stats,
    }

    markdown_report = render_markdown_report(
        selected,
        config,
        report_date=today,
        total_found=len(unique_papers),
        run_report=run_report,
    )
    latest_md, latest_html = save_reports(markdown_report, report_dir, report_date=today)
    html_report = markdown_to_html(markdown_report)
    sent = False if dry_run else send_email(html_report, config, report_date=today, markdown_body=markdown_report)

    if not dry_run:
        for paper in selected:
            seen.add(paper_fingerprint(paper))
        save_seen(seen_path, seen)

    return {
        "raw_count": len(raw_papers),
        "unique_count": len(unique_papers),
        "selected_count": len(selected),
        "source_stats": source_stats,
        "report_markdown": str(latest_md),
        "report_html": str(latest_html),
        "email_sent": sent,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly literature alert for composite solid electrolytes.")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config.yaml"), help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Generate reports without sending email")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    result = run(Path(args.config), dry_run=args.dry_run)
    LOGGER.info("Finished: %s", result)


if __name__ == "__main__":
    main()
