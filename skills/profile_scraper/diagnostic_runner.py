"""
diagnostic_runner.py — Live diagnostic testing runner for authorized LinkedIn profile scraping.
Executes the decoupled 5-layer pipeline and outputs a comprehensive diagnostic report:
1. Session & DOM Readiness
2. Progressive Profile Section Harvesting (Top Card, About, Experience, Education, Certs, Projects, Skills)
3. Candidate Career Analysis (Tenure, Domain, Relevance, Clearance, Visa)
4. Eligibility Evaluation (ELIGIBLE / NEEDS_REVIEW / REJECTED)
5. Immediate 4-Sheet Excel Persistence
"""

import sys
import os
import argparse
from typing import Dict, Any, Optional
from loguru import logger

# Add root directory to python path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, "..", ".."))
while _current_dir in sys.path:
    sys.path.remove(_current_dir)
if _project_root in sys.path:
    sys.path.remove(_project_root)
sys.path.insert(0, _project_root)

from skills.profile_scraper.browser_session import BrowserSessionManager
from skills.profile_scraper.candidate_models import NormalizedCandidateProfile, CandidateQualificationDecision
from skills.profile_scraper.candidate_analyzer import CandidateAnalysisEngine
from skills.profile_scraper.eligibility_engine import EligibilityRulesEngine, JobRequirements
from skills.profile_scraper.excel_repository import ExcelCandidateRepository
from skills.profile_scraper.page_readiness import navigate_to_profile, wait_for_profile_ready
from skills.profile_scraper.profile_extractor import extract_full_profile
from skills.profile_scraper.config import load_config
from skills.profile_scraper.session_monitor import SessionMonitor


def run_diagnostic_scrape(profile_url: str, query: str = "Cloud Infrastructure Engineer", excel_path: str = "skills/output/profiles.xlsx") -> Dict[str, Any]:
    """
    Executes an end-to-end diagnostic run for a single LinkedIn profile URL
    using the decoupled 5-layer architecture.
    """
    config = load_config()
    session_monitor = SessionMonitor(config)
    manager = BrowserSessionManager(config)

    report: Dict[str, Any] = {
        "profile_url": profile_url,
        "query": query,
        "state_transitions": [],
        "section_processing": [],
        "navigation_status": "PENDING",
        "page_readiness_status": "PENDING",
        "decision": "UNKNOWN",
        "confidence_score": 0.0,
        "evidence_sources": [],
        "excel_destination_sheet": "NONE",
        "excel_save_status": "NOT_SAVED"
    }

    try:
        report["state_transitions"].append({"state": "1. SESSION_INITIALIZATION", "status": "STARTING"})
        logger.info(f"[Diagnostic] Starting diagnostic run for: {profile_url}")
        page = manager.start_session()
        report["state_transitions"].append({"state": "1. SESSION_INITIALIZATION", "status": "COMPLETED"})

        # Step 1: Navigation
        report["state_transitions"].append({"state": "2. PROFILE_NAVIGATION", "status": "NAVIGATING"})
        nav_ok = navigate_to_profile(page, profile_url, timeout_ms=config.page_load_timeout)
        report["navigation_status"] = "SUCCESS" if nav_ok else "FAILED"
        report["state_transitions"].append({"state": "2. PROFILE_NAVIGATION", "status": "SUCCESS" if nav_ok else "FAILED"})
        if not nav_ok:
            manager.close()
            _print_report(report)
            return report

        # Step 2: DOM Readiness Check
        report["state_transitions"].append({"state": "3. PAGE_READINESS_CHECK", "status": "EVALUATING"})
        is_ready, reason = wait_for_profile_ready(page, timeout_ms=config.element_timeout)
        report["page_readiness_status"] = "READY" if is_ready else f"NOT_READY ({reason})"
        report["state_transitions"].append({"state": "3. PAGE_READINESS_CHECK", "status": "READY" if is_ready else "NOT_READY"})

        # Step 3: Progressive Profile Section Harvesting (Layer 1)
        report["state_transitions"].append({"state": "4. PROGRESSIVE_HARVESTING", "status": "EXTRACTING"})
        profile_data = extract_full_profile(page, profile_url, enable_extension=config.enable_signalhire_extension)
        manager.close()
        report["state_transitions"].append({"state": "4. PROGRESSIVE_HARVESTING", "status": "COMPLETED"})

        # Section processing log
        report["section_processing"] = profile_data.get("section_processing_log", [])

        candidate: NormalizedCandidateProfile = profile_data.get("normalized_candidate_object")
        report["extracted_name"] = candidate.full_name
        report["extracted_headline"] = candidate.headline
        report["extracted_location"] = candidate.location
        report["extracted_pronouns"] = candidate.pronouns
        report["extracted_dob"] = candidate.date_of_birth
        report["experience_count"] = len(candidate.experience_history)
        report["education_count"] = len(candidate.education)
        report["certifications_count"] = len(candidate.certifications)
        report["skills_count"] = len(candidate.skills)
        report["projects_count"] = len(candidate.projects)
        report["languages_count"] = len(candidate.languages)
        report["volunteer_count"] = len(candidate.volunteer)

        # Contact info availability
        report["contact_availability"] = {
            "email_value": candidate.email,
            "phone_value": candidate.phone,
            "github_value": candidate.github_url,
            "websites_count": len(candidate.websites)
        }

        # Step 4: Candidate Career Analysis (Layer 3)
        report["state_transitions"].append({"state": "5. CANDIDATE_CAREER_ANALYSIS", "status": "ANALYZING"})
        analyzer = CandidateAnalysisEngine()
        analysis = analyzer.analyze_candidate(candidate, target_role=query)
        report["state_transitions"].append({"state": "5. CANDIDATE_CAREER_ANALYSIS", "status": "COMPLETED"})

        report["analysis"] = {
            "total_exp_years": analysis.total_experience_years,
            "relevant_tech_years": analysis.relevant_technology_years,
            "primary_domain": analysis.primary_professional_domain,
            "specialization": analysis.technology_specialization,
            "skill_score": analysis.skill_relevance_score,
            "work_authorization": analysis.work_authorization,
            "security_clearance": analysis.security_clearance,
            "highest_education": analysis.highest_education,
            "ta_fit_summary": analysis.ta_fit_summary,
            "ta_score": analysis.ta_score,
            "seniority_level": analysis.seniority_level,
            "matched_skills": analysis.matched_skills,
            "missing_skills": analysis.missing_skills
        }

        # Step 5: Eligibility Rules Evaluation (Layer 4)
        report["state_transitions"].append({"state": "6. ELIGIBILITY_DECISION_ENGINE", "status": "EVALUATING"})
        elig_engine = EligibilityRulesEngine()
        requirements = JobRequirements(
            target_role=query,
            min_relevant_experience_years=2.0,
            min_total_experience_years=2.0,
            require_us_location=False
        )
        decision = elig_engine.evaluate(candidate, analysis, requirements)
        report["state_transitions"].append({"state": "6. ELIGIBILITY_DECISION_ENGINE", "status": f"DECIDED_{decision.decision.value}"})

        report["decision"] = decision.decision.value
        report["decision_reasons"] = decision.decision_reasons
        report["failed_mandatory_rules"] = decision.failed_mandatory_rules
        report["review_reasons"] = decision.review_reasons

        # Confidence and evidence derivation
        confidence = min(1.0, max(0.2, (analysis.skill_relevance_score / 100.0) * 0.7 + (1.0 if analysis.total_experience_years >= 2.0 else 0.5) * 0.3))
        report["confidence_score"] = round(confidence, 2)
        report["evidence_sources"] = [
            f"Experience history ({len(candidate.experience_history)} positions)",
            f"Skills section ({len(candidate.skills)} skills found, {len(analysis.matched_skills)} matched)",
            f"Headline: '{candidate.headline[:60]}...'",
            f"Location: '{candidate.location}'",
            f"Education ({len(candidate.education)} institutions)",
            f"Licenses & Certifications ({len(candidate.certifications)} records)"
        ]

        # Step 6: Immediate Excel Persistence (Layer 5)
        report["state_transitions"].append({"state": "7. EXCEL_PERSISTENCE", "status": "SAVING"})
        repo = ExcelCandidateRepository(excel_path=excel_path)
        saved = repo.save_candidate_decision(decision)
        dest_sheet = f"{decision.decision.value}_CANDIDATES"
        report["excel_destination_sheet"] = f"ALL_RAW_PROFILES + {dest_sheet}"
        report["excel_save_status"] = f"SUCCESS (Persisted to {excel_path} -> sheets: ALL_RAW_PROFILES & {dest_sheet})" if saved else "FAILED"
        report["state_transitions"].append({"state": "7. EXCEL_PERSISTENCE", "status": "SUCCESS" if saved else "FAILED"})

    except Exception as e:
        logger.error(f"[Diagnostic] Extraction encountered exception: {e}")
        report["extraction_error"] = str(e)
    finally:
        manager.close()

    _print_report(report)
    return report


def _print_report(report: dict):
    """Formats and prints the live diagnostic report."""
    print("\n" + "=" * 85)
    print("           REAL-WORLD PROFILE SCRAPING & EVALUATION AUDIT REPORT")
    print("=" * 85)
    print(f"  Target Profile URL     : {report.get('profile_url')}")
    print(f"  Campaign Target Role   : {report.get('query')}")
    print(f"  Page Readiness Status  : {report.get('page_readiness_status')}")

    print("\n  [1. WORKFLOW STATE TRANSITIONS]")
    for st in report.get("state_transitions", []):
        print(f"    -> {st['state']:<32}: {st['status']}")

    print("\n  [2. PROGRESSIVE SECTION HARVESTING & SCROLL STATUS]")
    sections = report.get("section_processing", [])
    if sections:
        for s in sections:
            print(f"    - Section: {s['section']:<14} | Status: {s['status']:<12} | Expanded Toggles: {s.get('expanded_controls', 0)} | Selector: {s.get('selector')}")
    else:
        print("    - Progressive scrolling completed across standard sections.")

    print("\n  [3. EXTRACTED FIELD COUNTS & DEMOGRAPHICS]")
    print(f"    Candidate Name       : {report.get('extracted_name') or 'None'}")
    print(f"    Headline             : {report.get('extracted_headline') or 'None'}")
    print(f"    Location             : {report.get('extracted_location') or 'None'}")
    print(f"    Declared Pronouns    : {report.get('extracted_pronouns') or 'NOT_SPECIFIED'}")
    print(f"    Explicit Birthday/DOB: {report.get('extracted_dob') or 'NOT_AVAILABLE'}")
    print(f"    Experience Roles     : {report.get('experience_count', 0)}")
    print(f"    Education Records    : {report.get('education_count', 0)}")
    print(f"    Certifications Found : {report.get('certifications_count', 0)}")
    print(f"    Skills Extracted     : {report.get('skills_count', 0)}")
    print(f"    Projects Extracted   : {report.get('projects_count', 0)}")
    print(f"    Languages Extracted  : {report.get('languages_count', 0)}")
    print(f"    Volunteer Records    : {report.get('volunteer_count', 0)}")

    contacts = report.get("contact_availability", {})
    print("\n  [4. CONTACT INFORMATION MODAL EXTRACTION]")
    print(f"    Public Email         : {contacts.get('email_value')}")
    print(f"    Phone Number         : {contacts.get('phone_value')}")
    print(f"    GitHub URL           : {contacts.get('github_value')}")
    print(f"    External Websites    : {contacts.get('websites_count', 0)}")

    analysis = report.get("analysis", {})
    if analysis:
        print("\n  [5. CANDIDATE CAREER ANALYSIS (LAYER 3)]")
        print(f"    Total Experience     : {analysis.get('total_exp_years')} years")
        print(f"    Relevant Tech Exp    : {analysis.get('relevant_tech_years')} years")
        print(f"    Primary Domain       : {analysis.get('primary_domain')}")
        print(f"    Specialization       : {analysis.get('specialization')}")
        print(f"    Assessed Seniority   : {analysis.get('seniority_level')}")
        print(f"    Skill Score          : {analysis.get('skill_score')}/100")
        print(f"    Highest Education    : {analysis.get('highest_education')}")
        print(f"    Work Authorization   : {analysis.get('work_authorization')}")
        print(f"    Security Clearance   : {analysis.get('security_clearance')}")
        print(f"    Matched Skills       : {', '.join(analysis.get('matched_skills', [])) or 'None'}")
        print(f"    Missing Skills       : {', '.join(analysis.get('missing_skills', [])) or 'None'}")
        print(f"    TA Specialist Score  : {analysis.get('ta_score')}")
        print(f"    TA Fit Summary       : {analysis.get('ta_fit_summary')}")

    print("\n  [6. ELIGIBILITY DECISION OUTCOME (LAYER 4)]")
    print(f"    FINAL DECISION       : [{report.get('decision')}]")
    print(f"    Confidence Score     : {report.get('confidence_score')}")
    print("    Decision Reasons     :")
    for r in report.get("decision_reasons", []):
        print(f"      * {r}")
    if report.get("failed_mandatory_rules"):
        print(f"    Failed Mandatory Rules: {report.get('failed_mandatory_rules')}")
    if report.get("review_reasons"):
        print(f"    Review Trigger Items  : {report.get('review_reasons')}")

    print("\n  [7. EVIDENCE SOURCES]")
    for ev in report.get("evidence_sources", []):
        print(f"    - {ev}")

    print("\n  [8. EXCEL PERSISTENCE (LAYER 5)]")
    print(f"    Target Sheets        : {report.get('excel_destination_sheet')}")
    print(f"    Workbook Status      : {report.get('excel_save_status')}")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Authorized LinkedIn Profile Diagnostic Runner")
    parser.add_argument("url", help="LinkedIn profile URL to scrape and analyze")
    parser.add_argument("--query", default="Cloud Infrastructure Engineer", help="Target job role")
    parser.add_argument("--excel", default="skills/output/profiles.xlsx", help="Output Excel workbook path")
    args = parser.parse_args()

    run_diagnostic_scrape(args.url, query=args.query, excel_path=args.excel)
