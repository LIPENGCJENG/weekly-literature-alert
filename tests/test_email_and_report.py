from datetime import date

from src.send_email import build_email_message
from src.summarize_papers import _gemini_summary, _json_from_model_text, markdown_to_html, render_markdown_report


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
    assert "A PEO based composite solid electrolyte is studied." not in markdown_report
    assert "它试图解决的是" in markdown_report
    assert "**链接**" not in markdown_report
    assert "https://example.org" not in markdown_report
    assert "[https://doi.org/10.1000/example](https://doi.org/10.1000/example)" in markdown_report
    assert "**SCI 影响因子 / JCR 分区**：18.9 / Q1（EasyScholar）" in markdown_report
    assert "https://doi.org/10.1000/example" in html
    assert "## 运行报告" in markdown_report
    assert "| OpenAlex | 成功 | 7 | API 已成功调用 |" in markdown_report
    assert "| Semantic Scholar | 未调用 | 0 | 缺少 SEMANTIC_SCHOLAR_API_KEY |" in markdown_report
    assert "期刊指标查询" in markdown_report
    assert "运行报告" in html
    assert "2026-06-16" in message["Subject"]
    assert message.is_multipart()


def test_gemini_json_code_fence_parsing():
    payload = _json_from_model_text(
        """```json
        {"problem": "真正要解决的问题", "contribution": "声称的贡献"}
        ```"""
    )
    assert payload["problem"] == "真正要解决的问题"
    assert payload["contribution"] == "声称的贡献"


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
                                "text": '{"problem": "真正要解决的问题", "contribution": "声称的贡献"}'
                            }
                        ]
                    }
                }
            ]
        }


def test_gemini_summary_uses_configured_flash_lite_model(monkeypatch):
    calls = {}

    def fake_post(url, params=None, json=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
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

    assert result == {"problem": "真正要解决的问题", "contribution": "声称的贡献"}
    assert "models/gemini-3.1-flash-lite:generateContent" in calls["url"]
    assert calls["params"] == {"key": "test-key"}
