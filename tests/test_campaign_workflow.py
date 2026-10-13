"""
test_campaign_workflow.py — Unit tests for workflow_state, campaign_manager, and featured parser.
"""

import pytest
from bs4 import BeautifulSoup

from skills.profile_scraper.workflow_state import WorkflowStage, WorkflowStateTracker
from skills.profile_scraper.campaign_manager import CampaignManager, create_job_requirements
from skills.profile_scraper.profile_extractor import _parse_featured_entities
from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    CandidateQualificationDecision,
    EligibilityDecision
)


def test_workflow_state_tracker_transitions():
    tracker = WorkflowStateTracker(profile_url="https://linkedin.com/in/test-user")
    assert tracker.current_stage == WorkflowStage.DISCOVERY
    assert len(tracker.transitions) == 1

    tracker.record_transition(WorkflowStage.PROFILE_OPENED, "Opening URL")
    tracker.record_transition(WorkflowStage.PAGE_READY, "DOM ready confirmed")
    tracker.record_transition(WorkflowStage.INTRO_PROCESSED, "Extracted name & title")
    tracker.record_transition(WorkflowStage.EXPERIENCE_PROCESSED, "Extracted 3 roles")
    tracker.complete("All sections harvested")

    assert tracker.current_stage == WorkflowStage.PROFILE_COMPLETED
    data = tracker.to_dict()
    assert data["profile_url"] == "https://linkedin.com/in/test-user"
    assert data["transitions_count"] == 6
    assert data["current_stage"] == "PROFILE_COMPLETED"


def test_workflow_state_tracker_fail():
    tracker = WorkflowStateTracker(profile_url="https://linkedin.com/in/failed-user")
    tracker.fail("Checkpoint security detected")
    assert tracker.current_stage == WorkflowStage.PROFILE_FAILED
    assert tracker.transitions[-1]["details"] == "Checkpoint security detected"


def test_campaign_manager_multi_domain_requirements():
    roles = [
        ("Cybersecurity Architect", 3.0),
        ("Cloud Infrastructure Engineer", 3.0),
        ("SAP ERP Consultant", 3.0),
        ("Senior Network Engineer", 3.0),
        ("Databricks Data Engineer", 2.0),
        ("Snowflake Architect", 2.0),
        ("AI / ML Research Scientist", 2.0),
        ("Python Backend Developer", 2.0),
        ("General Software Specialist", 2.0),
    ]

    for role_name, expected_min_tenure in roles:
        req = create_job_requirements(role_name)
        assert req.target_role == role_name
        assert req.min_relevant_experience_years == expected_min_tenure
        assert req.require_us_location is True
        assert req.reject_c2c_recruiters is True


def test_campaign_manager_pacing_and_recording():
    mgr = CampaignManager(target_role="Cloud Engineer", target_count=2, batch_size=2)
    assert mgr.can_process_next() is True
    assert mgr.is_goal_reached() is False

    # Mock candidate decision 1: ELIGIBLE
    c1 = NormalizedCandidateProfile(full_name="Alice Candidate", linkedin_url="https://linkedin.com/in/alice")
    a1 = CandidateAnalysisResult(total_experience_years=5.0, relevant_technology_years=5.0)
    d1 = CandidateQualificationDecision(candidate=c1, analysis=a1, decision=EligibilityDecision.ELIGIBLE)
    mgr.record_candidate(d1)

    assert mgr.eligible_count == 1
    assert mgr.is_goal_reached() is False

    # Mock candidate decision 2: ELIGIBLE
    c2 = NormalizedCandidateProfile(full_name="Bob Candidate", linkedin_url="https://linkedin.com/in/bob")
    a2 = CandidateAnalysisResult(total_experience_years=4.0, relevant_technology_years=4.0)
    d2 = CandidateQualificationDecision(candidate=c2, analysis=a2, decision=EligibilityDecision.ELIGIBLE)
    mgr.record_candidate(d2)

    assert mgr.eligible_count == 2
    assert mgr.is_goal_reached() is True
    assert mgr.can_process_next() is False


def test_featured_section_parsing():
    html_with_featured = """
    <html>
        <body>
            <section id="featured">
                <h2>Featured</h2>
                <ul>
                    <li componentkey="entity-collection-item">
                        <a href="https://example.com/blog/cloud-architecture">
                            <span>High Scale Cloud Architecture on AWS</span>
                        </a>
                        <span>Technical Deep-Dive Article</span>
                    </li>
                    <li componentkey="entity-collection-item">
                        <a href="https://github.com/test/project">
                            <span>Open Source Kubernetes Operator</span>
                        </a>
                    </li>
                </ul>
            </section>
        </body>
    </html>
    """
    soup = BeautifulSoup(html_with_featured, "html.parser")
    featured = _parse_featured_entities(soup)
    assert len(featured) == 2
    assert "High Scale Cloud Architecture on AWS" in featured[0]
    assert "https://example.com/blog/cloud-architecture" in featured[0]
    assert "Open Source Kubernetes Operator" in featured[1]

    # Empty test when section missing
    html_empty = "<html><body><section id='about'><h2>About</h2></section></body></html>"
    soup_empty = BeautifulSoup(html_empty, "html.parser")
    assert _parse_featured_entities(soup_empty) == []


def test_direct_linkedin_search_defaults(monkeypatch):
    from skills.profile_scraper import scraper
    import inspect

    sig = inspect.signature(scraper.search_all_sources)
    assert sig.parameters["mode"].default == "linkedin"

    # Mock unified_google_search to return mixed links and verify filtering
    mock_google_results = [
        {"link": "https://www.linkedin.com/in/valid-us-dev", "title": "Dev - US | LinkedIn"},
        {"link": "https://in.linkedin.com/in/foreign-dev", "title": "Dev - India | LinkedIn"},
        {"link": "https://uk.linkedin.com/in/foreign-dev-2", "title": "Dev - UK | LinkedIn"},
        {"link": "https://github.com/some-user", "title": "Some User GitHub"},
    ]

    monkeypatch.setattr(scraper, "unified_google_search", lambda q, n, start_offset=0: mock_google_results)
    monkeypatch.setattr(scraper.role_expansion, "expand_query_via_ollama", lambda q: None)
    monkeypatch.setenv("SERPER_API_KEY", "mock_key")

    results = scraper.search_all_sources("Python Developer", num=5, mode="linkedin")
    # In linkedin mode, foreign subdomains and github links should be excluded
    links = [r.get("link") for r in results]
    assert "https://www.linkedin.com/in/valid-us-dev" in links
    assert "https://in.linkedin.com/in/foreign-dev" not in links
    assert "https://uk.linkedin.com/in/foreign-dev-2" not in links
    assert "https://github.com/some-user" not in links

