"""
Tests for candidate_analyzer.py.
Verifies timeline union math, relevant technology tenure, domain classification, and explicit attribute extraction.
"""

from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    ExperienceEntry,
    EducationEntry,
    CertificationEntry
)
from skills.profile_scraper.candidate_analyzer import (
    calculate_career_timeline_months,
    calculate_relevant_technology_months,
    classify_primary_domain,
    compute_skill_relevance,
    extract_explicit_clearance_and_visa,
    determine_highest_education,
    CandidateAnalysisEngine
)


def test_timeline_union_eliminates_overlapping_double_counting():
    # Role 1: Jan 2020 - Dec 2021 (24 months)
    # Role 2: Jul 2020 - Jun 2022 (Concurrent part-time role overlapping Role 1)
    # Together: Jan 2020 - Jun 2022 = 30 months (not 24 + 24 = 48 months!)
    role1 = ExperienceEntry(
        title="Software Engineer",
        company="Alpha Inc",
        start_date="Jan 2020",
        end_date="Dec 2021"
    )
    role2 = ExperienceEntry(
        title="Consultant",
        company="Beta LLC",
        start_date="Jul 2020",
        end_date="Jun 2022"
    )

    months = calculate_career_timeline_months([role1, role2])
    # 2020 has 12 months (0-11), 2021 has 12 months (12-23), 2022 has 6 months (24-29) -> 30 months total
    assert len(months) == 30
    total_years = round(len(months) / 12.0, 1)
    assert total_years == 2.5


def test_relevant_technology_months_filtering():
    # Role 1: Network Engineer working on Cisco and BGP (Jan 2021 - Dec 2022 = 24 months)
    # Role 2: Barista at Coffee Shop (Jan 2019 - Dec 2020 = 24 months)
    role1 = ExperienceEntry(
        title="Network Engineer",
        company="Cisco Partner",
        start_date="Jan 2021",
        end_date="Dec 2022",
        description="Configured BGP, OSPF, and Cisco Catalyst switches."
    )
    role2 = ExperienceEntry(
        title="Barista",
        company="Coffee Roasters",
        start_date="Jan 2019",
        end_date="Dec 2020",
        description="Customer service."
    )

    all_months = calculate_career_timeline_months([role1, role2])
    assert len(all_months) == 48

    rel_months = calculate_relevant_technology_months([role1, role2], target_role="Network Engineer")
    # Only role 1 should be counted
    assert len(rel_months) == 24


def test_domain_classification_and_specialization():
    profile = NormalizedCandidateProfile(
        full_name="Morgan Vance",
        linkedin_url="https://www.linkedin.com/in/morgan-vance",
        headline="Senior DevOps Engineer | AWS Certified",
        about="Passionate about cloud native infrastructure, Kubernetes, Terraform, and CI/CD.",
        experience_history=[
            ExperienceEntry(
                title="Lead DevOps Engineer",
                company="CloudScale",
                start_date="Jan 2020",
                end_date="Present",
                description="Terraform, AWS, Docker, Kubernetes"
            )
        ],
        skills=["AWS", "Terraform", "Docker", "Kubernetes", "Linux"]
    )

    domain, spec = classify_primary_domain(profile)
    assert domain == "Cloud / DevOps / Infrastructure"
    assert "AWS" in spec


def test_explicit_clearance_and_visa_extraction():
    profile = NormalizedCandidateProfile(
        full_name="David Miller",
        linkedin_url="https://www.linkedin.com/in/david-miller",
        headline="Systems Architect (Active TS/SCI Clearance)",
        about="US Citizen with over 10 years of defense engineering experience.",
        experience_history=[]
    )

    clearance, visa = extract_explicit_clearance_and_visa(profile)
    assert clearance == "TS/SCI"
    assert visa == "US Citizen"


def test_education_level_identification():
    profile = NormalizedCandidateProfile(
        full_name="Samantha Ray",
        linkedin_url="https://www.linkedin.com/in/samantha-ray",
        education=[
            EducationEntry(institution="MIT", degree="Master of Science", field_of_study="Computer Science"),
            EducationEntry(institution="Purdue", degree="Bachelor of Science", field_of_study="Electrical Engineering")
        ]
    )

    highest_edu = determine_highest_education(profile)
    assert highest_edu == "Master's"
