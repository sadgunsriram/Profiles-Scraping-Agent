"""
Unit tests for experience date parsing and normalization.
"""

from skills.profile_scraper.experience_extractor import parse_experience_date_range
from skills.profile_scraper.set1_identity import parse_date_to_month_offset


def test_parse_experience_date_range_standard():
    res = parse_experience_date_range("Jan 2021 - Present · 3 yrs 8 mos")
    assert res is not None
    assert res["start_date"] == "Jan 2021"
    assert res["end_date"] == "Present"
    assert res["duration_text"] == "3 yrs 8 mos"


def test_parse_experience_date_range_years_only():
    res = parse_experience_date_range("2017 - 2021 · 4 yrs")
    assert res is not None
    assert res["start_date"] == "2017"
    assert res["end_date"] == "2021"
    assert res["duration_text"] == "4 yrs"


def test_parse_experience_date_range_endash():
    res = parse_experience_date_range("Mar 2019 – Nov 2022")
    assert res is not None
    assert res["start_date"] == "Mar 2019"
    assert res["end_date"] == "Nov 2022"


def test_parse_experience_date_range_invalid():
    assert parse_experience_date_range("") is None
    assert parse_experience_date_range("Software Engineer at Google") is None


def test_parse_date_to_month_offset_integration():
    # Start dates default to month 0 (January) if only year provided
    start_offset = parse_date_to_month_offset("Jan 2021", is_end_date=False)
    assert start_offset == 2021 * 12 + 0

    dec_offset = parse_date_to_month_offset("Dec 2021", is_end_date=False)
    assert dec_offset == 2021 * 12 + 11

    # End dates default to month 11 (December) if only year provided
    year_end_offset = parse_date_to_month_offset("2020", is_end_date=True)
    assert year_end_offset == 2020 * 12 + 11

    # Present defaults to current calendar offset
    present_offset = parse_date_to_month_offset("Present", is_end_date=True)
    assert present_offset == 2026 * 12 + 7
