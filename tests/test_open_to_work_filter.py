import pytest
from bs4 import BeautifulSoup
from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    EligibilityDecision
)
from skills.profile_scraper.eligibility_engine import EligibilityRulesEngine, JobRequirements
from skills.profile_scraper.profile_extractor import detect_open_to_work
from skills.profile_scraper.campaign_manager import is_open_to_work_query, create_job_requirements


def test_is_open_to_work_query_detection():
    # Boolean query with open to work
    assert is_open_to_work_query('("Network Engineer") AND ("open to work" OR "#opentowork")')
    assert is_open_to_work_query('Python Developer AND "Open to Work"')
    assert is_open_to_work_query('Cloud Engineer #opentowork')
    assert is_open_to_work_query('DevOps opentowork')

    # Regular queries without open to work
    assert not is_open_to_work_query("Network Engineer")
    assert not is_open_to_work_query("IAM Security Engineer")
    assert not is_open_to_work_query('("SailPoint" OR "CyberArk")')


def test_create_job_requirements_auto_enables_open_to_work():
    reqs_otw = create_job_requirements('("Network Engineer") AND ("open to work" OR "#opentowork")')
    assert reqs_otw.require_open_to_work is True

    reqs_normal = create_job_requirements("Network Engineer")
    assert reqs_normal.require_open_to_work is False


def test_detect_open_to_work_from_headline():
    # 1. Headline hashtag
    is_otw, details = detect_open_to_work(
        headline="Senior Network Engineer | CCIE | #OpenToWork | Looking for new roles",
        about="Passionate infrastructure engineer with 8 years experience."
    )
    assert is_otw is True
    assert "Headline" in details

    # 2. Headline plain text
    is_otw2, details2 = detect_open_to_work(
        headline="DevOps Engineer | Open to work | AWS certified"
    )
    assert is_otw2 is True

    # 3. Headline actively looking
    is_otw3, details3 = detect_open_to_work(
        headline="Cloud Architect - Actively Looking for next opportunity"
    )
    assert is_otw3 is True


def test_detect_open_to_work_from_dom_photo_frame_and_cards():
    # Photo avatar frame badge
    html_badge = """
    <div class="pv-top-card">
        <img class="pv-top-card-profile-picture__image--show-open-to-work" alt="John Doe - Open to work" src="photo.jpg" />
        <h1>John Doe</h1>
    </div>
    """
    soup = BeautifulSoup(html_badge, "html.parser")
    is_otw, details = detect_open_to_work(soup=soup, headline="Senior Engineer")
    assert is_otw is True
    assert "Photo Frame" in details or "DOM Attribute" in details

    # Spotlight card
    html_card = """
    <div class="pv-open-to-work-card">
        <h2>Open to work</h2>
        <p>Network Engineer, Cloud Engineer roles</p>
    </div>
    """
    soup_card = BeautifulSoup(html_card, "html.parser")
    is_otw_card, details_card = detect_open_to_work(soup=soup_card, headline="Senior Engineer")
    assert is_otw_card is True


def test_detect_open_to_work_negative():
    # Regular profile with no open to work indicators
    is_otw, details = detect_open_to_work(
        headline="Staff Network Engineer at Cisco Systems",
        about="Currently leading high-scale enterprise datacenter architecture and design."
    )
    assert is_otw is False
    assert details == "Not Open to Work"


def test_detect_open_to_work_ignores_viewer_nav_avatar():
    # Page with a non-open candidate, but viewer's own avatar in the nav bar has open to work
    html_viewer_nav = """
    <html>
        <header class="global-nav">
            <div class="feed-identity-module__open-to-work">
                <img alt="View Manas Jain's profile, open to work" src="viewer.jpg" />
            </div>
        </header>
        <main>
            <section class="pv-top-card">
                <h1>David Miller</h1>
                <p>Cloud Engineer at Microsoft</p>
                <img class="pv-top-card-profile-picture__image" alt="David Miller" src="david.jpg" />
            </section>
        </main>
    </html>
    """
    soup = BeautifulSoup(html_viewer_nav, "html.parser")
    is_otw, details = detect_open_to_work(soup=soup, headline="Cloud Engineer at Microsoft", candidate_name="David Miller")
    assert is_otw is False
    assert details == "Not Open to Work"


def test_eligibility_engine_enforces_open_to_work_filter():
    engine = EligibilityRulesEngine()
    requirements = JobRequirements(
        target_role="Network Engineer",
        min_relevant_experience_years=3.0,
        min_total_experience_years=3.0,
        require_us_location=True,
        require_open_to_work=True
    )

    analysis = CandidateAnalysisResult(
        total_experience_years=6.0,
        relevant_technology_years=5.0,
        primary_professional_domain="Cloud / DevOps / Infrastructure",
        skill_relevance_score=85,
        work_authorization="US Citizen"
    )

    # 1. Candidate who is NOT open to work -> MUST BE REJECTED
    c_not_otw = NormalizedCandidateProfile(
        full_name="Alice Smith",
        linkedin_url="https://www.linkedin.com/in/alicesmith",
        headline="Senior Network Engineer at Google",
        location="Austin, Texas",
        is_open_to_work=False,
        open_to_work_details="Not Open to Work"
    )
    dec_not_otw = engine.evaluate(c_not_otw, analysis, requirements)
    assert dec_not_otw.decision == EligibilityDecision.REJECTED
    assert any("Open to Work" in r for r in dec_not_otw.failed_mandatory_rules)

    # 2. Candidate who IS open to work -> MUST BE ELIGIBLE
    c_otw = NormalizedCandidateProfile(
        full_name="Bob Jones",
        linkedin_url="https://www.linkedin.com/in/bobjones",
        headline="Senior Network Engineer | #OpenToWork",
        location="Dallas, Texas",
        email="bob@example.com",
        is_open_to_work=True,
        open_to_work_details="Headline: '#OpenToWork'"
    )
    dec_otw = engine.evaluate(c_otw, analysis, requirements)
    assert dec_otw.decision == EligibilityDecision.ELIGIBLE
