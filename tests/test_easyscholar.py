from src.easyscholar import enrich_papers_with_journal_metrics, query_publication_rank
from src.rank_papers import score_paper


class FakeEasyScholarResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "code": 200,
            "data": {
                "publicationName": "Energy Storage Materials",
                "sciif": "18.9",
                "jcr": "Q1",
            },
        }


class FakeEasyScholarSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeEasyScholarResponse()


def test_query_publication_rank_parses_sci_if_and_jcr(monkeypatch):
    monkeypatch.setenv("EASYSCHOLAR_SECRET_KEY", "test-secret")
    session = FakeEasyScholarSession()

    metrics = query_publication_rank("Energy Storage Materials", {"search": {"request_timeout": 5}}, session=session)

    assert metrics["impact_factor"] == 18.9
    assert metrics["jcr_quartile"] == "Q1"
    assert metrics["impact_factor_source"] == "EasyScholar"
    assert session.calls[0]["params"] == {
        "secretKey": "test-secret",
        "publicationName": "Energy Storage Materials",
    }


def test_enriched_impact_factor_is_used_for_scoring(monkeypatch):
    monkeypatch.setenv("EASYSCHOLAR_SECRET_KEY", "test-secret")
    config = {
        "search": {"request_timeout": 5},
        "easyscholar": {"min_interval_seconds": 0},
        "keywords": {"include": ["composite solid electrolyte"], "exclude": []},
        "venues": {"impact_factors": {"Energy Storage Materials": 1.0}},
        "ranking": {
            "weight_title_relevance": 0.7,
            "weight_impact_factor": 0.3,
            "default_impact_factor": 1.0,
            "max_impact_factor": 20.0,
        },
    }
    papers = [
        {
            "title": "Composite solid electrolyte",
            "venue": "Energy Storage Materials",
        }
    ]

    enriched, stats = enrich_papers_with_journal_metrics(papers, config, session=FakeEasyScholarSession())
    scored = score_paper(enriched[0], config)

    assert stats["status"] == "成功"
    assert stats["matched_count"] == 1
    assert scored["impact_factor"] == 18.9
    assert scored["impact_factor_source"] == "EasyScholar"
    assert scored["score_breakdown"]["impact_factor_value"] == 18.9
