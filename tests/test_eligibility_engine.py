"""
Tests for eligibility_engine.py.
Verifies three distinct decision outcomes: ELIGIBLE, NEEDS_REVIEW, and REJECTED.
"""

from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    EligibilityDecision
)
from skills.profile_scraper.eligibility_engine import (
    EligibilityRulesEngine,
    JobRequirements,
    is_valid_candidate_name,
    is_us_location
)


def test_name_and_location_helpers():
    assert is_valid_candidate_name("John Doe") is True
    assert is_valid_candidate_name("Kiran R") is True
    assert is_valid_candidate_name("Vishal A.") is True
    assert is_valid_candidate_name("J. Doe") is False
    assert is_valid_candidate_name("LinkedIn Member") is False
    assert is_valid_candidate_name("M") is False

    assert is_us_location("San Francisco, California, United States") is True
    assert is_us_location("Austin, TX") is True
    assert is_us_location("London, United Kingdom") is False
    assert is_us_location("Bangalore, India") is False


def test_rejection_for_non_practitioner_recruiter():
    candidate = NormalizedCandidateProfile(
        full_name="Sarah Jenkins",
        linkedin_url="https://www.linkedin.com/in/sarah-jenkins",
        headline="Senior Technical Recruiter | Sourcing Top Cloud Talent",
        location="Austin, Texas, United States"
    )
    analysis = CandidateAnalysisResult(
        total_experience_years=6.0,
        relevant_technology_years=0.5,
        primary_professional_domain="Recruitment / HR / Sales",
        technology_specialization="Technical Recruiting",
        skill_relevance_score=20
    )
    reqs = JobRequirements(target_role="Cloud Infrastructure Engineer", reject_c2c_recruiters=True)

    engine = EligibilityRulesEngine()
    decision = engine.evaluate(candidate, analysis, reqs)

    assert decision.decision == EligibilityDecision.REJECTED
    assert any("Recruitment / HR / Sales" in r for r in decision.failed_mandatory_rules)


def test_rejection_for_insufficient_experience():
    candidate = NormalizedCandidateProfile(
        full_name="Alex Kim",
        linkedin_url="https://www.linkedin.com/in/alex-kim",
        headline="Junior Web Developer Intern",
        location="New York, NY"
    )
    analysis = CandidateAnalysisResult(
        total_experience_years=0.8,
        relevant_technology_years=0.8,
        primary_professional_domain="Software Engineering / Full-Stack",
        skill_relevance_score=35
    )
    reqs = JobRequirements(target_role="Senior Software Engineer", min_relevant_experience_years=3.0, min_total_experience_years=3.0)

    engine = EligibilityRulesEngine()
    decision = engine.evaluate(candidate, analysis, reqs)

    assert decision.decision == EligibilityDecision.REJECTED
    assert any("Insufficient" in r for r in decision.failed_mandatory_rules)


def test_needs_review_for_unstated_clearance_and_missing_email():
    candidate = NormalizedCandidateProfile(
        full_name="Michael Chen",
        linkedin_url="https://www.linkedin.com/in/michael-chen",
        headline="Senior DevOps Engineer",
        location="Reston, Virginia, United States",
        email="NOT_AVAILABLE",
        phone="NOT_AVAILABLE"
    )
    analysis = CandidateAnalysisResult(
        total_experience_years=7.0,
        relevant_technology_years=5.5,
        primary_professional_domain="Cloud / DevOps / Infrastructure",
        technology_specialization="AWS, Kubernetes",
        skill_relevance_score=85,
        work_authorization="US Citizen",
        security_clearance="NOT_AVAILABLE"  # Role requests clearance
    )
    reqs = JobRequirements(
        target_role="DevOps Engineer",
        min_relevant_experience_years=3.0,
        required_security_clearance="Secret"
    )

    engine = EligibilityRulesEngine()
    decision = engine.evaluate(candidate, analysis, reqs)

    assert decision.decision == EligibilityDecision.NEEDS_REVIEW
    assert len(decision.review_reasons) >= 1
    assert any("clearance" in r.lower() for r in decision.review_reasons)


def test_eligible_when_all_mandatory_satisfied():
    candidate = NormalizedCandidateProfile(
        full_name="Rachel Green",
        linkedin_url="https://www.linkedin.com/in/rachel-green-cloud",
        headline="Senior Cloud Infrastructure Architect",
        location="Seattle, WA, United States",
        email="rachel.green@example.org"
    )
    analysis = CandidateAnalysisResult(
        total_experience_years=8.0,
        relevant_technology_years=7.0,
        primary_professional_domain="Cloud / DevOps / Infrastructure",
        technology_specialization="AWS, Terraform, Kubernetes",
        skill_relevance_score=90,
        work_authorization="US Citizen",
        security_clearance="Secret"
    )
    reqs = JobRequirements(
        target_role="Cloud Infrastructure Architect",
        min_relevant_experience_years=3.0,
        require_us_location=True,
        required_security_clearance="Secret"
    )

    engine = EligibilityRulesEngine()
    decision = engine.evaluate(candidate, analysis, reqs)

    assert decision.decision == EligibilityDecision.ELIGIBLE
    assert len(decision.failed_mandatory_rules) == 0
    assert len(decision.review_reasons) == 0
