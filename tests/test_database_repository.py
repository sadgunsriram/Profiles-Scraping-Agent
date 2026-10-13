"""
Unit tests for DatabaseCandidateRepository and CampaignOrchestrator DB integration.
"""

import pytest
from unittest.mock import MagicMock, patch
from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    CandidateQualificationDecision,
    EligibilityDecision
)
from skills.profile_scraper.database_repository import (
    DatabaseCandidateRepository,
    EligibleCandidateModel
)
from skills.profile_scraper.campaign_orchestrator import CampaignOrchestrator
from skills.profile_scraper.eligibility_engine import JobRequirements


@pytest.fixture
def in_memory_repo():
    """Provides an isolated in-memory SQLite DatabaseCandidateRepository for testing."""
    repo = DatabaseCandidateRepository(db_url="sqlite:///:memory:", enabled=True)
    return repo


@pytest.fixture
def sample_eligible_decision():
    candidate = NormalizedCandidateProfile(
        full_name="Sarah Connor",
        linkedin_url="https://www.linkedin.com/in/sarah-connor-cloud",
        headline="Senior Cloud Infrastructure Architect",
        location="Austin, Texas, United States",
        current_title="Cloud Architect",
        current_company="Cyberdyne Systems",
        skills=["AWS", "Terraform", "Kubernetes", "Linux"],
        email="sarah@cyberdyne.com",
        phone="+1-512-555-0199",
        github_url="https://github.com/sconnor"
    )
    candidate.signalhire_phone = "+1-512-555-0199"
    candidate.signalhire_email = "sarah@cyberdyne.com"
    candidate.signalhire_status = "SUCCESS"

    analysis = CandidateAnalysisResult(
        total_experience_years=8.5,
        relevant_technology_years=6.0,
        experience_bracket=">5 years (Senior)",
        primary_professional_domain="Cloud / DevOps / Infrastructure",
        technology_specialization="AWS, Terraform",
        skill_relevance_score=95,
        highest_education="Master of Science",
        work_authorization="US Citizen"
    )

    return CandidateQualificationDecision(
        candidate=candidate,
        analysis=analysis,
        decision=EligibilityDecision.ELIGIBLE,
        decision_reasons=["Meets all senior cloud engineering criteria"]
    )


def test_database_disabled_by_default():
    repo = DatabaseCandidateRepository(db_url="", enabled=False)
    assert not repo.enabled
    assert repo.get_eligible_count() == 0
    assert repo.get_candidate_by_url("https://linkedin.com/in/dummy") is None


def test_database_save_eligible_candidate(in_memory_repo, sample_eligible_decision):
    assert in_memory_repo.enabled
    saved = in_memory_repo.save_eligible_candidate(sample_eligible_decision)
    assert saved is True

    # Verify candidate count
    assert in_memory_repo.get_eligible_count() == 1

    # Verify fields in database
    cand_data = in_memory_repo.get_candidate_by_url("https://www.linkedin.com/in/sarah-connor-cloud")
    assert cand_data is not None
    assert cand_data["full_name"] == "Sarah Connor"
    assert cand_data["company"] == "Cyberdyne Systems"
    assert cand_data["total_experience_years"] == 8.5
    assert cand_data["primary_domain"] == "Cloud / DevOps / Infrastructure"
    assert cand_data["signalhire_phone"] == "+1-512-555-0199"
    assert cand_data["email"] == "sarah@cyberdyne.com"


def test_database_upsert_on_duplicate_linkedin_url(in_memory_repo, sample_eligible_decision):
    # First save
    in_memory_repo.save_eligible_candidate(sample_eligible_decision)
    assert in_memory_repo.get_eligible_count() == 1

    # Simulate subsequent run discovering updated email and phone
    sample_eligible_decision.candidate.email = "sarah.updated@cyberdyne.com"
    sample_eligible_decision.candidate.signalhire_email = "sarah.updated@cyberdyne.com"
    sample_eligible_decision.candidate.phone = "+1-512-555-9999"

    saved_again = in_memory_repo.save_eligible_candidate(sample_eligible_decision)
    assert saved_again is True

    # Count must remain 1 (no duplicate row!)
    assert in_memory_repo.get_eligible_count() == 1

    # Fields must reflect the updated information
    updated_cand = in_memory_repo.get_candidate_by_url("https://www.linkedin.com/in/sarah-connor-cloud")
    assert updated_cand["email"] == "sarah.updated@cyberdyne.com"
    assert updated_cand["phone"] == "+1-512-555-9999"


def test_database_skips_non_eligible_candidate(in_memory_repo, sample_eligible_decision):
    sample_eligible_decision.decision = EligibilityDecision.REJECTED
    sample_eligible_decision.failed_mandatory_rules = ["Non-US Location"]

    saved = in_memory_repo.save_eligible_candidate(sample_eligible_decision)
    assert saved is False
    assert in_memory_repo.get_eligible_count() == 0


def test_orchestrator_persists_eligible_candidate_to_database():
    orchestrator = CampaignOrchestrator(excel_path="skills/output/test_profiles.xlsx")
    req = JobRequirements(target_role="Cloud Architect")

    candidate = NormalizedCandidateProfile(
        full_name="John Connor",
        linkedin_url="https://www.linkedin.com/in/john-connor-dev",
        location="Dallas, TX, United States"
    )

    eligible_decision = CandidateQualificationDecision(
        candidate=candidate,
        analysis=CandidateAnalysisResult(
            total_experience_years=7.0,
            relevant_technology_years=5.0,
            primary_professional_domain="Cloud / DevOps / Infrastructure"
        ),
        decision=EligibilityDecision.ELIGIBLE,
        decision_reasons=["Passed all requirements"]
    )

    # Mock components
    with patch.object(orchestrator.analysis_engine, "analyze_candidate", return_value=eligible_decision.analysis), \
         patch.object(orchestrator.eligibility_engine, "evaluate", return_value=eligible_decision), \
         patch.object(orchestrator.signalhire_client, "enrich_candidate", return_value={"status": "SKIPPED_NO_API_KEY"}), \
         patch.object(orchestrator.excel_repository, "save_candidate_decision", return_value=True), \
         patch.object(orchestrator.db_repository, "save_eligible_candidate", return_value=True) as mock_db_save:

        orchestrator.db_repository.enabled = True
        decision = orchestrator.process_candidate_profile(candidate, req)

        # Assert database save was called
        mock_db_save.assert_called_once_with(eligible_decision)
