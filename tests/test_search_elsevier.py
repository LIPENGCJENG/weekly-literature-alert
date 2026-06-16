from datetime import date

from src.search_elsevier import search_elsevier


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "search-results": {
                "entry": [
                    {
                        "eid": "2-s2.0-123",
                        "dc:title": "PEO based composite polymer electrolyte with ceramic filler",
                        "dc:creator": "Example Author",
                        "prism:publicationName": "Journal of Power Sources",
                        "prism:coverDate": "2026-06-12",
                        "prism:doi": "10.1000/example",
                        "prism:url": "https://api.elsevier.com/content/abstract/scopus_id/123",
                        "dc:description": "Solid polymer electrolyte with ceramic filler.",
                        "citedby-count": "3",
                        "subtypeDescription": "Article",
                    }
                ]
            }
        }


class FakeSession:
    def __init__(self):
        self.last_headers = None
        self.last_params = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.last_params = params
        self.last_headers = headers
        return FakeResponse()


def test_elsevier_search_skips_without_key(monkeypatch):
    monkeypatch.delenv("ELSEVIER_API_KEY", raising=False)
    assert search_elsevier({"keywords": {"include": ["PEO LiTFSI"]}}, date(2026, 6, 1), date(2026, 6, 16)) == []


def test_elsevier_search_normalizes_results(monkeypatch):
    monkeypatch.setenv("ELSEVIER_API_KEY", "test-key")
    session = FakeSession()
    results = search_elsevier(
        {
            "search": {"max_results_per_source": 10, "request_timeout": 5},
            "keywords": {"include": ["PEO LiTFSI"]},
        },
        date(2026, 6, 1),
        date(2026, 6, 16),
        session=session,
    )
    assert len(results) == 1
    assert results[0]["source"] == "Elsevier Scopus"
    assert results[0]["doi"] == "10.1000/example"
    assert results[0]["citation_count"] == 3
    assert session.last_headers["X-ELS-APIKey"] == "test-key"
    assert "TITLE-ABS-KEY" in session.last_params["query"]
