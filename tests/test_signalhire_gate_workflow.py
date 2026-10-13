import pytest
from unittest.mock import patch, MagicMock
from skills.profile_scraper.campaign_orchestrator import CampaignOrchestrator
from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    CandidateQualificationDecision,
    EligibilityDecision
)
from skills.profile_scraper.eligibility_engine import JobRequirements


def test_signalhire_called_when_candidate_eligible():
    orchestrator = CampaignOrchestrator(excel_path="skills/output/test_profiles.xlsx")
    req = JobRequirements(target_role="IAM Engineer")

    candidate = NormalizedCandidateProfile(
        full_name="Alice Smith",
        linkedin_url="https://www.linkedin.com/in/alice-smith-iam",
        location="Austin, Texas, United States",
        current_title="Senior IAM Engineer",
        current_company="TechCorp"
    )

    eligible_decision = CandidateQualificationDecision(
        candidate=candidate,
        analysis=CandidateAnalysisResult(
            total_experience_years=6.0,
            relevant_technology_years=5.0,
            experience_bracket=">5 years (Senior)",
            primary_professional_domain="IDENTITY_ACCESS_MANAGEMENT"
        ),
        decision=EligibilityDecision.ELIGIBLE,
        decision_reasons=["Meets all criteria"]
    )

    mock_sh_result = {
        "status": "SUCCESS",
        "phone": "+1-512-555-9876",
        "email": "alice.smith@techcorp.com",
        "all_phones": ["+1-512-555-9876"],
        "all_emails": ["alice.smith@techcorp.com"]
    }

    with patch.object(orchestrator.analysis_engine, "analyze_candidate", return_value=eligible_decision.analysis), \
         patch.object(orchestrator.eligibility_engine, "evaluate", return_value=eligible_decision), \
         patch.object(orchestrator.signalhire_client, "enrich_candidate", return_value=mock_sh_result) as mock_sh, \
         patch.object(orchestrator.excel_repository, "save_candidate_decision", return_value=True):

        decision = orchestrator.process_candidate_profile(candidate, req)

        # Assert SignalHire was called strictly for this ELIGIBLE candidate
        mock_sh.assert_called_once_with(
            linkedin_url="https://www.linkedin.com/in/alice-smith-iam",
            full_name="Alice Smith",
            company="TechCorp"
        )
        assert decision.signalhire_phone == "+1-512-555-9876"
        assert decision.signalhire_email == "alice.smith@techcorp.com"
        assert decision.candidate.phone == "+1-512-555-9876"
        assert decision.candidate.email == "alice.smith@techcorp.com"


def test_signalhire_never_called_when_candidate_rejected():
    orchestrator = CampaignOrchestrator(excel_path="skills/output/test_profiles.xlsx")
    req = JobRequirements(target_role="IAM Engineer")

    candidate = NormalizedCandidateProfile(
        full_name="Bob Recruiter",
        linkedin_url="https://www.linkedin.com/in/bob-recruiter",
        location="London, United Kingdom",
        current_title="Technical Recruiter",
        current_company="Staffing Solutions"
    )

    rejected_decision = CandidateQualificationDecision(
        candidate=candidate,
        analysis=CandidateAnalysisResult(
            total_experience_years=4.0,
            experience_bracket="<5 years (Junior/Mid)",
            primary_professional_domain="HUMAN_RESOURCES"
        ),
        decision=EligibilityDecision.REJECTED,
        failed_mandatory_rules=["Non-US Location", "Primary domain is Recruitment/HR"]
    )

    with patch.object(orchestrator.analysis_engine, "analyze_candidate", return_value=rejected_decision.analysis), \
         patch.object(orchestrator.eligibility_engine, "evaluate", return_value=rejected_decision), \
         patch.object(orchestrator.signalhire_client, "enrich_candidate") as mock_sh, \
         patch.object(orchestrator.excel_repository, "save_candidate_decision", return_value=True):

        decision = orchestrator.process_candidate_profile(candidate, req)

        # Assert SignalHire was NEVER called to save credits
        mock_sh.assert_not_called()
        assert decision.signalhire_phone == "NOT_AVAILABLE"
        assert decision.signalhire_email == "NOT_AVAILABLE"
