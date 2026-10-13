"""
campaign_orchestrator.py — Campaign Workflow Orchestrator.

Orchestrates the complete 5-layer pipeline for each candidate profile:
1. Profile Discovery
2. Complete Progressive Profile Collection (All available sections)
3. Raw Data Validation & Normalization
4. Candidate Career Analysis (Total tenure, Tech experience, Domain, Skills, Clearance, Visa, LLM TA)
5. Eligibility Evaluation (Strict Mandatory Checks & Advisory Completeness)
6. Decision Routing (ELIGIBLE / NEEDS_REVIEW / REJECTED)
7. Immediate Excel Persistence (ALL_RAW_PROFILES + Specific Sheet)
8. Next Profile
"""

import time
import random
from typing import Optional, Dict, Any
from loguru import logger
from playwright.sync_api import Page

from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    CandidateQualificationDecision,
    EligibilityDecision
)
from skills.profile_scraper.candidate_analyzer import CandidateAnalysisEngine
from skills.profile_scraper.eligibility_engine import EligibilityRulesEngine, JobRequirements
from skills.profile_scraper.excel_repository import ExcelCandidateRepository
from skills.profile_scraper.database_repository import DatabaseCandidateRepository
from skills.profile_scraper.signalhire_client import SignalHireClient
from skills.profile_scraper.page_readiness import wait_for_profile_ready
from skills.profile_scraper.profile_extractor import extract_full_profile
from skills.profile_scraper.workflow_state import WorkflowStage, WorkflowStateTracker


class CampaignOrchestrator:
    """
    State-driven campaign orchestrator executing the decoupled profile processing flow.
    """

    def __init__(self, excel_path: Optional[str] = None):
        self.analysis_engine = CandidateAnalysisEngine()
        self.eligibility_engine = EligibilityRulesEngine()
        self.excel_repository = ExcelCandidateRepository(excel_path=excel_path)
        self.db_repository = DatabaseCandidateRepository()
        self.signalhire_client = SignalHireClient()

    def process_candidate_profile(
        self,
        candidate: NormalizedCandidateProfile,
        requirements: JobRequirements,
        tracker: Optional[WorkflowStateTracker] = None
    ) -> CandidateQualificationDecision:
        """
        Executes Layers 3, 4, and 5 for an already extracted/normalized candidate profile:
        - Layer 3: Candidate Career Analysis
        - Layer 4: Eligibility Rules Evaluation
        - Layer 4.5: Credit-Protected SignalHire Enrichment (STRICTLY for ELIGIBLE candidates)
        - Layer 5: Immediate Excel Persistence
        """
        if tracker is None:
            tracker = WorkflowStateTracker(profile_url=candidate.linkedin_url or candidate.github_url)

        # Step 3 & 4: Candidate Career Analysis
        tracker.record_transition(WorkflowStage.ANALYSIS_COMPLETED, f"Starting analysis against '{requirements.target_role}'")
        analysis: CandidateAnalysisResult = self.analysis_engine.analyze_candidate(
            candidate,
            target_role=requirements.target_role
        )
        tracker.record_transition(
            WorkflowStage.ANALYSIS_COMPLETED,
            f"Analysis complete: Total Exp={analysis.total_experience_years} yrs ({analysis.experience_bracket}), Relevant Exp={analysis.relevant_technology_years} yrs, Domain='{analysis.primary_professional_domain}'"
        )

        # Step 5 & 6: Eligibility Evaluation & Decision Routing
        decision: CandidateQualificationDecision = self.eligibility_engine.evaluate(
            candidate,
            analysis,
            requirements
        )
        tracker.record_transition(WorkflowStage.ELIGIBILITY_EVALUATED, f"Decision: {decision.decision.value}")

        # Step 6.5: Credit-Protected SignalHire Enrichment (STRICTLY for qualified candidates)
        if decision.decision in (EligibilityDecision.ELIGIBLE, EligibilityDecision.NEEDS_REVIEW):
            if self.signalhire_client.enabled:
                tracker.record_transition(WorkflowStage.CONTACT_INFO_PROCESSED, f"Candidate {decision.decision.value}. Triggering SignalHire REST API enrichment for: {candidate.linkedin_url}")
                sh_result = self.signalhire_client.enrich_candidate(
                    linkedin_url=candidate.linkedin_url,
                    full_name=candidate.full_name,
                    company=candidate.current_company
                )
                candidate.signalhire_status = sh_result.get("status", "NOT_AVAILABLE")
                decision.signalhire_status = sh_result.get("status", "NOT_AVAILABLE")

                if sh_result.get("phone") and sh_result.get("phone") != "Not Available":
                    candidate.signalhire_phone = sh_result["phone"]
                    decision.signalhire_phone = sh_result["phone"]
                    if candidate.phone in ("NOT_AVAILABLE", "Not Available", ""):
                        candidate.phone = sh_result["phone"]

                if sh_result.get("email") and sh_result.get("email") != "Not Available":
                    candidate.signalhire_email = sh_result["email"]
                    decision.signalhire_email = sh_result["email"]
                    if candidate.email in ("NOT_AVAILABLE", "Not Available", ""):
                        candidate.email = sh_result["email"]
        else:
            logger.debug(f"[CampaignOrchestrator] Candidate {candidate.full_name} is {decision.decision.value}. Skipping SignalHire enrichment to protect credits.")

        # Step 7: Immediate Excel Persistence (All Raw Profiles + Classified Sheet)
        save_ok = self.excel_repository.save_candidate_decision(decision)
        if save_ok:
            tracker.record_transition(WorkflowStage.PERSISTED, f"Persisted to Excel sheets -> ALL_RAW_PROFILES + {decision.decision.value}_CANDIDATES")
            tracker.complete(f"Candidate '{candidate.full_name}' evaluated as {decision.decision.value}")
        else:
            tracker.fail(f"Failed to persist candidate '{candidate.full_name}' to Excel.")
            logger.error(f"[CampaignOrchestrator] Failed to persist candidate '{candidate.full_name}' to Excel.")

        # Step 7.5: Relational Database Persistence (Strictly for ELIGIBLE candidates)
        if decision.decision == EligibilityDecision.ELIGIBLE and getattr(self, "db_repository", None) and self.db_repository.enabled:
            db_ok = self.db_repository.save_eligible_candidate(decision)
            if db_ok:
                tracker.record_transition(WorkflowStage.PERSISTED, f"Persisted eligible candidate to database table 'eligible_candidates'")

        # Log decision summary
        print("\n" + "=" * 75)
        print(f"  CANDIDATE DECISION: {decision.decision.value} -> '{candidate.full_name}'")
        print(f"  Target Role       : {requirements.target_role}")
        print(f"  Primary Domain    : {analysis.primary_professional_domain}")
        print(f"  Total Experience  : {analysis.total_experience_years} years")
        print(f"  Relevant Tech Exp : {analysis.relevant_technology_years} years")
        print(f"  Skill Relevance   : {analysis.skill_relevance_score}/100")
        visa_val = analysis.work_authorization if analysis.work_authorization not in ("NOT_AVAILABLE", "not_available", "") else "Not Available"
        print(f"  Work Authorization / Visa: {visa_val}")
        print(f"  Open to Work      : {'YES (' + getattr(candidate, 'open_to_work_details', 'Verified') + ')' if getattr(candidate, 'is_open_to_work', False) else 'NO'}")
        print(f"  Phone Number      : {candidate.phone}")
        print(f"  Email Address     : {candidate.email}")
        if getattr(candidate, "signalhire_phone", None) and candidate.signalhire_phone not in ("NOT_AVAILABLE", "Not Available", ""):
            print(f"  SignalHire Mobile : {candidate.signalhire_phone} (VERIFIED)")
        if getattr(candidate, "signalhire_email", None) and candidate.signalhire_email not in ("NOT_AVAILABLE", "Not Available", ""):
            print(f"  SignalHire Email  : {candidate.signalhire_email} (VERIFIED)")
        print(f"  SignalHire Status : {getattr(candidate, 'signalhire_status', 'NOT_AVAILABLE')}")
        print(f"  Reasons           :")
        for r in decision.decision_reasons:
            print(f"    • {r}")
        if decision.failed_mandatory_rules:
            print(f"  Failed Rules      : {decision.failed_mandatory_rules}")
        if decision.review_reasons:
            print(f"  Review Items      : {decision.review_reasons}")
        print("=" * 75 + "\n")

        return decision

    def process_candidate_page(
        self,
        page: Page,
        profile_url: str,
        requirements: JobRequirements,
        enable_extension: bool = False
    ) -> CandidateQualificationDecision:
        """
        Executes the progressive harvesting and qualification pipeline for a single profile from a live page.
        """
        logger.info(f"[CampaignOrchestrator] Starting workflow for profile: {profile_url}")
        tracker = WorkflowStateTracker(profile_url=profile_url)

        # Step 1: Page Readiness Confirmation
        is_ready, reason = wait_for_profile_ready(page, timeout_ms=10000)
        if not is_ready:
            logger.warning(f"[CampaignOrchestrator] Page layout not ready: {reason}. Proceeding with best-effort harvesting.")
        tracker.record_transition(WorkflowStage.PAGE_READY, f"Readiness status: {reason}")

        # Natural human pacing pause (400-800ms)
        page.wait_for_timeout(random.randint(400, 800))

        # Step 2: Complete Progressive Profile Collection
        otw_required = getattr(requirements, "require_open_to_work", False)
        extracted_data = extract_full_profile(
            page,
            profile_url,
            enable_extension=enable_extension,
            tracker=tracker,
            require_open_to_work=otw_required
        )
        candidate: NormalizedCandidateProfile = extracted_data.get("normalized_candidate_object")
        if not candidate:
            candidate = NormalizedCandidateProfile(
                full_name=extracted_data.get("full_name") or "Candidate",
                linkedin_url=profile_url,
                headline=extracted_data.get("headline") or "NOT_AVAILABLE",
                location=extracted_data.get("location") or "NOT_AVAILABLE",
                about=extracted_data.get("about") or "NOT_AVAILABLE",
                email=extracted_data.get("email") or "NOT_AVAILABLE",
                phone=extracted_data.get("phone") or "NOT_AVAILABLE",
                github_url=extracted_data.get("github_url") or "NOT_AVAILABLE",
                is_open_to_work=extracted_data.get("is_open_to_work", False),
                open_to_work_details=extracted_data.get("open_to_work_details", "NOT_AVAILABLE")
            )

        return self.process_candidate_profile(candidate, requirements, tracker=tracker)
