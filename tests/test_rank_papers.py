from datetime import date

from src.rank_papers import contains_term, deduplicate_papers, rank_papers, score_paper, title_similarity
from src.main import select_papers


CONFIG = {
    "search": {"days_back": 10},
    "keywords": {
        "include": ["composite solid electrolyte", "solid polymer electrolyte", "ceramic filler", "PEO LiTFSI"],
        "exclude": ["aqueous electrolyte"],
    },
    "venues": {
        "impact_factors": {"Energy Storage Materials": 18.9, "Journal of Power Sources": 8.1},
        "whitelist": ["Energy Storage Materials", "Journal of Power Sources"],
    },
    "ranking": {
        "weight_title_relevance": 0.70,
        "weight_impact_factor": 0.30,
        "default_impact_factor": 1.0,
        "max_impact_factor": 20.0,
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


def test_scoring_uses_only_title_relevance_and_impact_factor():
    relevant = {
        "title": "PEO LiTFSI composite solid electrolyte with ceramic filler interface",
        "abstract": "This abstract should not affect the score.",
        "venue": "Energy Storage Materials",
        "published_date": "2020-01-01",
        "citation_count": 0,
    }
    same_title_lower_if = {
        **relevant,
        "venue": "Unknown Journal",
        "published_date": "2026-06-15",
        "citation_count": 1000,
    }
    scored = score_paper(relevant, CONFIG, end_date=date(2026, 6, 16))
    lower_if_score = score_paper(same_title_lower_if, CONFIG, end_date=date(2026, 6, 16))

    assert set(scored["score_breakdown"]) == {"title_relevance", "impact_factor", "impact_factor_value"}
    assert scored["score"] > lower_if_score["score"]
    assert rank_papers([same_title_lower_if, relevant], CONFIG, end_date=date(2026, 6, 16))[0]["venue"] == "Energy Storage Materials"


def test_select_papers_can_supplement_to_minimum_without_excluded_topics():
    config = {
        **CONFIG,
        "search": {"days_back": 30, "top_n": 10, "min_recommendations": 3},
    }
    relevant = {
        "title": "Ceramic filler enhanced composite solid electrolyte",
        "abstract": "Lithium ion transport is discussed.",
        "venue": "Energy Storage Materials",
        "published_date": "2026-06-15",
    }
    fallback = {
        "title": "Solid polymer electrolyte materials for lithium batteries",
        "abstract": "Mechanical and electrochemical properties of polymer electrolytes are reviewed.",
        "venue": "Journal of Power Sources",
        "published_date": "2026-06-14",
    }
    excluded = {
        "title": "Aqueous electrolyte for supercapacitor",
        "abstract": "Aqueous electrolyte device.",
        "venue": "Journal of Power Sources",
        "published_date": "2026-06-13",
    }
    ranked = rank_papers([relevant, fallback, excluded], config, end_date=date(2026, 6, 16))
    selected = select_papers([relevant, fallback, excluded], ranked, config, end_date=date(2026, 6, 16))

    assert len(selected) == 2
    assert selected[0]["title"] == relevant["title"]
    assert all("Aqueous" not in paper["title"] for paper in selected)
