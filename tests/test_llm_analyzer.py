import pytest
from unittest.mock import patch, MagicMock
from skills.profile_scraper.llm_analyzer import TalentAcquisitionAnalyzer
from skills.profile_scraper.set1_identity import Set1Candidate, qualify_candidate_set1
from skills.profile_scraper.excel_manager import batch_save_profiles
import openpyxl
import os


def test_build_candidate_summary():
    analyzer = TalentAcquisitionAnalyzer()
    profile = {
        "full_name": "Alice Networker",
        "headline": "Lead Network Engineer at Acme Corp",
        "about": "Expert in Cisco, BGP, and MPLS.",
        "skills": ["Cisco", "BGP", "Python", "OSPF"],
        "years_of_experience": 8,
        "experience_history": [
            {
                "title": "Lead Network Engineer",
                "company": "Acme Corp",
                "start_date": "2020",
                "end_date": "Present",
                "description": "Architected datacenter BGP fabrics."
            }
        ],
        "education": ["BS Computer Science, Purdue 2016"]
    }
    summary = analyzer._build_candidate_summary(profile, "Network Engineer")
    assert "TARGET ROLE: Network Engineer" in summary
    assert "Alice Networker" in summary
    assert "Acme Corp" in summary
    assert "Cisco" in summary


def test_evaluate_candidate_qualified():
    analyzer = TalentAcquisitionAnalyzer()
    profile = {
        "full_name": "Alice Networker",
        "headline": "Network Engineer",
        "skills": ["Cisco", "Routing"],
        "experience_history": [{"title": "Network Engineer", "company_name": "Cisco Systems"}]
    }

    mock_response = {
        "decision": "QUALIFIED",
        "relevance_score": 92,
        "seniority_level": "Senior",
        "ta_fit_summary": "Strong network engineering background with direct Cisco experience.",
        "key_strengths": ["Cisco", "Routing", "BGP"],
        "red_flags": "None",
        "rejection_reason": None
    }

    with patch.object(analyzer, "_call_ollama_chat", return_value=mock_response):
        result = analyzer.evaluate_candidate(profile, "Network Engineer")
        assert result["decision"] == "QUALIFIED"
        assert result["score"] == 92
        assert result["seniority"] == "Senior"
        assert "Cisco" in result["fit_summary"]
        assert result["analyzer_status"] == "SUCCESS"


def test_evaluate_candidate_rejected_by_ta():
    analyzer = TalentAcquisitionAnalyzer()
    profile = {
        "full_name": "Bob Recruiter",
        "headline": "Technical Recruiter at Staffing Agency",
        "skills": ["Sourcing", "Interviewing"],
        "experience_history": [{"title": "Senior Technical Recruiter", "company_name": "HireFast"}]
    }

    mock_response = {
        "decision": "REJECTED",
        "relevance_score": 15,
        "seniority_level": "Senior",
        "ta_fit_summary": "Candidate is a recruiter without technical engineering responsibilities.",
        "key_strengths": ["Recruiting", "Sourcing"],
        "red_flags": "Non-engineering role",
        "rejection_reason": "Candidate is a recruiter, not a hands-on Network Engineer"
    }

    with patch.object(analyzer, "_call_ollama_chat", return_value=mock_response):
        result = analyzer.evaluate_candidate(profile, "Network Engineer")
        assert result["decision"] == "REJECTED"
        assert result["score"] == 15
        assert "recruiter" in result["rejection_reason"].lower()


def test_evaluate_candidate_score_below_threshold_rejection():
    analyzer = TalentAcquisitionAnalyzer()
    analyzer.min_score = 50
    profile = {"full_name": "Charlie Junior"}

    mock_response = {
        "decision": "QUALIFIED",  # Model said qualified but gave 40/100
        "relevance_score": 40,
        "seniority_level": "Junior",
        "ta_fit_summary": "Limited experience in adjacent role.",
        "key_strengths": ["HTML"],
        "red_flags": "None",
        "rejection_reason": None
    }

    with patch.object(analyzer, "_call_ollama_chat", return_value=mock_response):
        result = analyzer.evaluate_candidate(profile, "Network Engineer")
        assert result["decision"] == "REJECTED"
        assert "below minimum threshold" in result["rejection_reason"]


def test_evaluate_candidate_graceful_fallback():
    analyzer = TalentAcquisitionAnalyzer()
    profile = {"full_name": "Dana Offline", "skills": ["Networking"]}

    with patch.object(analyzer, "_call_ollama_chat", return_value=None):
        result = analyzer.evaluate_candidate(profile, "Network Engineer")
        assert result["decision"] == "QUALIFIED"
        assert result["analyzer_status"] == "FALLBACK"
        assert "fallback" in result["fit_summary"].lower()


def test_qualify_candidate_set1_integration_rejected_by_ta():
    profile = {
        "full_name": "Elena Recruiter",
        "linkedin_url": "https://linkedin.com/in/elena-recruiter",
        "experience_history": [
            {"title": "Technical Recruiter", "company_name": "TechStaff", "start_date": "Jan 2020", "end_date": "Present"}
        ]
    }

    mock_ta_result = {
        "decision": "REJECTED",
        "score": 20,
        "seniority": "Mid-Level",
        "fit_summary": "Recruiter profile, not a network engineer.",
        "rejection_reason": "Candidate lacks technical networking experience."
    }

    with patch("skills.profile_scraper.llm_analyzer.TalentAcquisitionAnalyzer.evaluate_candidate", return_value=mock_ta_result):
        res = qualify_candidate_set1(profile, "Network Engineer")
        assert res is None
        assert profile.get("rejection_stage") == "TA Specialist Evaluation"
        assert "Candidate lacks technical networking experience" in profile.get("rejection_reason")


def test_excel_export_includes_ta_columns(tmp_path):
    excel_file = str(tmp_path / "test_ta_profiles.xlsx")
    candidate = Set1Candidate(
        technology="Network Engineer",
        github_url="Not Available",
        linkedin_url="https://linkedin.com/in/test-engineer",
        joined_linkedin=2015,
        full_name="Frank Engineer",
        years_of_experience=6.0,
        experience_bracket="Mid-Level",
        location="Austin, Texas",
        current_company="Acme Corp",
        age="~30",
        gender="Male",
        ta_decision="QUALIFIED",
        ta_score=88,
        ta_seniority="Senior",
        ta_fit_summary="Demonstrated high competency in datacenter networking at Acme Corp.",
        ta_key_strengths="Cisco, BGP, MPLS"
    )

    batch_save_profiles(
        set1_candidates=[candidate],
        set2_candidates=[candidate],
        set3_candidates=[candidate],
        rejected_candidates={},
        path=excel_file
    )

    wb = openpyxl.load_workbook(excel_file)
    assert "ELIGIBLE_CANDIDATES" in wb.sheetnames
    assert "SET_3" not in wb.sheetnames
    ws_elig = wb["ELIGIBLE_CANDIDATES"]
    headers = [cell for cell in next(ws_elig.iter_rows(max_row=1, values_only=True))]
    assert "TA Fit Summary" not in headers
    assert "TA Seniority" not in headers
    assert "TA Score" not in headers

    row2 = [cell for cell in next(ws_elig.iter_rows(min_row=2, max_row=2, values_only=True))]
    assert len(row2) == len(headers)
    assert row2[headers.index("Full Name")] == "Frank Engineer"
    assert row2[headers.index("LinkedIn URL")] == "https://linkedin.com/in/test-engineer"
    assert "Date Qualified" in headers

