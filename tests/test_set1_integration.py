"""
Unit and integration tests for structured experience history feeding into Set 1 validation.
"""

from skills.profile_scraper.set1_identity import (
    calculate_employment_months_union,
    qualify_candidate_set1,
    Set1Candidate
)


def test_calculate_employment_months_union_no_overlap():
    # 2020 (12 mos) + 2021 (12 mos) = 24 months
    history = [
        {"title": "Engineer 2", "company": "Co B", "start_date": "Jan 2021", "end_date": "Dec 2021"},
        {"title": "Engineer 1", "company": "Co A", "start_date": "Jan 2020", "end_date": "Dec 2020"}
    ]
    months = calculate_employment_months_union(history)
    assert len(months) == 24


def test_calculate_employment_months_union_overlapping_roles():
    # Role A: Jan 2021 - Dec 2022 (24 months)
    # Role B: Jun 2021 - Jun 2022 (13 months, completely inside Role A)
    # Total union should be exactly 24 months (no double counting!)
    history = [
        {"title": "Lead Engineer", "company": "Co A", "start_date": "Jan 2021", "end_date": "Dec 2022"},
        {"title": "Advisor", "company": "Startup X", "start_date": "Jun 2021", "end_date": "Jun 2022"}
    ]
    months = calculate_employment_months_union(history)
    assert len(months) == 24


def test_qualify_candidate_set1_with_structured_experience():
    # Candidate with >= 3 years verified experience timeline
    profile = {
        "full_name": "Alexander Vance",
        "location": "Austin, Texas, United States",
        "headline": "Senior Cloud Infrastructure Engineer",
        "linkedin_url": "https://www.linkedin.com/in/alexandervance",
        "github_url": "https://github.com/avance",
        "experience_history": [
            {
                "title": "Senior Cloud Infrastructure Engineer",
                "company": "Dell Technologies",
                "start_date": "Jan 2021",
                "end_date": "Present",
                "duration_text": "3 yrs 8 mos",
                "description": "Kubernetes and AWS platform architecture"
            },
            {
                "title": "DevOps Engineer",
                "company": "Rackspace",
                "start_date": "Jan 2018",
                "end_date": "Dec 2020",
                "duration_text": "3 yrs",
                "description": "Terraform, CI/CD automation"
            }
        ]
    }

    from unittest.mock import patch
    with patch("skills.profile_scraper.llm_analyzer.TalentAcquisitionAnalyzer.evaluate_candidate", return_value={"decision": "QUALIFIED", "score": 85, "seniority": "Senior", "fit_summary": "Strong cloud infrastructure background."}):
        candidate = qualify_candidate_set1(profile, query="Cloud Infrastructure")

    assert candidate is not None
    assert isinstance(candidate, Set1Candidate)
    assert candidate.full_name == "Alexander Vance"
    assert candidate.experience_confidence == "HIGH"
    assert candidate.experience_source == "linkedin_experience_timeline"
    assert candidate.years_of_experience is not None
    assert candidate.years_of_experience >= 5.0
