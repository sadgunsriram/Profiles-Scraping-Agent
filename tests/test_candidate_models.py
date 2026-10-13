"""
Tests for candidate_models.py.
Verifies dataclass construction, default values, and serialization.
"""

from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    ExperienceEntry,
    EducationEntry,
    CertificationEntry,
    ProjectEntry,
    CandidateAnalysisResult,
    CandidateQualificationDecision,
    EligibilityDecision
)


def test_candidate_models_defaults_and_serialization():
    exp = ExperienceEntry(
        title="Senior Cloud Engineer",
        company="Acme Corp",
        start_date="Jan 2021",
        end_date="Present",
        duration_text="3 yrs 8 mos",
        description="Managed AWS infrastructure with Terraform."
    )
    edu = EducationEntry(
        institution="University of Washington",
        degree="Bachelor of Science",
        field_of_study="Computer Science",
        start_year=2016,
        end_year=2020
    )
    cert = CertificationEntry(
        name="AWS Certified Solutions Architect",
        issuing_organization="Amazon Web Services"
    )
    proj = ProjectEntry(
        title="KubeDeploy",
        description="Automated Kubernetes cluster provisioning"
    )

    profile = NormalizedCandidateProfile(
        full_name="Alex Rivera",
        linkedin_url="https://www.linkedin.com/in/alex-rivera-cloud",
        headline="Senior Cloud & DevOps Engineer",
        location="Seattle, Washington, United States",
        experience_history=[exp],
        education=[edu],
        certifications=[cert],
        skills=["AWS", "Terraform", "Kubernetes", "Python"],
        projects=[proj],
        email="alex.rivera@example.org"
    )

    assert profile.full_name == "Alex Rivera"
    assert profile.date_of_birth == "NOT_AVAILABLE"
    assert profile.gender == "NOT_SPECIFIED"
    assert profile.pronouns == "NOT_SPECIFIED"
    assert len(profile.experience_history) == 1
    assert len(profile.education) == 1
    assert len(profile.certifications) == 1
    assert len(profile.projects) == 1

    d = profile.to_dict()
    assert d["full_name"] == "Alex Rivera"
    assert d["experience_history"][0]["company"] == "Acme Corp"


def test_qualification_decision_serialization():
    profile = NormalizedCandidateProfile(
        full_name="Jordan Lee",
        linkedin_url="https://www.linkedin.com/in/jordan-lee"
    )
    analysis = CandidateAnalysisResult(
        total_experience_years=5.5,
        relevant_technology_years=4.0,
        primary_professional_domain="Cloud / DevOps / Infrastructure",
        technology_specialization="AWS, Terraform",
        skill_relevance_score=85,
        work_authorization="US Citizen",
        security_clearance="Secret"
    )
    decision = CandidateQualificationDecision(
        candidate=profile,
        analysis=analysis,
        decision=EligibilityDecision.ELIGIBLE,
        decision_reasons=["Passed all mandatory criteria"]
    )

    data = decision.to_dict()
    assert data["decision"] == "ELIGIBLE"
    assert data["analysis"]["primary_professional_domain"] == "Cloud / DevOps / Infrastructure"
