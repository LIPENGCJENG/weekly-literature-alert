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
            }
        ],
        config,
        report_date=date(2026, 6, 16),
        total_found=1,
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
