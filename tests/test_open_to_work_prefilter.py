"""
Unit tests verifying pre-browser Open to Work search result filtering and SignalHire contact normalization.
"""

from skills.profile_scraper.set1_identity import is_search_result_open_to_work
from skills.profile_scraper.signalhire_client import SignalHireClient
from skills.profile_scraper.eligibility_engine import is_valid_candidate_name


def test_search_result_open_to_work_positives():
    # Candidates with explicit Open to Work signals
    c1 = {
        "title": "Anna Hao - Open to work: React Developer/Full-Stack - LinkedIn",
        "snippet": "Anna Hao. Open to work: React Developer/Full-Stack Developer. Seattle, Washington, United States."
    }
    c2 = {
        "title": "Gopi reddy - Actively looking for new opportunities - Senior React ...",
        "snippet": "Senior React Developer. Actively looking for new opportunities. United States."
    }
    c3 = {
        "title": "Steve Erickson - Actively looking for Front-End React Developer",
        "snippet": "Lincoln, Nebraska, United States. Actively seeking roles."
    }
    c4 = {
        "title": "Harshitha Kakumanu - Frontend Engineer | React Developer",
        "snippet": "Frontend Engineer | React Developer | UI Engineer | Open to Work | React ... Texas, United States."
    }
    c5 = {
        "title": "Karthik Reddy - Sr. Network Engineer",
        "snippet": "Seeking new opportunities as a Senior Network Engineer. Available immediately."
    }

    for c in [c1, c2, c3, c4, c5]:
        is_otw, reason = is_search_result_open_to_work(c)
        assert is_otw is True, f"Expected {c['title']} to be recognized as Open to Work: {reason}"


def test_search_result_open_to_work_negatives():
    # Candidates without any Open to Work indicator (must be skipped in 0ms)
    c1 = {
        "title": "Deshik Eddula - Senior Python Engineer - LinkedIn",
        "snippet": "Senior Python Developer @ E*TRADE. Jun 2020 - Nov 2020 6 months. Salt Lake City, Utah, United States."
    }
    c2 = {
        "title": "John Smith - VP of Engineering - Acme Corp",
        "snippet": "Experienced engineering leader managing cloud infrastructure teams across North America."
    }
    c3 = {
        "title": "Recruiter Name - Senior Talent Acquisition Lead",
        "snippet": "We are hiring Senior React developers for our client in New York."
    }

    for c in [c1, c2, c3]:
        is_otw, reason = is_search_result_open_to_work(c)
        assert is_otw is False, f"Expected {c['title']} to be rejected by OTW pre-filter"


def test_name_with_last_initial():
    assert is_valid_candidate_name("Kiran R") is True
    assert is_valid_candidate_name("Vishal A.") is True
    assert is_valid_candidate_name("Jaya K.") is True
    assert is_valid_candidate_name("A B") is False
    assert is_valid_candidate_name("LinkedIn Member") is False


def test_signalhire_extract_contacts_mobile_prioritized():
    client = SignalHireClient(api_key="mock_key")
    payload = {
        "candidate": {
            "contacts": [
                {"type": "phone", "subType": "office", "value": "2125551234"},
                {"type": "phone", "subType": "mobile", "value": "5016157105"},
                {"type": "email", "value": "test@example.com"}
            ]
        }
    }
    result = client._extract_contacts_from_payload(payload, "https://www.linkedin.com/in/test")
    assert result["status"] == "SUCCESS"
    assert result["phone"] == "5016157105"  # mobile prioritized over office
    assert result["email"] == "test@example.com"
