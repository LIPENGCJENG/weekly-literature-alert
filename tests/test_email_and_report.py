from datetime import date

from src.send_email import build_email_message
from src.summarize_papers import _json_from_model_text, markdown_to_html, render_markdown_report


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
    assert "A PEO based composite solid electrolyte is studied." not in markdown_report
    assert "该论文主要关注" in markdown_report
    assert "2026-06-16" in message["Subject"]
    assert message.is_multipart()


def test_gemini_json_code_fence_parsing():
    payload = _json_from_model_text(
        """```json
        {"summary": "中文总结", "inspiration": "博士课题启发"}
        ```"""
    )
    assert payload["summary"] == "中文总结"
    assert payload["inspiration"] == "博士课题启发"
