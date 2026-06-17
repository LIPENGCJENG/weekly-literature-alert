from datetime import date

from src.search_semantic_scholar import search_semantic_scholar


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": [
                {
                    "paperId": "s2-123",
                    "title": "Ceramic filler interface in PEO LiTFSI composite polymer electrolyte",
                    "authors": [{"name": "Example Author"}],
                    "venue": "Energy Storage Materials",
                    "publicationDate": "2026-06-12",
                    "externalIds": {"DOI": "10.1000/s2-example"},
                    "url": "https://www.semanticscholar.org/paper/s2-123",
                    "abstract": "Lithium ion transport at a polymer ceramic interface.",
                    "citationCount": 5,
                    "influentialCitationCount": 1,
                    "fieldsOfStudy": ["Materials Science"],
                }
            ]
        }


class FakeSession:
    def __init__(self):
        self.last_headers = None
        self.last_params = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.last_headers = headers
        self.last_params = params
        return FakeResponse()


def test_semantic_scholar_search_skips_without_key(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    assert (
        search_semantic_scholar(
            {"keywords": {"include": ["PEO LiTFSI"]}},
            date(2026, 6, 1),
            date(2026, 6, 16),
        )
        == []
    )


def test_semantic_scholar_search_uses_x_api_key_header(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")
    session = FakeSession()

    results = search_semantic_scholar(
        {
            "search": {
                "max_results_per_source": 10,
                "request_timeout": 5,
                "semantic_scholar_min_interval_seconds": 0,
            },
            "keywords": {"include": ["PEO LiTFSI"]},
        },
        date(2026, 6, 1),
        date(2026, 6, 16),
        session=session,
    )

    assert len(results) == 1
    assert results[0]["source"] == "Semantic Scholar"
    assert results[0]["doi"] == "10.1000/s2-example"
    assert results[0]["influential_citation_count"] == 1
    assert session.last_headers["x-api-key"] == "test-key"
    assert session.last_params["fields"]
