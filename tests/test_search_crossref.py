from datetime import date

from src.search_crossref import search_crossref


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "items": [
                    {
                        "title": ["PEO based composite polymer electrolyte with ceramic filler"],
                        "author": [{"given": "Example", "family": "Author"}],
                        "container-title": ["Journal of Power Sources"],
                        "published-online": {"date-parts": [[2026, 6, 12]]},
                        "DOI": "10.1000/crossref-example",
                        "URL": "https://doi.org/10.1000/crossref-example",
                        "abstract": "Solid polymer electrolyte with ceramic filler.",
                        "is-referenced-by-count": 7,
                        "subject": ["Materials Chemistry"],
                    }
                ]
            }
        }


class FakeSession:
    def __init__(self):
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_params = params
        return FakeResponse()


def test_crossref_search_normalizes_results():
    session = FakeSession()
    results = search_crossref(
        {
            "profile": {"email_to": "tao@example.edu"},
            "search": {"max_results_per_source": 10, "request_timeout": 5},
            "keywords": {"include": ["PEO LiTFSI"]},
        },
        date(2026, 6, 1),
        date(2026, 6, 16),
        session=session,
    )

    assert len(results) == 1
    assert results[0]["source"] == "Crossref"
    assert results[0]["title"] == "PEO based composite polymer electrolyte with ceramic filler"
    assert results[0]["authors"] == ["Example Author"]
    assert results[0]["published_date"] == "2026-06-12"
    assert results[0]["doi"] == "10.1000/crossref-example"
    assert results[0]["citation_count"] == 7
    assert "from-pub-date:2026-06-01" in session.last_params["filter"]
    assert session.last_params["mailto"] == "tao@example.edu"
