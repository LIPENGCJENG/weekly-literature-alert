from datetime import date

import requests

from src.send_email import build_email_message
from src.summarize_papers import (
    _gemini_summary,
    _json_from_model_text,
    enrich_papers_with_summaries,
    markdown_to_html,
    render_markdown_report,
)


def test_email_body_generation():
    config = {
        "profile": {"email_to": "tao@example.com"},
        "email": {"subject_prefix": "[每周文献推送]"},
        "keywords": {"include": ["composite solid electrolyte"]},
        "ranking": {"doctoral_boost_terms": ["PEO"]},
    }
    markdown_report = render_markdown_report(
        [
            {
                "title": "Composite solid electrolyte paper",
                "authors": ["A", "B"],
                "venue": "Energy Storage Materials",
                "published_date": "2026-06-15",
                "doi": "10.1000/example",
                "url": "https://example.org",
                "abstract": "A PEO based composite solid electrolyte is studied.",
                "score": 9.1,
                "impact_factor": 18.9,
                "jcr_quartile": "Q1",
                "impact_factor_source": "EasyScholar",
            }
        ],
        config,
        report_date=date(2026, 6, 16),
        total_found=1,
        run_report={
            "start_date": "2026-06-06",
            "end_date": "2026-06-16",
            "raw_count": 12,
            "unique_count": 10,
            "unseen_count": 8,
            "selected_count": 1,
            "sources": [
                {"source": "OpenAlex", "status": "成功", "returned_count": 7, "note": "API 已成功调用"},
                {"source": "Semantic Scholar", "status": "未调用", "returned_count": 0, "note": "缺少 SEMANTIC_SCHOLAR_API_KEY"},
            ],
            "journal_metrics": {
                "source": "EasyScholar JCR",
                "status": "成功",
                "queried_count": 1,
                "matched_count": 1,
                "note": "API 已调用，1 次成功，0 次失败；1 篇论文匹配到影响因子",
            },
            "gemini": {
                "source": "Gemini",
                "status": "部分成功",
                "attempted_count": 2,
                "request_count": 3,
                "success_count": 1,
                "failed_count": 1,
                "fallback_count": 1,
                "rate_limited_count": 1,
                "note": "Gemini 已启用；测试统计",
            },
        },
    )
    html = markdown_to_html(markdown_report)
    message = build_email_message(html, config, report_date=date(2026, 6, 16), markdown_body=markdown_report)
    assert "Composite solid electrolyte paper" in html
    assert "推荐理由" not in markdown_report
    assert "与我的研究方向的关系" not in markdown_report
    assert "中文总结" not in markdown_report
    assert "对博士课题的启发" not in markdown_report
    assert "### 1. 它真正想解决的问题是什么？" in markdown_report
    assert "### 2. 它声称的贡献是什么？" in markdown_report
    assert "### 3. 它的主要结论是什么？" in markdown_report
    assert "A PEO based composite solid electrolyte is studied." not in markdown_report
    assert "它试图解决的是" in markdown_report
    assert "它的主要结论" in markdown_report
    assert "**链接**" not in markdown_report
    assert "https://example.org" not in markdown_report
    assert "[https://doi.org/10.1000/example](https://doi.org/10.1000/example)" in markdown_report
    assert "**SCI 影响因子 / JCR 分区**：18.9 / Q1（EasyScholar）" in markdown_report
    assert "https://doi.org/10.1000/example" in html
    assert "## 运行报告" in markdown_report
    assert "| OpenAlex | 成功 | 7 | API 已成功调用 |" in markdown_report
    assert "| Semantic Scholar | 未调用 | 0 | 缺少 SEMANTIC_SCHOLAR_API_KEY |" in markdown_report
    assert "期刊指标查询" in markdown_report
    assert "Gemini API 调用" in markdown_report
    assert "尝试 2 篇，成功 1 篇，失败 1 篇，规则回退 1 篇" in markdown_report
    assert "运行报告" in html
    assert "2026-06-16" in message["Subject"]
    assert message.is_multipart()


def test_english_email_language_generation():
    config = {
        "profile": {"email_to": "reader@example.com"},
        "email": {"language": "English", "subject_prefix": "[每周文献推送]"},
        "keywords": {"include": ["composite solid electrolyte"]},
        "ranking": {"doctoral_boost_terms": ["PEO"]},
    }
    markdown_report = render_markdown_report(
        [
            {
                "title": "Composite solid electrolyte paper",
                "authors": ["A", "B"],
                "venue": "Energy Storage Materials",
                "published_date": "2026-06-15",
                "doi": "10.1000/example",
                "abstract": "A PEO based composite solid electrolyte is studied.",
                "score": 9.1,
                "impact_factor": 18.9,
                "jcr_quartile": "Q1",
                "impact_factor_source": "EasyScholar",
            }
        ],
        config,
        report_date=date(2026, 6, 16),
        total_found=1,
        run_report={
            "start_date": "2026-05-16",
            "end_date": "2026-06-16",
            "raw_count": 12,
            "unique_count": 10,
            "unseen_count": 8,
            "selected_count": 1,
            "sources": [
                {"source": "OpenAlex", "status": "成功", "returned_count": 7, "note": "API 已成功调用"},
            ],
            "journal_metrics": {
                "source": "EasyScholar JCR",
                "status": "成功",
                "queried_count": 1,
                "matched_count": 1,
                "note": "API 已调用，1 次成功，0 次失败；1 篇论文匹配到影响因子",
            },
            "gemini": {
                "source": "Gemini",
                "status": "成功",
                "attempted_count": 1,
                "request_count": 1,
                "success_count": 1,
                "failed_count": 0,
                "fallback_count": 0,
                "rate_limited_count": 0,
                "note": "Gemini enabled; successfully analyzed 1 final recommended papers",
            },
        },
    )
    html = markdown_to_html(markdown_report, config=config)
    message = build_email_message(html, config, report_date=date(2026, 6, 16), markdown_body=markdown_report)

    assert "# Weekly Literature Alert" in markdown_report
    assert "### 1. What problem is it really trying to solve?" in markdown_report
    assert "**SCI Impact Factor / JCR Quartile**: 18.9 / Q1(EasyScholar)" in markdown_report
    assert "## Run Report" in markdown_report
    assert "| OpenAlex | Success | 7 | API called successfully |" in markdown_report
    assert "Gemini API usage" in markdown_report
    assert '<html lang="en">' in html
    assert message["Subject"] == "[Weekly Literature Alert] Latest Literature Update - 2026-06-16"


def test_gemini_json_code_fence_parsing():
    payload = _json_from_model_text(
        """```json
        {"problem": "真正要解决的问题", "contribution": "声称的贡献", "conclusion": "主要结论"}
        ```"""
    )
    assert payload["problem"] == "真正要解决的问题"
    assert payload["contribution"] == "声称的贡献"
    assert payload["conclusion"] == "主要结论"


class FakeGeminiResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"problem": "真正要解决的问题", "contribution": "声称的贡献", "conclusion": "主要结论"}'
                            }
                        ]
                    }
                }
            ]
        }


class FakeRateLimitResponse:
    status_code = 429
    headers = {}

    def raise_for_status(self):
        raise requests.HTTPError("429 Client Error", response=self)


def test_gemini_summary_uses_configured_flash_lite_model(monkeypatch):
    calls = {}

    def fake_post(url, params=None, json=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        calls["json"] = json
        return FakeGeminiResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("src.summarize_papers.requests.post", fake_post)

    result = _gemini_summary(
        {
            "title": "Composite polymer electrolyte",
            "venue": "Energy Storage Materials",
            "published_date": "2026-06-17",
            "abstract": "A ceramic filler regulates lithium ion transport.",
        },
        {"gemini": {"model": "gemini-3.1-flash-lite"}, "search": {"request_timeout": 5}},
    )

    assert result == {"problem": "真正要解决的问题", "contribution": "声称的贡献", "conclusion": "主要结论"}
    assert "models/gemini-3.1-flash-lite:generateContent" in calls["url"]
    assert calls["params"] == {"key": "test-key"}
    prompt = calls["json"]["contents"][0]["parts"][0]["text"]
    assert "你现在扮演一个严格的审稿人" in prompt
    assert "不要总结这篇论文" in prompt
    assert "它的主要结论是什么？" in prompt


def test_gemini_summary_uses_english_prompt_when_configured(monkeypatch):
    calls = {}

    def fake_post(url, params=None, json=None, timeout=None):
        calls["json"] = json
        return FakeGeminiResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("src.summarize_papers.requests.post", fake_post)

    _gemini_summary(
        {
            "title": "Composite polymer electrolyte",
            "venue": "Energy Storage Materials",
            "published_date": "2026-06-17",
            "doi": "10.1000/example",
            "abstract": "A ceramic filler regulates lithium ion transport.",
        },
        {
            "email": {"language": "English"},
            "gemini": {"model": "gemini-3.1-flash-lite"},
            "search": {"request_timeout": 5},
        },
    )

    prompt = calls["json"]["contents"][0]["parts"][0]["text"]
    assert "You are now acting as a strict reviewer" in prompt
    assert "do not summarize the paper" in prompt
    assert "What are its main conclusions?" in prompt
    assert "Answer in English" in prompt
    assert "https://doi.org/10.1000/example" in prompt


def test_gemini_summary_retries_rate_limit(monkeypatch):
    calls = []
    sleeps = []

    def fake_post(url, params=None, json=None, timeout=None):
        calls.append(url)
        return FakeRateLimitResponse() if len(calls) == 1 else FakeGeminiResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("src.summarize_papers.requests.post", fake_post)
    monkeypatch.setattr("src.summarize_papers.time.sleep", sleeps.append)

    result = _gemini_summary(
        {"title": "Composite polymer electrolyte"},
        {
            "gemini": {
                "model": "gemini-3.1-flash-lite",
                "retry_attempts": 2,
                "retry_backoff_seconds": 3,
            },
            "search": {"request_timeout": 5},
        },
    )

    assert result == {"problem": "真正要解决的问题", "contribution": "声称的贡献", "conclusion": "主要结论"}
    assert len(calls) == 2
    assert sleeps == [3]


def test_render_report_does_not_call_gemini(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Gemini should only be called before rendering final selected papers.")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("src.summarize_papers.requests.post", fail_if_called)

    markdown_report = render_markdown_report(
        [
            {
                "title": "Composite solid electrolyte paper",
                "venue": "Energy Storage Materials",
                "abstract": "A ceramic filler regulates lithium ion transport.",
            }
        ],
        {
            "gemini": {"model": "gemini-3.1-flash-lite"},
            "keywords": {"include": ["composite solid electrolyte"]},
            "ranking": {"doctoral_boost_terms": []},
        },
        report_date=date(2026, 6, 16),
    )

    assert "Composite solid electrolyte paper" in markdown_report
    assert "它试图解决的是" in markdown_report


def test_enrich_summaries_calls_gemini_only_for_given_final_papers(monkeypatch):
    calls = []

    def fake_post(url, params=None, json=None, timeout=None):
        calls.append(json["contents"][0]["parts"][0]["text"])
        return FakeGeminiResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("src.summarize_papers.requests.post", fake_post)

    final_papers = [
        {"title": "Final selected paper 1", "doi": "10.1000/one"},
        {"title": "Final selected paper 2", "doi": "https://doi.org/10.1000/two"},
    ]
    enriched = enrich_papers_with_summaries(
        final_papers,
        {"gemini": {"model": "gemini-3.1-flash-lite"}, "search": {"request_timeout": 5}},
    )

    assert len(calls) == 2
    assert all("analysis" in paper for paper in enriched)
    assert "https://doi.org/10.1000/one" in calls[0]
    assert "https://doi.org/10.1000/two" in calls[1]


def test_enrich_summaries_returns_gemini_stats(monkeypatch):
    def fake_post(url, params=None, json=None, timeout=None):
        return FakeGeminiResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("src.summarize_papers.requests.post", fake_post)

    enriched, stats = enrich_papers_with_summaries(
        [{"title": "Final selected paper", "doi": "10.1000/one"}],
        {"gemini": {"model": "gemini-3.1-flash-lite"}, "search": {"request_timeout": 5}},
        include_stats=True,
    )

    assert enriched[0]["analysis_source"] == "Gemini"
    assert stats["status"] == "成功"
    assert stats["attempted_count"] == 1
    assert stats["request_count"] == 1
    assert stats["success_count"] == 1
    assert stats["failed_count"] == 0
    assert stats["fallback_count"] == 0
