import html
import json
import logging
import os
import re
import time
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


def _email_language(config: dict[str, Any]) -> str:
    language = str(config.get("email", {}).get("language", "Chinese")).strip().lower()
    if language in {"english", "en", "英语"}:
        return "en"
    return "zh"


def _is_english(config: dict[str, Any]) -> bool:
    return _email_language(config) == "en"


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


def _authors_text(authors: list[str], limit: int = 6, english: bool = False) -> str:
    if not authors:
        return "Unknown" if english else "未知"
    if len(authors) <= limit:
        return ", ".join(authors)
    suffix = " et al." if english else " 等"
    return ", ".join(authors[:limit]) + suffix


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


def _summary_signals(paper: dict[str, Any], english: bool = False) -> list[str]:
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
        value = term if english else translation
        if _contains_term(text, term) and value not in signals:
            signals.append(value)
    return signals


def _rule_based_summary(paper: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    include_terms = _matched_terms(paper, config.get("keywords", {}).get("include", []))
    boost_terms = _matched_terms(paper, config.get("ranking", {}).get("doctoral_boost_terms", []))
    english = _is_english(config)
    topic_terms = (include_terms + boost_terms) if english else _translated_terms(include_terms + boost_terms)
    if english:
        topic = ", ".join(topic_terms[:5]) or "the configured research topic"
        signals = ", ".join(_summary_signals(paper, english=True)[:5])
    else:
        topic = "、".join(topic_terms[:5]) or "复合固态电解质与锂离子传输"
        signals = "、".join(_summary_signals(paper)[:5])

    if english:
        if paper.get("abstract"):
            problem = (
                f"It appears to address a key limitation related to {topic}. "
                f"From the title and abstract, the problem centers on "
                f"{signals or 'materials design, performance evaluation, and mechanistic interpretation'}. "
                "The available metadata suggests that the authors are trying to connect material structure, "
                "interfacial behavior, and ion-transport performance more clearly."
            )
            contribution = (
                f"It claims to propose or validate a design, characterization, or mechanistic analysis route "
                f"around {topic}, supported by "
                f"{signals or 'performance data and structural analysis'}. "
                "The strength of the claimed contribution should still be checked against the full text, "
                "especially controls, experimental conditions, and mechanistic evidence."
            )
            conclusion = (
                f"Its main conclusions likely concern performance improvement or mechanism clarification in "
                f"{topic}. Based on the accessible information, the evidence mainly rests on "
                f"{signals or 'structural characterization, performance testing, and mechanistic analysis'}; "
                "the full paper should be checked to see whether competing explanations are adequately excluded."
            )
        else:
            problem = (
                "The public APIs did not return a complete abstract. "
                f"Based on the title, venue, and metadata, the paper appears to focus on {topic}, "
                "but the exact problem requires checking the full text."
            )
            contribution = (
                "Because the abstract is unavailable, it can only be inferred that the paper may claim progress "
                "in materials design, performance improvement, or mechanistic interpretation. "
                "The full text should be checked for the actual method, evidence, and novelty."
            )
            conclusion = (
                "Because the abstract is unavailable, the main conclusions cannot be judged reliably. "
                "From the title alone, they may involve improved material performance, interfacial stability, "
                "or ion-transport behavior."
            )
        return {
            "problem": problem,
            "contribution": contribution,
            "conclusion": conclusion,
        }

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
        conclusion = (
            f"它的主要结论大概率围绕{topic}体系的性能改善或机制解释展开。"
            f"从可获取信息看，结论证据主要落在{signals or '结构表征、性能测试和机理分析'}上；"
            "建议阅读全文确认作者是否充分排除了其他解释。"
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
        conclusion = (
            "由于缺少摘要，暂时无法可靠判断主要结论。"
            "目前只能根据题名推测其结论可能涉及材料性能、界面稳定性或离子传输表现的改善。"
        )
    return {
        "problem": problem,
        "contribution": contribution,
        "conclusion": conclusion,
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


def _gemini_summary(
    paper: dict[str, Any],
    config: dict[str, Any],
    stats: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_config = config.get("gemini", {})
    if not api_key or not gemini_config.get("enable_if_key_present", True):
        return None
    retry_attempts = max(1, int(gemini_config.get("retry_attempts", 1)))
    retry_backoff = max(0.0, float(gemini_config.get("retry_backoff_seconds", 20)))
    try:
        model = gemini_config.get("model", "gemini-3.1-flash-lite")
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        doi_url = _doi_url(paper.get("doi", "")) or "无"
        if _is_english(config):
            prompt = (
                f"You are now acting as a strict reviewer. For this paper {doi_url}, do not summarize the paper. "
                "Instead, answer three questions:\n"
                "1. What problem is it really trying to solve?\n"
                "2. What contribution does it claim?\n"
                "3. What are its main conclusions?\n\n"
                "Answer in English and return JSON only, with exactly these keys: problem, contribution, conclusion. "
                "Be restrained and specific like a reviewer, and distinguish the authors' claims from what is "
                "actually supported by evidence. Do not paste the abstract, and do not invent information that is "
                "not available from the DOI page, title, or abstract.\n\n"
                f"Title: {paper.get('title')}\n"
                f"Venue: {paper.get('venue')}\n"
                f"Date: {paper.get('published_date')}\n"
                f"DOI URL: {doi_url}\n"
                f"Abstract: {paper.get('abstract')}\n"
                "Research context: composite solid electrolytes, polymer electrolytes, lithium-ion conduction "
                "mechanisms, and ceramic filler interface effects."
            )
        else:
            prompt = (
                f"你现在扮演一个严格的审稿人。对于这篇论文 {doi_url}，不要总结这篇论文，"
                "而是回答三个问题：\n"
                "1. 它真正想解决的问题是什么？\n"
                "2. 它声称的贡献是什么？\n"
                "3. 它的主要结论是什么？\n\n"
                "请用中文回答，并只用 JSON 返回，键名必须为 problem, contribution, conclusion。"
                "回答要像审稿人一样克制、具体，区分作者声称的内容和已经被证据支持的内容。"
                "不要直接粘贴英文摘要，不要编造 DOI 页面、题名或摘要中没有的信息。\n\n"
                f"标题：{paper.get('title')}\n"
                f"期刊：{paper.get('venue')}\n"
                f"日期：{paper.get('published_date')}\n"
                f"DOI URL：{doi_url}\n"
                f"摘要：{paper.get('abstract')}\n"
                "研究背景：复合固态电解质、聚合物电解质、锂离子传导机理、陶瓷填料界面效应。"
            )
        for attempt in range(1, retry_attempts + 1):
            try:
                if stats is not None:
                    stats["request_count"] = int(stats.get("request_count", 0)) + 1
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
                LOGGER.info("Gemini summary generated for %r", paper.get("title"))
                return {key: str(payload.get(key, "")) for key in ["problem", "contribution", "conclusion"]}
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 429 and stats is not None:
                    stats["rate_limited_count"] = int(stats.get("rate_limited_count", 0)) + 1
                if status_code == 429 and attempt < retry_attempts:
                    retry_after = exc.response.headers.get("Retry-After", "") if exc.response is not None else ""
                    try:
                        wait_seconds = float(retry_after)
                    except ValueError:
                        wait_seconds = retry_backoff * attempt
                    LOGGER.warning(
                        "Gemini rate limited for %r; retrying in %.1f seconds.",
                        paper.get("title"),
                        wait_seconds,
                    )
                    time.sleep(wait_seconds)
                    continue
                raise
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        LOGGER.warning("Gemini summary failed for %r: %s", paper.get("title"), exc)
        return None


def _gemini_is_enabled(config: dict[str, Any]) -> bool:
    gemini_config = config.get("gemini", {})
    return bool(os.getenv("GEMINI_API_KEY", "") and gemini_config.get("enable_if_key_present", True))


def _gemini_min_interval(config: dict[str, Any]) -> float:
    return max(0.0, float(config.get("gemini", {}).get("min_interval_seconds", 0)))


def summarize_paper(paper: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    return _gemini_summary(paper, config) or _rule_based_summary(paper, config)


def _gemini_disabled_note(config: dict[str, Any]) -> str:
    if _is_english(config):
        if not os.getenv("GEMINI_API_KEY", ""):
            return "Missing GEMINI_API_KEY; using rule-based analysis"
        if not config.get("gemini", {}).get("enable_if_key_present", True):
            return "Gemini is disabled in config.yaml; using rule-based analysis"
        return "Gemini was not called; using rule-based analysis"
    if not os.getenv("GEMINI_API_KEY", ""):
        return "缺少 GEMINI_API_KEY，使用规则分析"
    if not config.get("gemini", {}).get("enable_if_key_present", True):
        return "Gemini 已在 config.yaml 中关闭，使用规则分析"
    return "Gemini 未调用，使用规则分析"


def _finalize_gemini_stats(stats: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    attempted = int(stats.get("attempted_count", 0))
    success = int(stats.get("success_count", 0))
    failed = int(stats.get("failed_count", 0))
    fallback = int(stats.get("fallback_count", 0))
    requests_count = int(stats.get("request_count", 0))
    rate_limited = int(stats.get("rate_limited_count", 0))

    english = _is_english(config)
    if attempted == 0:
        stats["status"] = "Not called" if english else "未调用"
        stats["note"] = stats.get("note") or ("Gemini was not called" if english else "Gemini 未调用")
    elif english and failed and success:
        stats["status"] = "Partial success"
        stats["note"] = (
            f"Gemini enabled; attempted {attempted} final recommended papers, "
            f"{success} succeeded, {failed} failed, {fallback} used rule-based fallback; "
            f"{requests_count} HTTP requests, {rate_limited} rate-limit responses"
        )
    elif english and failed:
        stats["status"] = "Failed"
        stats["note"] = (
            f"Gemini enabled; attempted {attempted} final recommended papers, all failed and used "
            f"rule-based fallback; {requests_count} HTTP requests, {rate_limited} rate-limit responses"
        )
    elif english:
        stats["status"] = "Success"
        stats["note"] = (
            f"Gemini enabled; successfully analyzed {success} final recommended papers; "
            f"{requests_count} HTTP requests, {rate_limited} rate-limit responses"
        )
    elif failed and success:
        stats["status"] = "部分成功"
        stats["note"] = (
            f"Gemini 已启用；尝试分析 {attempted} 篇最终推荐论文，"
            f"{success} 篇成功，{failed} 篇失败，回退 {fallback} 篇；"
            f"HTTP 请求 {requests_count} 次，429 限流 {rate_limited} 次"
        )
    elif failed:
        stats["status"] = "失败"
        stats["note"] = (
            f"Gemini 已启用；尝试分析 {attempted} 篇最终推荐论文，全部失败并回退规则分析；"
            f"HTTP 请求 {requests_count} 次，429 限流 {rate_limited} 次"
        )
    else:
        stats["status"] = "成功"
        stats["note"] = (
            f"Gemini 已启用；成功分析 {success} 篇最终推荐论文；"
            f"HTTP 请求 {requests_count} 次，429 限流 {rate_limited} 次"
        )
    return stats


def enrich_papers_with_summaries(
    papers: list[dict[str, Any]],
    config: dict[str, Any],
    include_stats: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    gemini_enabled = _gemini_is_enabled(config)
    min_interval = _gemini_min_interval(config) if gemini_enabled else 0.0
    stats: dict[str, Any] = {
        "source": "Gemini",
        "status": "未调用",
        "attempted_count": 0,
        "request_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "fallback_count": 0,
        "rate_limited_count": 0,
        "note": "",
    }
    if not gemini_enabled:
        stats["fallback_count"] = len(papers)
        stats["note"] = _gemini_disabled_note(config)

    for index, paper in enumerate(papers):
        if index and min_interval:
            time.sleep(min_interval)
        item = dict(paper)
        if gemini_enabled:
            stats["attempted_count"] += 1
            gemini_analysis = _gemini_summary(item, config, stats=stats)
            if gemini_analysis:
                stats["success_count"] += 1
                item["analysis"] = gemini_analysis
                item["analysis_source"] = "Gemini"
            else:
                stats["failed_count"] += 1
                stats["fallback_count"] += 1
                item["analysis"] = _rule_based_summary(item, config)
                item["analysis_source"] = "规则回退"
        else:
            item["analysis"] = _rule_based_summary(item, config)
            item["analysis_source"] = "规则回退"
        enriched.append(item)
    stats = _finalize_gemini_stats(stats, config)
    if include_stats:
        return enriched, stats
    return enriched


def _analysis_for_report(paper: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    analysis = paper.get("analysis")
    if (
        isinstance(analysis, dict)
        and analysis.get("problem")
        and analysis.get("contribution")
        and analysis.get("conclusion")
    ):
        return {
            "problem": str(analysis["problem"]),
            "contribution": str(analysis["contribution"]),
            "conclusion": str(analysis["conclusion"]),
        }
    return _rule_based_summary(paper, config)


def _doi_markdown(doi: str, english: bool = False) -> str:
    doi_url = _doi_url(doi)
    if not doi_url:
        return "None" if english else "无"
    return f"[{doi_url}]({doi_url})"


def _journal_metrics_text(paper: dict[str, Any], english: bool = False) -> str:
    try:
        impact_factor = float(paper.get("impact_factor"))
    except (TypeError, ValueError):
        impact_factor = 0.0
    if impact_factor <= 0:
        return "Not available" if english else "未获取"

    impact_factor_text = f"{impact_factor:.3f}".rstrip("0").rstrip(".")
    jcr_quartile = str(paper.get("jcr_quartile") or "").strip()
    source = str(paper.get("impact_factor_source") or "").strip()
    parts = [impact_factor_text, jcr_quartile or ("JCR not available" if english else "JCR 未获取")]
    suffix = f"({source})" if english and source else f"（{source}）" if source else ""
    return " / ".join(parts) + suffix


def _status_text(value: Any, english: bool = False) -> str:
    text = str(value or ("Unknown" if english else "未知"))
    if not english:
        return text
    return {
        "成功": "Success",
        "失败": "Failed",
        "部分成功": "Partial success",
        "未调用": "Not called",
        "未知": "Unknown",
    }.get(text, text)


def _note_text(value: Any, english: bool = False) -> str:
    text = str(value or "")
    if not english:
        return text
    replacements = [
        ("缺少 SEMANTIC_SCHOLAR_API_KEY", "Missing SEMANTIC_SCHOLAR_API_KEY"),
        ("缺少 ELSEVIER_API_KEY", "Missing ELSEVIER_API_KEY"),
        ("缺少 EASYSCHOLAR_SECRET_KEY", "Missing EASYSCHOLAR_SECRET_KEY"),
        ("使用配置表影响因子作为备用值", "using configured impact factors as fallback"),
        ("API 已成功调用", "API called successfully"),
        ("API 调用失败", "API call failed"),
        ("API 已调用", "API called"),
        ("次成功", "successful request(s)"),
        ("次失败", "failed request(s)"),
        ("篇论文匹配到影响因子", "paper(s) matched impact factors"),
    ]
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def render_markdown_report(
    papers: list[dict[str, Any]],
    config: dict[str, Any],
    report_date: date | None = None,
    total_found: int | None = None,
    run_report: dict[str, Any] | None = None,
) -> str:
    report_date = report_date or date.today()
    total_found = total_found if total_found is not None else len(papers)
    english = _is_english(config)
    if english:
        lines = [
            "# Weekly Literature Alert",
            "",
            f"Report date: {report_date.isoformat()}",
            "",
            f"This run found {total_found} candidate papers and recommends {len(papers)} high-priority papers after filtering.",
            "",
        ]
    else:
        lines = [
            "# 每周文献推送报告",
            "",
            f"报告日期：{report_date.isoformat()}",
            "",
            f"本周共检索到 {total_found} 篇候选论文，经过筛选后推荐 {len(papers)} 篇高质量文献。",
            "",
        ]

    if not papers:
        lines.extend(["No sufficiently relevant new papers were selected in this run." if english else "本周未筛选到足够相关的新论文。", ""])
        _append_run_report(lines, run_report, english=english)
        return "\n".join(lines)

    for index, paper in enumerate(papers, start=1):
        analysis = _analysis_for_report(paper, config)
        lines.extend(
            [
                f"## {index}. {paper.get('title') or ('Untitled paper' if english else '未命名论文')}",
                "",
                (
                    f"**Authors**: {_authors_text(paper.get('authors', []), english=True)}"
                    if english
                    else f"**作者**：{_authors_text(paper.get('authors', []))}"
                ),
                (
                    f"**Journal/Platform**: {paper.get('venue') or paper.get('source') or 'Unknown'}"
                    if english
                    else f"**期刊/平台**：{paper.get('venue') or paper.get('source') or '未知'}"
                ),
                (
                    f"**SCI Impact Factor / JCR Quartile**: {_journal_metrics_text(paper, english=True)}"
                    if english
                    else f"**SCI 影响因子 / JCR 分区**：{_journal_metrics_text(paper)}"
                ),
                (
                    f"**Publication Date**: {paper.get('published_date') or 'Unknown'}"
                    if english
                    else f"**发表时间**：{paper.get('published_date') or '未知'}"
                ),
                f"**DOI**: {_doi_markdown(paper.get('doi', ''), english=True)}" if english else f"**DOI**：{_doi_markdown(paper.get('doi', ''))}",
                f"**Relevance Score**: {paper.get('score', 0)}/10" if english else f"**相关性评分**：{paper.get('score', 0)}/10",
                "",
                "### 1. What problem is it really trying to solve?" if english else "### 1. 它真正想解决的问题是什么？",
                "",
                analysis["problem"],
                "",
                "### 2. What contribution does it claim?" if english else "### 2. 它声称的贡献是什么？",
                "",
                analysis["contribution"],
                "",
                "### 3. What are its main conclusions?" if english else "### 3. 它的主要结论是什么？",
                "",
                analysis["conclusion"],
                "",
            ]
        )
    _append_run_report(lines, run_report, english=english)
    return "\n".join(lines)


def _append_run_report(lines: list[str], run_report: dict[str, Any] | None, english: bool = False) -> None:
    if not run_report:
        return
    if english:
        lines.extend(
            [
                "## Run Report",
                "",
                f"**Search window**: {run_report.get('start_date', 'Unknown')} to {run_report.get('end_date', 'Unknown')}",
                f"**Raw search results**: {run_report.get('raw_count', 0)}",
                f"**After deduplication**: {run_report.get('unique_count', 0)}",
                f"**Not previously pushed**: {run_report.get('unseen_count', 0)}",
                f"**Recommended in this run**: {run_report.get('selected_count', 0)}",
                "",
                "| Database | API status | Results | Notes |",
                "| --- | --- | ---: | --- |",
            ]
        )
    else:
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
                status=_status_text(source.get("status", "未知"), english=english).replace("|", "\\|"),
                count=int(source.get("returned_count", 0) or 0),
                note=_note_text(source.get("note", ""), english=english).replace("|", "\\|"),
            )
        )
    lines.append("")
    journal_metrics = run_report.get("journal_metrics") or {}
    if journal_metrics:
        if english:
            lines.extend(
                [
                    "",
                    "**Journal metrics lookup**: {status}; queried {queried} journals, matched {matched} papers. {note}".format(
                        status=_status_text(journal_metrics.get("status", "未知"), english=True),
                        queried=int(journal_metrics.get("queried_count", 0) or 0),
                        matched=int(journal_metrics.get("matched_count", 0) or 0),
                        note=_note_text(journal_metrics.get("note", ""), english=True),
                    ),
                    "",
                ]
            )
        else:
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
    gemini_stats = run_report.get("gemini") or {}
    if gemini_stats:
        if english:
            lines.extend(
                [
                    "**Gemini API usage**: {status}; attempted {attempted} papers, {success} succeeded, {failed} failed, {fallback} used rule-based fallback; {requests} HTTP requests, {rate_limited} rate-limit responses. {note}".format(
                        status=_status_text(gemini_stats.get("status", "未知"), english=True),
                        attempted=int(gemini_stats.get("attempted_count", 0) or 0),
                        success=int(gemini_stats.get("success_count", 0) or 0),
                        failed=int(gemini_stats.get("failed_count", 0) or 0),
                        fallback=int(gemini_stats.get("fallback_count", 0) or 0),
                        requests=int(gemini_stats.get("request_count", 0) or 0),
                        rate_limited=int(gemini_stats.get("rate_limited_count", 0) or 0),
                        note=_note_text(gemini_stats.get("note", ""), english=True),
                    ),
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "**Gemini API 调用**：{status}；尝试 {attempted} 篇，成功 {success} 篇，失败 {failed} 篇，规则回退 {fallback} 篇；HTTP 请求 {requests} 次，429 限流 {rate_limited} 次。{note}".format(
                        status=str(gemini_stats.get("status", "未知")),
                        attempted=int(gemini_stats.get("attempted_count", 0) or 0),
                        success=int(gemini_stats.get("success_count", 0) or 0),
                        failed=int(gemini_stats.get("failed_count", 0) or 0),
                        fallback=int(gemini_stats.get("fallback_count", 0) or 0),
                        requests=int(gemini_stats.get("request_count", 0) or 0),
                        rate_limited=int(gemini_stats.get("rate_limited_count", 0) or 0),
                        note=str(gemini_stats.get("note", "")),
                    ),
                    "",
                ]
            )


def markdown_to_html(markdown_text: str, config: dict[str, Any] | None = None) -> str:
    lang = "en" if config and _is_english(config) else "zh-CN"
    body = markdown.markdown(markdown_text, extensions=["extra", "sane_lists"])
    return f"""<!doctype html>
<html lang="{lang}">
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


def save_reports(
    markdown_text: str,
    report_dir: Path,
    report_date: date | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    report_date = report_date or date.today()
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_md = report_dir / "weekly_report.md"
    latest_html = report_dir / "weekly_report.html"
    dated_md = report_dir / f"weekly_report_{report_date.isoformat()}.md"
    dated_html = report_dir / f"weekly_report_{report_date.isoformat()}.html"
    html_text = markdown_to_html(markdown_text, config=config)
    for path, content in [(latest_md, markdown_text), (dated_md, markdown_text), (latest_html, html_text), (dated_html, html_text)]:
        path.write_text(content, encoding="utf-8")
    return latest_md, latest_html


def plain_text_preview(markdown_text: str) -> str:
    return html.unescape(markdown_text.replace("#", "").strip())
