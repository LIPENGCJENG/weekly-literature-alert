import html
import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import markdown
import requests

LOGGER = logging.getLogger(__name__)

TERM_TRANSLATIONS = {
    "composite solid electrolyte": "复合固态电解质",
    "polymer solid electrolyte": "聚合物固态电解质",
    "solid polymer electrolyte": "固态聚合物电解质",
    "composite polymer electrolyte": "复合聚合物电解质",
    "lithium-ion conduction mechanism": "锂离子传导机理",
    "lithium ion transport": "锂离子传输",
    "ceramic filler": "陶瓷填料",
    "polymer ceramic interface": "聚合物-陶瓷界面",
    "space charge layer": "空间电荷层",
    "PEO LiTFSI": "PEO/LiTFSI 体系",
    "LLZO polymer electrolyte": "LLZO/聚合物电解质",
    "BaTiO3 polymer electrolyte": "BaTiO3/聚合物电解质",
    "polymer-ceramic composite electrolyte": "聚合物-陶瓷复合电解质",
    "interfacial ion transport": "界面离子传输",
    "inert ceramic filler": "惰性陶瓷填料",
    "active ceramic filler": "活性陶瓷填料",
    "PEO": "PEO 基体",
    "LiTFSI": "LiTFSI 锂盐",
    "lithium salt": "锂盐",
    "ceramic filler surface": "陶瓷填料表面作用",
    "dielectric constant": "介电常数",
    "Li+ coordination": "锂离子配位结构",
    "polymer crystallinity": "聚合物结晶度",
    "fast ion-conducting interphase": "界面快速导电层",
    "molecular dynamics": "分子动力学模拟",
    "first-principles": "第一性原理计算",
    "DFT": "密度泛函理论计算",
    "in situ": "原位表征",
    "operando": "工况原位表征",
}

SIGNAL_TRANSLATIONS = [
    ("ionic conductivity", "离子电导率"),
    ("lithium ion", "锂离子传输"),
    ("li ion", "锂离子传输"),
    ("lithium-ion", "锂离子传输"),
    ("electrochemical performance", "电化学性能"),
    ("thermal stability", "热稳定性"),
    ("safety", "电池安全性"),
    ("flammability", "阻燃与安全性"),
    ("mechanical", "力学性能"),
    ("crystallinity", "聚合物结晶度"),
    ("segmental motion", "聚合物链段运动"),
    ("interface", "界面结构与界面作用"),
    ("interfacial", "界面结构与界面作用"),
    ("filler", "填料改性"),
    ("ceramic", "陶瓷相引入"),
    ("coordination", "锂离子配位环境"),
    ("space charge", "空间电荷层"),
    ("molecular dynamics", "分子动力学模拟"),
    ("first-principles", "第一性原理计算"),
    ("in situ", "原位表征"),
    ("operando", "工况原位表征"),
]


def _normalize_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return False
    if len(normalized_term) <= 3:
        return re.search(rf"(^|\s){re.escape(normalized_term)}($|\s)", text) is not None
    return normalized_term in text


def _authors_text(authors: list[str], limit: int = 6) -> str:
    if not authors:
        return "未知"
    if len(authors) <= limit:
        return ", ".join(authors)
    return ", ".join(authors[:limit]) + " 等"


def _shorten(text: str, length: int = 380) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(" ".join(text.split()))
    if not text:
        return "未获取到完整摘要。"
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def _matched_terms(paper: dict[str, Any], terms: list[str]) -> list[str]:
    text = _normalize_text(
        " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("keywords", []) or []),
            ]
        )
    )
    return [term for term in terms if _contains_term(text, term)]


def _translated_terms(terms: list[str]) -> list[str]:
    translated: list[str] = []
    for term in terms:
        value = TERM_TRANSLATIONS.get(term, "")
        if value and value not in translated:
            translated.append(value)
    return translated


def _summary_signals(paper: dict[str, Any]) -> list[str]:
    text = _normalize_text(
        " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("keywords", []) or []),
            ]
        )
    )
    signals: list[str] = []
    for term, translation in SIGNAL_TRANSLATIONS:
        if _contains_term(text, term) and translation not in signals:
            signals.append(translation)
    return signals


def _rule_based_summary(paper: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    include_terms = _matched_terms(paper, config.get("keywords", {}).get("include", []))
    boost_terms = _matched_terms(paper, config.get("ranking", {}).get("doctoral_boost_terms", []))
    topic_terms = _translated_terms(include_terms + boost_terms)
    topic = "、".join(topic_terms[:5]) or "复合固态电解质与锂离子传输"
    signals = "、".join(_summary_signals(paper)[:5])
    if paper.get("abstract"):
        problem = (
            f"它试图解决的是{topic}相关体系中的关键限制。"
            f"从题名和摘要看，问题集中在{signals or '材料体系设计、性能评估和机理解释'}。"
            "这些信息提示作者关注的是材料结构、界面行为与离子传输表现之间如何建立更清楚的联系。"
        )
        contribution = (
            f"它声称的贡献是提出或验证了一个围绕{topic}的材料设计、表征或机理分析方案，"
            f"并用{signals or '性能数据和结构分析'}支撑该方案的有效性。"
            "具体贡献仍建议结合全文核对实验条件、对照组和机理证据强度。"
        )
    else:
        problem = (
            "当前公开 API 未返回完整摘要。"
            f"根据题名、期刊和元数据信息判断，该论文主要关注{topic}，"
            "它想解决的问题需要通过阅读全文进一步确认。"
        )
        contribution = (
            "由于缺少摘要，暂时只能判断它可能声称在材料设计、性能提升或机理解释上有所推进。"
            "建议后续阅读全文核对作者真正提出的新方法、新证据或新机制。"
        )
    return {
        "problem": problem,
        "contribution": contribution,
    }


def _json_from_model_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _doi_url(doi: str) -> str:
    doi = (doi or "").strip()
    if not doi:
        return ""
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE).strip()
    return f"https://doi.org/{doi}"


def _gemini_summary(paper: dict[str, Any], config: dict[str, Any]) -> dict[str, str] | None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_config = config.get("gemini", {})
    if not api_key or not gemini_config.get("enable_if_key_present", True):
        return None
    try:
        model = gemini_config.get("model", "gemini-3.1-flash-lite")
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        prompt = (
            "请用中文分析下面论文，并只用 JSON 返回，键名为 problem, contribution。"
            "problem 回答“它真正想解决的问题是什么？”，要指出论文试图处理的核心科学或工程问题。"
            "contribution 回答“它声称的贡献是什么？”，要说明作者声称的新材料、新方法、新机制或新证据。"
            "不要直接粘贴英文摘要，不要编造摘要中没有的信息。\n\n"
            f"标题：{paper.get('title')}\n"
            f"期刊：{paper.get('venue')}\n"
            f"日期：{paper.get('published_date')}\n"
            f"DOI URL：{_doi_url(paper.get('doi', '')) or '无'}\n"
            f"摘要：{paper.get('abstract')}\n"
            "研究背景：复合固态电解质、聚合物电解质、锂离子传导机理、陶瓷填料界面效应。"
        )
        response = requests.post(
            endpoint,
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                },
            },
            timeout=config.get("search", {}).get("request_timeout", 20),
        )
        response.raise_for_status()
        parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        payload = _json_from_model_text(text)
        return {key: str(payload.get(key, "")) for key in ["problem", "contribution"]}
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        LOGGER.warning("Gemini summary failed for %r: %s", paper.get("title"), exc)
        return None


def summarize_paper(paper: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    return _gemini_summary(paper, config) or _rule_based_summary(paper, config)


def enrich_papers_with_summaries(papers: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for paper in papers:
        item = dict(paper)
        item["analysis"] = summarize_paper(item, config)
        enriched.append(item)
    return enriched


def _analysis_for_report(paper: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    analysis = paper.get("analysis")
    if isinstance(analysis, dict) and analysis.get("problem") and analysis.get("contribution"):
        return {
            "problem": str(analysis["problem"]),
            "contribution": str(analysis["contribution"]),
        }
    return _rule_based_summary(paper, config)


def _doi_markdown(doi: str) -> str:
    doi_url = _doi_url(doi)
    if not doi_url:
        return "无"
    return f"[{doi_url}]({doi_url})"


def _journal_metrics_text(paper: dict[str, Any]) -> str:
    try:
        impact_factor = float(paper.get("impact_factor"))
    except (TypeError, ValueError):
        impact_factor = 0.0
    if impact_factor <= 0:
        return "未获取"

    impact_factor_text = f"{impact_factor:.3f}".rstrip("0").rstrip(".")
    jcr_quartile = str(paper.get("jcr_quartile") or "").strip()
    source = str(paper.get("impact_factor_source") or "").strip()
    parts = [impact_factor_text, jcr_quartile or "JCR 未获取"]
    suffix = f"（{source}）" if source else ""
    return " / ".join(parts) + suffix


def render_markdown_report(
    papers: list[dict[str, Any]],
    config: dict[str, Any],
    report_date: date | None = None,
    total_found: int | None = None,
    run_report: dict[str, Any] | None = None,
) -> str:
    report_date = report_date or date.today()
    total_found = total_found if total_found is not None else len(papers)
    lines = [
        "# 每周文献推送报告",
        "",
        f"报告日期：{report_date.isoformat()}",
        "",
        f"本周共检索到 {total_found} 篇候选论文，经过筛选后推荐 {len(papers)} 篇高质量文献。",
        "",
    ]

    if not papers:
        lines.extend(["本周未筛选到足够相关的新论文。", ""])
        _append_run_report(lines, run_report)
        return "\n".join(lines)

    for index, paper in enumerate(papers, start=1):
        analysis = _analysis_for_report(paper, config)
        lines.extend(
            [
                f"## {index}. {paper.get('title') or '未命名论文'}",
                "",
                f"**作者**：{_authors_text(paper.get('authors', []))}",
                f"**期刊/平台**：{paper.get('venue') or paper.get('source') or '未知'}",
                f"**SCI 影响因子 / JCR 分区**：{_journal_metrics_text(paper)}",
                f"**发表时间**：{paper.get('published_date') or '未知'}",
                f"**DOI**：{_doi_markdown(paper.get('doi', ''))}",
                f"**相关性评分**：{paper.get('score', 0)}/10",
                "",
                "### 1. 它真正想解决的问题是什么？",
                "",
                analysis["problem"],
                "",
                "### 2. 它声称的贡献是什么？",
                "",
                analysis["contribution"],
                "",
            ]
        )
    _append_run_report(lines, run_report)
    return "\n".join(lines)


def _append_run_report(lines: list[str], run_report: dict[str, Any] | None) -> None:
    if not run_report:
        return
    lines.extend(
        [
            "## 运行报告",
            "",
            f"**检索时间范围**：{run_report.get('start_date', '未知')} 至 {run_report.get('end_date', '未知')}",
            f"**原始检索结果**：{run_report.get('raw_count', 0)} 条",
            f"**去重后结果**：{run_report.get('unique_count', 0)} 条",
            f"**未推送过结果**：{run_report.get('unseen_count', 0)} 条",
            f"**本次推荐结果**：{run_report.get('selected_count', 0)} 条",
            "",
            "| 数据库 | API 调用状态 | 检索结果数 | 备注 |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for source in run_report.get("sources", []):
        lines.append(
            "| {source} | {status} | {count} | {note} |".format(
                source=str(source.get("source", "未知")).replace("|", "\\|"),
                status=str(source.get("status", "未知")).replace("|", "\\|"),
                count=int(source.get("returned_count", 0) or 0),
                note=str(source.get("note", "")).replace("|", "\\|"),
            )
        )
    lines.append("")
    journal_metrics = run_report.get("journal_metrics") or {}
    if journal_metrics:
        lines.extend(
            [
                "",
                "**期刊指标查询**：{status}；查询 {queried} 个期刊，匹配 {matched} 篇论文。{note}".format(
                    status=str(journal_metrics.get("status", "未知")),
                    queried=int(journal_metrics.get("queried_count", 0) or 0),
                    matched=int(journal_metrics.get("matched_count", 0) or 0),
                    note=str(journal_metrics.get("note", "")),
                ),
                "",
            ]
        )


def markdown_to_html(markdown_text: str) -> str:
    body = markdown.markdown(markdown_text, extensions=["extra", "sane_lists"])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.65; color: #1f2933; max-width: 860px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 26px; border-bottom: 2px solid #d9e2ec; padding-bottom: 12px; }}
    h2 {{ font-size: 21px; margin-top: 32px; color: #102a43; }}
    h3 {{ font-size: 17px; margin-top: 20px; color: #334e68; }}
    a {{ color: #0969da; }}
    strong {{ color: #243b53; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def save_reports(markdown_text: str, report_dir: Path, report_date: date | None = None) -> tuple[Path, Path]:
    report_date = report_date or date.today()
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_md = report_dir / "weekly_report.md"
    latest_html = report_dir / "weekly_report.html"
    dated_md = report_dir / f"weekly_report_{report_date.isoformat()}.md"
    dated_html = report_dir / f"weekly_report_{report_date.isoformat()}.html"
    html_text = markdown_to_html(markdown_text)
    for path, content in [(latest_md, markdown_text), (dated_md, markdown_text), (latest_html, html_text), (dated_html, html_text)]:
        path.write_text(content, encoding="utf-8")
    return latest_md, latest_html


def plain_text_preview(markdown_text: str) -> str:
    return html.unescape(markdown_text.replace("#", "").strip())
