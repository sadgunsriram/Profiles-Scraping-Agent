"""
Tests for demographics.py ensuring strict ethical compliance:
- Zero first-name SSA/Census gender guessing.
- Zero synthetic age math from graduation/career start.
- Explicit public birthday extraction.
- Pronouns preserved as declared without forcing gender.
"""

from skills.profile_scraper.demographics import (
    extract_declared_pronouns,
    extract_explicit_gender,
    extract_explicit_dob,
    extract_explicit_demographics,
    extract_gender,
    estimate_age
)


def test_zero_name_gender_guessing():
    # Names that previously triggered SSA inference dictionary
    profile = {
        "full_name": "James Smith",
        "headline": "Software Engineer",
        "about": "Backend specialist with Python and Go."
    }
    # Must NOT guess Male (Inferred)
    gender = extract_explicit_gender(profile)
    assert gender == "NOT_SPECIFIED"
    assert extract_gender(profile) == "NOT_SPECIFIED"

    female_profile = {
        "full_name": "Sarah Connor",
        "headline": "Security Analyst",
        "about": "Cybersecurity defense."
    }
    assert extract_explicit_gender(female_profile) == "NOT_SPECIFIED"
    assert extract_gender(female_profile) == "NOT_SPECIFIED"


def test_zero_synthetic_age_estimation():
    profile = {
        "full_name": "Alex Taylor",
        "education": ["Bachelor of Science | Stanford University | 2016"],
        "experience_history": [
            {"start_date": "Jan 2016", "end_date": "Present", "title": "Developer"}
        ]
    }
    # Must NOT return ~32 or any calculated age
    dob = extract_explicit_dob(profile_data=profile)
    assert dob == "NOT_AVAILABLE"
    assert estimate_age(profile) == "NOT_AVAILABLE"


def test_explicit_birthday_extraction():
    modal_text = """
    Contact info
    Your Profile
    linkedin.com/in/alex-taylor
    Email
    alex.taylor@example.org
    Birthday
    October 24
    Connected
    August 15, 2021
    """
    dob = extract_explicit_dob(modal_text=modal_text)
    assert dob == "October 24"


def test_pronouns_preserved_without_gender_conflation():
    profile = {
        "full_name": "Robin Smith",
        "headline": "Lead DevOps Engineer (they/them)",
        "about": "Building scalable platforms."
    }
    pronouns = extract_declared_pronouns(profile)
    assert pronouns == "They/Them"
    # Gender should still be NOT_SPECIFIED unless explicitly self-declared
    gender = extract_explicit_gender(profile)
    assert gender == "NOT_SPECIFIED"


def test_explicit_self_identified_gender():
    profile = {
        "full_name": "Elena Rostova",
        "headline": "Senior Architect | Passionate female engineer advocating for women in tech",
        "about": "Elena identifies as a woman and mentors aspiring engineers."
    }
    gender = extract_explicit_gender(profile)
    assert gender == "Female"
