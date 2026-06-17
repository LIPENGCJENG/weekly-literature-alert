import argparse
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import yaml

from rank_papers import deduplicate_papers, filter_seen, load_seen, paper_fingerprint, rank_papers, save_seen
from search_elsevier import search_elsevier
from search_openalex import search_openalex
from search_semantic_scholar import search_semantic_scholar
from send_email import send_email
from summarize_papers import markdown_to_html, render_markdown_report, save_reports

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def search_all_sources(config: dict[str, Any], start_date: date, end_date: date) -> list[dict[str, Any]]:
    sources: list[Callable[[dict[str, Any], date, date], list[dict[str, Any]]]] = [
        search_openalex,
        search_semantic_scholar,
        search_elsevier,
    ]
    papers: list[dict[str, Any]] = []
    for search_func in sources:
        try:
            source_results = search_func(config, start_date, end_date)
            LOGGER.info("%s returned %d papers", search_func.__name__, len(source_results))
            papers.extend(source_results)
        except Exception as exc:
            LOGGER.exception("%s failed and was skipped: %s", search_func.__name__, exc)
    return papers


def run(config_path: Path, dry_run: bool = False) -> dict[str, Any]:
    config = load_config(config_path)
    today = date.today()
    days_back = int(config.get("search", {}).get("days_back", 10))
    top_n = int(config.get("search", {}).get("top_n", 10))
    start_date = today - timedelta(days=days_back)
    seen_path = PROJECT_ROOT / "data" / "seen.json"
    report_dir = PROJECT_ROOT / "reports"

    LOGGER.info("Searching papers from %s to %s", start_date, today)
    raw_papers = search_all_sources(config, start_date, today)
    unique_papers = deduplicate_papers(raw_papers)
    seen = load_seen(seen_path)
    unseen_papers = filter_seen(unique_papers, seen)
    ranked = rank_papers(unseen_papers, config, end_date=today)
    selected = ranked[:top_n]

    markdown_report = render_markdown_report(selected, config, report_date=today, total_found=len(unique_papers))
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
