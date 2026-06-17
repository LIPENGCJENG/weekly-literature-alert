import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from src.main import search_all_sources


def test_search_all_sources_records_success_failure_and_missing_key(monkeypatch):
    def successful_source(config, start_date, end_date):
        return [{"title": "A"}]

    def failing_source(config, start_date, end_date):
        raise RuntimeError("boom")

    monkeypatch.delenv("MISSING_TEST_KEY", raising=False)
    monkeypatch.setattr(
        "src.main.SOURCE_DEFINITIONS",
        [
            {"name": "Success DB", "func": successful_source},
            {"name": "Missing Key DB", "func": successful_source, "required_env": "MISSING_TEST_KEY"},
            {"name": "Failing DB", "func": failing_source},
        ],
    )

    papers, stats = search_all_sources({}, date(2026, 6, 1), date(2026, 6, 16))

    assert papers == [{"title": "A"}]
    assert stats == [
        {"source": "Success DB", "status": "成功", "returned_count": 1, "note": "API 已成功调用"},
        {"source": "Missing Key DB", "status": "未调用", "returned_count": 0, "note": "缺少 MISSING_TEST_KEY"},
        {"source": "Failing DB", "status": "失败", "returned_count": 0, "note": "boom"},
    ]
