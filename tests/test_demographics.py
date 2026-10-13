"""
Unit tests for demographics module: Ethical compliance, zero name guessing, and zero age estimation.
"""

from skills.profile_scraper.demographics import (
    extract_gender,
    estimate_age,
    extract_declared_pronouns,
    extract_explicit_dob,
    extract_explicit_gender
)


def test_extract_gender_no_name_guessing():
    # Profile without explicit self-identification - should return NOT_SPECIFIED (zero name guessing)
    profile_male = {"full_name": "Michael Owens", "headline": "Network Engineer"}
    assert extract_gender(profile_male, page_html="") == "NOT_SPECIFIED"

    profile_female = {"full_name": "Sarah Connor", "headline": "Security Specialist"}
    assert extract_gender(profile_female, page_html="") == "NOT_SPECIFIED"


def test_extract_gender_unknown_name():
    profile_unknown = {"full_name": "Xyz123 Qwe", "headline": "Engineer"}
    assert extract_gender(profile_unknown, page_html="") == "NOT_SPECIFIED"


def test_estimate_age_always_returns_not_available():
    # Per ethical compliance, age estimation from education or career start is eliminated
    profile_edu = {
        "education": [
            "Iowa State University | Master of Science | Aug 2021 · Nov 2022",
            "Webster University | Bachelor's Degree | 2012 · 2016"
        ],
        "experience_history": []
    }
    assert estimate_age(profile_edu) == "NOT_AVAILABLE"

    profile_exp = {
        "education": [],
        "experience_history": [
            {"title": "Senior Engineer", "start_date": "Jan 2022"},
            {"title": "Junior Engineer", "start_date": "Jun 2018"}
        ]
    }
    assert estimate_age(profile_exp) == "NOT_AVAILABLE"


def test_declared_pronouns_stored_without_gender_conflation():
    html = """
    <div componentkey="Topcard">
      <h2>Alex Morgan</h2>
      <p>She/Her</p>
      <p>Senior Infrastructure Engineer</p>
    </div>
    """
    profile = {"full_name": "Alex Morgan", "headline": "Senior Infrastructure Engineer"}
    pronouns = extract_declared_pronouns(profile, page_html=html)
    assert pronouns == "She/Her"
    # Gender remains NOT_SPECIFIED unless explicitly self-identified
    assert extract_explicit_gender(profile, page_html=html) == "NOT_SPECIFIED"


def test_explicit_dob_from_modal():
    modal_text = """
    Contact info
    Your Profile
    linkedin.com/in/alex-morgan
    Birthday
    July 19
    """
    dob = extract_explicit_dob(modal_text=modal_text)
    assert dob == "July 19"
