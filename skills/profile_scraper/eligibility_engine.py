"""
eligibility_engine.py — Eligibility Rules & Decision Routing Engine.

Evaluates candidates against configured recruitment requirements and classifies them
into three unambiguous decision outcomes:
- ELIGIBLE: Satisfies all configured mandatory requirements with verified technical depth.
- NEEDS_REVIEW: Strong technical potential but has incomplete, unstated, or borderline attributes
  (e.g., unstated clearance/visa, missing direct email, borderline skill score).
- REJECTED: Clearly fails mandatory requirements with exact rejection reasons recorded.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from loguru import logger

from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    CandidateQualificationDecision,
    EligibilityDecision
)


# Configurable C2C bench sales keywords
C2C_KEYWORDS = [
    "bench sales", "bench marketing", "hotlist", "on our bench", "on my bench",
    "bench resource", "bench consultant", "bench sales recruiter", "us it recruiter",
    "bench sales lead", "bench sales executive", "staffing company recruiter"
]

US_STATES = {
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado', 'connecticut',
    'delaware', 'florida', 'georgia', 'hawaii', 'idaho', 'illinois', 'indiana', 'iowa',
    'kansas', 'kentucky', 'louisiana', 'maine', 'maryland', 'massachusetts', 'michigan',
    'minnesota', 'mississippi', 'missouri', 'montana', 'nebraska', 'nevada', 'new hampshire',
    'new jersey', 'new mexico', 'new york', 'north carolina', 'north dakota', 'ohio',
    'oklahoma', 'oregon', 'pennsylvania', 'rhode island', 'south carolina', 'south dakota',
    'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington', 'west virginia',
    'wisconsin', 'wyoming', 'district of columbia'
}

US_STATE_ABBREVS = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
}


@dataclass
class JobRequirements:
    """
    Configurable recruitment requirements for a specific sourcing campaign.
    """
    target_role: str
    min_relevant_experience_years: float = 2.0
    min_total_experience_years: float = 2.0
    require_us_location: bool = True
    required_security_clearance: Optional[str] = None  # e.g. "Secret", "TS/SCI"
    required_work_authorization: Optional[str] = None  # e.g. "US Citizen", "Green Card"
    reject_c2c_recruiters: bool = True
    min_skill_score: int = 40
    require_open_to_work: bool = False


def is_valid_candidate_name(name: str) -> bool:
    """Validates that name is not a placeholder or organization, allowing valid last initials."""
    if not name or not isinstance(name, str):
        return False
    clean = name.strip()
    if clean.lower() in ["linkedin member", "unknown", "candidate", "n/a", "not available", "none", "null", "admin"]:
        return False
    parts = [p.replace(".", "").strip() for p in clean.split() if p.strip()]
    if len(parts) < 2:
        return False
    # First name must have at least 2 alphabetic characters
    if len(parts[0]) < 2 or not any(c.isalpha() for c in parts[0]):
        return False
    # Last name/initial must contain at least 1 alphabetic character
    if not any(c.isalpha() for c in parts[1]):
        return False
    return True


NON_US_COUNTRIES = {
    "india", "united kingdom", "uk", "canada", "germany", "france", "australia",
    "china", "japan", "brazil", "nigeria", "pakistan", "bangladesh", "russia",
    "singapore", "netherlands", "spain", "italy", "sweden", "switzerland",
    "mexico", "ireland", "poland", "ukraine", "vietnam", "philippines"
}


def is_us_location(location_str: str) -> bool:
    """Checks if location string corresponds to a US jurisdiction."""
    if not location_str or location_str.lower() in ("not_available", "unknown", ""):
        return False
    loc = location_str.lower()

    # Reject explicitly non-US country names
    if any(re.search(rf'\b{re.escape(c)}\b', loc) for c in NON_US_COUNTRIES):
        return False

    if any(k in loc for k in ["united states", "usa", "u.s.a", "u.s."]):
        return True
    if any(re.search(rf'\b{re.escape(st.lower())}\b', loc) for st in US_STATES):
        return True
    for abbrev in US_STATE_ABBREVS:
        # Match e.g. ", tx" or ", tx," or " tx$" with word boundaries
        if re.search(rf',\s*{re.escape(abbrev.lower())}(?:,|$|\s)', loc) or re.search(rf'\s+{re.escape(abbrev.lower())}$', loc):
            return True
    return False


def is_c2c_profile(profile: NormalizedCandidateProfile) -> Tuple[bool, str]:
    """Detects bench marketing and C2C sales signals."""
    combined = f"{profile.headline} {profile.about} {profile.current_title}".lower()
    for kw in C2C_KEYWORDS:
        if kw in combined:
            return True, kw
    return False, ""


class EligibilityRulesEngine:
    """
    Evaluates analyzed candidate profiles against campaign JobRequirements.
    """

    def evaluate(
        self,
        candidate: NormalizedCandidateProfile,
        analysis: CandidateAnalysisResult,
        requirements: JobRequirements
    ) -> CandidateQualificationDecision:
        """
        Executes strict mandatory checks followed by data completeness checks.
        Produces ELIGIBLE, NEEDS_REVIEW, or REJECTED.
        """
        logger.info(f"[EligibilityEngine] Evaluating candidate '{candidate.full_name}'...")
        failed_mandatory: List[str] = []
        review_reasons: List[str] = []
        decision_reasons: List[str] = []

        # -------------------------------------------------------------
        # 1. MANDATORY RULES EVALUATION (Any failure -> REJECTED)
        # -------------------------------------------------------------

        # Rule 1.1: Valid Real Full Name
        if not is_valid_candidate_name(candidate.full_name):
            failed_mandatory.append("Invalid or incomplete real full name")

        # Rule 1.15: Open to Work Verification
        if getattr(requirements, "require_open_to_work", False):
            if not getattr(candidate, "is_open_to_work", False):
                failed_mandatory.append("Candidate is not actively Open to Work (Requirement: Open to Work Only)")

        # Rule 1.2: Practitioner vs Recruiter/Sales Domain Check
        if requirements.reject_c2c_recruiters:
            if analysis.primary_professional_domain == "Recruitment / HR / Sales":
                failed_mandatory.append("Non-practitioner: primary professional domain is Recruitment / HR / Sales")
            
            c2c_match, matched_kw = is_c2c_profile(candidate)
            if c2c_match:
                failed_mandatory.append(f"C2C bench sales profile matched keyword: '{matched_kw}'")

        # Rule 1.3: Location Requirement
        if requirements.require_us_location:
            if not is_us_location(candidate.location):
                # If location explicitly states another country (e.g. India, UK, Canada, Germany)
                foreign_countries = ["india", "united kingdom", "canada", "germany", "france", "australia", "brazil", "nigeria", "pakistan"]
                if any(fc in candidate.location.lower() for fc in foreign_countries):
                    failed_mandatory.append(f"Candidate location outside USA: '{candidate.location}'")
                elif candidate.location == "NOT_AVAILABLE":
                    review_reasons.append("Location is unstated; verification required for US residency")

        # Rule 1.4: Minimum Experience Requirements
        if analysis.relevant_technology_years < requirements.min_relevant_experience_years:
            if analysis.total_experience_years < requirements.min_total_experience_years:
                failed_mandatory.append(
                    f"Insufficient career tenure: Total experience ({analysis.total_experience_years} yrs) "
                    f"and relevant technology experience ({analysis.relevant_technology_years} yrs) "
                    f"are below mandatory minimum ({requirements.min_relevant_experience_years} yrs)"
                )
            else:
                review_reasons.append(
                    f"Relevant technology experience ({analysis.relevant_technology_years} yrs) is below target "
                    f"({requirements.min_relevant_experience_years} yrs), though total experience is {analysis.total_experience_years} yrs"
                )

        # Rule 1.5: Incompatible Work Authorization / Clearance (if strictly required)
        if requirements.required_work_authorization:
            req_visa = requirements.required_work_authorization.lower()
            cand_visa = analysis.work_authorization.lower()
            if cand_visa not in ("not_available", "unknown"):
                if "citizen" in req_visa and "sponsorship" in cand_visa:
                    failed_mandatory.append(f"Incompatible work authorization: Requires {requirements.required_work_authorization}, but candidate states '{analysis.work_authorization}'")

        # Instant Rejection Routing
        if failed_mandatory:
            logger.info(f"[EligibilityEngine] Candidate '{candidate.full_name}' REJECTED. Failed rules: {failed_mandatory}")
            return CandidateQualificationDecision(
                candidate=candidate,
                analysis=analysis,
                decision=EligibilityDecision.REJECTED,
                decision_reasons=[f"Failed mandatory criterion: {r}" for r in failed_mandatory],
                failed_mandatory_rules=failed_mandatory,
                review_reasons=review_reasons
            )

        # -------------------------------------------------------------
        # 2. DATA COMPLETENESS & ADVISORY CHECKS (Flags -> NEEDS_REVIEW)
        # -------------------------------------------------------------

        # Check 2.1: Required Clearance not publicly stated (only if explicitly required)
        if requirements.required_security_clearance:
            if str(analysis.security_clearance).strip().lower() in ("not_available", "not available", "unknown", "none", ""):
                review_reasons.append(f"Security clearance ({requirements.required_security_clearance}) not publicly stated on profile")
            elif requirements.required_security_clearance.lower() not in analysis.security_clearance.lower():
                review_reasons.append(f"Stated clearance '{analysis.security_clearance}' may not satisfy required '{requirements.required_security_clearance}'")

        # Check 2.2: Required Work Authorization not publicly stated (only if explicitly required)
        if requirements.required_work_authorization:
            if str(analysis.work_authorization).strip().lower() in ("not_available", "not available", "unknown", "none", ""):
                review_reasons.append(f"Work authorization ({requirements.required_work_authorization}) not publicly stated on profile")

        # Check 2.3: Contact details availability note
        # Note: Absence of public email/phone on LinkedIn is expected and normal.
        # Qualified candidates proceed to ELIGIBLE so SignalHire can enrich verified contact details.
        if candidate.email in ("NOT_AVAILABLE", "Not Available", "") and candidate.phone in ("NOT_AVAILABLE", "Not Available", ""):
            decision_reasons.append("Direct public contact details (email/phone) not available on profile; queued for SignalHire enrichment")

        # Check 2.4: Skill Relevance Score below target threshold
        if analysis.skill_relevance_score < requirements.min_skill_score:
            review_reasons.append(f"Skill relevance score ({analysis.skill_relevance_score}/100) below target minimum ({requirements.min_skill_score}/100)")

        # Check 2.5: Red flags reported by TA specialist
        if analysis.red_flags and analysis.red_flags.lower() not in ("none", "null", ""):
            review_reasons.append(f"TA Specialist note: {analysis.red_flags}")

        # Routing: NEEDS_REVIEW vs ELIGIBLE
        if review_reasons:
            logger.info(f"[EligibilityEngine] Candidate '{candidate.full_name}' classified as NEEDS_REVIEW. Items: {review_reasons}")
            return CandidateQualificationDecision(
                candidate=candidate,
                analysis=analysis,
                decision=EligibilityDecision.NEEDS_REVIEW,
                decision_reasons=[
                    f"Passed mandatory requirements ({analysis.relevant_technology_years} yrs tech exp in {analysis.primary_professional_domain}).",
                    f"Requires recruiter verification for: {'; '.join(review_reasons)}"
                ],
                failed_mandatory_rules=[],
                review_reasons=review_reasons
            )

        # Full Eligibility
        logger.info(f"[EligibilityEngine] Candidate '{candidate.full_name}' classified as ELIGIBLE!")
        visa_display = analysis.work_authorization if analysis.work_authorization not in ("NOT_AVAILABLE", "not_available", "") else "Not Available"
        return CandidateQualificationDecision(
            candidate=candidate,
            analysis=analysis,
            decision=EligibilityDecision.ELIGIBLE,
            decision_reasons=[
                f"Satisfies all mandatory criteria: {analysis.total_experience_years} yrs total exp, {analysis.relevant_technology_years} yrs relevant tech exp.",
                f"Primary domain '{analysis.primary_professional_domain}', skill score {analysis.skill_relevance_score}/100.",
                f"Work Authorization / Visa Status: {visa_display}."
            ],
            failed_mandatory_rules=[],
            review_reasons=[]
        )
