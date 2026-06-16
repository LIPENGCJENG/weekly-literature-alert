from datetime import date

from src.rank_papers import contains_term, deduplicate_papers, rank_papers, score_paper, title_similarity


CONFIG = {
    "search": {"days_back": 10},
    "keywords": {
        "include": ["composite solid electrolyte", "ceramic filler", "PEO LiTFSI"],
        "exclude": ["aqueous electrolyte"],
    },
    "venues": {"whitelist": ["Energy Storage Materials", "Journal of Power Sources"]},
    "ranking": {
        "weight_relevance": 0.45,
        "weight_venue": 0.30,
        "weight_recency": 0.15,
        "weight_citation_signal": 0.10,
        "doctoral_boost_terms": ["PEO", "LiTFSI", "space charge layer"],
    },
}


def test_doi_deduplication():
    papers = [
        {"title": "A", "doi": "10.1000/ABC", "url": "https://a"},
        {"title": "A duplicate", "doi": "https://doi.org/10.1000/abc", "url": "https://b"},
    ]
    assert len(deduplicate_papers(papers)) == 1


def test_title_similarity_deduplication():
    papers = [
        {"title": "Ceramic filler enhanced PEO LiTFSI composite solid electrolyte", "doi": "", "url": "https://a"},
        {"title": "Ceramic fillers enhanced PEO-LiTFSI composite solid electrolytes", "doi": "", "url": "https://b"},
    ]
    assert title_similarity(papers[0]["title"], papers[1]["title"]) > 0.9
    assert len(deduplicate_papers(papers, title_threshold=0.9)) == 1


def test_short_term_matching_uses_whole_words():
    assert contains_term("peo litfsi electrolyte", "PEO")
    assert not contains_term("people living near public transport", "PEO")


def test_boost_terms_alone_do_not_rank_paper():
    paper = {
        "title": "Public transport demand near urban regions",
        "abstract": "People living near stations are discussed.",
        "venue": "Transport",
        "published_date": "2026-06-15",
    }
    assert rank_papers([paper], CONFIG, end_date=date(2026, 6, 16)) == []


def test_scoring_prefers_relevant_high_quality_paper():
    relevant = {
        "title": "PEO LiTFSI composite solid electrolyte with ceramic filler interface",
        "abstract": "The space charge layer improves lithium ion transport.",
        "venue": "Energy Storage Materials",
        "published_date": "2026-06-15",
        "citation_count": 8,
    }
    irrelevant = {
        "title": "Aqueous electrolyte for supercapacitor",
        "abstract": "An aqueous electrolyte device.",
        "venue": "Unknown Journal",
        "published_date": "2026-06-15",
        "citation_count": 8,
    }
    assert score_paper(relevant, CONFIG, end_date=date(2026, 6, 16))["score"] > score_paper(irrelevant, CONFIG, end_date=date(2026, 6, 16))["score"]
    assert rank_papers([irrelevant, relevant], CONFIG, end_date=date(2026, 6, 16))[0]["title"] == relevant["title"]
