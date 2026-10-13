import pytest
from skills.profile_scraper.candidate_models import NormalizedCandidateProfile, ExperienceEntry
from skills.profile_scraper.candidate_analyzer import CandidateAnalysisEngine
from skills.profile_scraper.eligibility_engine import EligibilityRulesEngine, JobRequirements
from skills.profile_scraper.set1_identity import validate_us_location
from skills.profile_scraper.run import is_valid_url_key, is_valid_email_key


def test_url_and_email_key_validation():
    # Sentinels must not be valid keys
    assert not is_valid_url_key("", "github.com")
    assert not is_valid_url_key("not available", "github.com")
    assert not is_valid_url_key("NOT_AVAILABLE", "github.com")
    assert not is_valid_url_key("none", "github.com")
    assert not is_valid_url_key("n/a", "github.com")

    # Real URLs must be valid keys
    assert is_valid_url_key("https://github.com/torvalds", "github.com")
    assert is_valid_url_key("https://www.linkedin.com/in/karthikreddy456", "linkedin.com")

    # Email keys
    assert not is_valid_email_key("")
    assert not is_valid_email_key("not available")
    assert not is_valid_email_key("NOT_AVAILABLE")
    assert is_valid_email_key("karthik@example.com")


def test_location_headline_filtering():
    # Headlines containing job keywords and pipes should not be treated as locations
    headline_loc = "Network Engineer | B.S. Information Systems | Network Operations, Infrastructure & Systems Support | Open to Work"
    profile = {
        "location": headline_loc,
        "bio_text": "Experienced network engineer located in Dallas, Texas, United States."
    }
    is_us, status, reasons = validate_us_location(profile)
    # The headline should be filtered out, falling back to bio_text which contains Dallas, Texas -> US_LIKELY
    assert is_us is True
    assert status == "US_LIKELY"


def test_location_not_available_fallback_to_snippet():
    profile = {
        "location": "NOT_AVAILABLE",
        "bio_text": "San Francisco Bay Area · Senior Network Engineer at Cisco Systems · Open to work"
    }
    is_us, status, reasons = validate_us_location(profile)
    assert is_us is True
    assert status == "US_LIKELY"


def test_candidate_experience_fallback_from_roles():
    engine = CandidateAnalysisEngine()
    cand = NormalizedCandidateProfile(
        full_name="Karthik Reddy",
        linkedin_url="https://www.linkedin.com/in/karthikreddy456",
        headline="Network Engineer",
        location="United States",
        experience_history=[
            ExperienceEntry(title="Network Engineer", company="Cisco", start_date="", end_date="", duration_text="3 yrs 2 mos"),
            ExperienceEntry(title="Network Specialist", company="AT&T", start_date="", end_date="", duration_text="2 yrs")
        ],
        skills=["Cisco", "BGP", "OSPF", "Routing"],
        is_open_to_work=True
    )
    analysis = engine.analyze_candidate(cand, target_role="Network Engineers")
    assert analysis.total_experience_years >= 5.0
    assert analysis.relevant_technology_years >= 2.0
