import re
from typing import Optional, Tuple
from loguru import logger

# Import Set1Candidate and validate_us_location
from skills.profile_scraper.set1_identity import Set1Candidate, validate_us_location

# Case-insensitive security clearance regex patterns for LinkedIn profile inspection
CLEARANCE_PATTERNS = [
    (r'\b(ts/sci|ts-sci|top secret/sci|top secret-sci|tssci)\b', 'TS/SCI'),
    (r'\b(active top secret|top secret clearance|top secret)\b', 'TOP SECRET'),
    (r'\b(active secret clearance|secret clearance|active secret|interim secret)\b', 'SECRET'),
    (r'\b(public trust|public trust clearance)\b', 'PUBLIC TRUST'),
    (r'\b(q clearance|q-cleared|l clearance)\b', 'DOE Q/L'),
    (r'\b(polygraph|ci poly|full scope poly|lifestyle poly)\b', 'TS/SCI (Poly)'),
    (r'\b(confidential clearance|active confidential)\b', 'CONFIDENTIAL'),
    (r'\b(dod security clearance|active dod clearance|dod clearance)\b', 'DoD Clearance')
]

# Explicit Visa / Work Authorization indicator regex patterns for LinkedIn profile inspection
VISA_KEYWORDS = [
    (r'\b(us citizen|u\.s\.\s+citizen|united states citizen)\b', 'US Citizen'),
    (r'\b(green card|permanent resident|gc-ead|gc ead)\b', 'Green Card'),
    (r'\b(no sponsorship required|does not require sponsorship|sponsorship not required)\b', 'No sponsorship required'),
    (r'\b(h1b|h-1b)\b', 'H1B'),
    (r'\b(stem opt|stem-opt)\b', 'STEM OPT'),
    (r'\b(opt|cpt)\b', 'OPT/CPT'),
    (r'\b(authorized to work in the us|authorized to work in the usa|authorized to work in us)\b', 'Authorized to work in US'),
    (r'\b(sponsorship required|requires sponsorship|seeking sponsorship)\b', 'Requires Sponsorship')
]


def qualify_candidate_set2(candidate: Set1Candidate, profile: dict, query: str = "") -> Tuple[bool, Optional[str], Optional[str], Optional[bool], str]:
    """
    Qualify candidate for SET 2: Visa & US Clearance (LinkedIn-Only Extraction).
    
    Rules:
    - Inspects candidate's LinkedIn profile for explicit Visa Status and Security Clearance.
    - If found on LinkedIn: saves extracted value.
    - If not found on LinkedIn: assigns 'Not Available'.
    - NEVER rejects a candidate for missing Visa Status or Security Clearance.
    - Always saves profile in SET 2 and continues to SET 3.
    
    Returns: (is_passed, rejection_stage, rejection_reason, visa_sponsorship_needed, security_clearance)
    """
    # 1. Location Validation (must be valid US location)
    is_us, loc_confidence, loc_details = validate_us_location(profile)
    location_val = profile.get("location") or candidate.location or ""
    if not is_us or not location_val or location_val.lower() in ("unknown", "not available", "n/a", "null", ""):
        logger.warning(f"[SET 2] Rejected: Missing Location or Non-US Profile for candidate '{candidate.full_name}'")
        return False, "Location Validation", "Candidate location is missing or outside the USA", None, "Not Available"

    # Scan all LinkedIn profile sections (headline, bio/about, experience history, skills, certifications)
    bio_text = str(profile.get("bio") or profile.get("about") or profile.get("summary") or "").lower()
    headline = str(profile.get("headline") or "").lower()
    skills = profile.get("skills") or []
    skills_str = ", ".join(skills).lower() if isinstance(skills, list) else str(skills).lower()
    
    exp_history = profile.get("experience_history") or profile.get("experience") or []
    exp_text_parts = []
    if isinstance(exp_history, list):
        for exp in exp_history:
            if isinstance(exp, dict):
                exp_text_parts.append(f"{exp.get('title', '')} {exp.get('description', '')}")
            elif isinstance(exp, str):
                exp_text_parts.append(exp)
    exp_text = " ".join(exp_text_parts).lower()
    
    text_to_scan = f"{headline} {bio_text} {exp_text} {skills_str}"

    # 2. LinkedIn Visa Status Inspection
    norm_visa = profile.get("visa_status")
    if not norm_visa or str(norm_visa).strip().lower() in ("unknown", "not available", "none", "null", ""):
        norm_visa = "Not Available"
        for pattern, label in VISA_KEYWORDS:
            if re.search(pattern, text_to_scan, re.IGNORECASE):
                norm_visa = label
                break

    visa_sponsorship_needed = False
    if norm_visa in ["H1B", "OPT", "CPT", "STEM OPT", "Requires Sponsorship"]:
        visa_sponsorship_needed = True

    # 3. LinkedIn Security Clearance Inspection
    security_clearance = profile.get("security_clearance")
    if not security_clearance or str(security_clearance).strip().lower() in ("not available", "unknown", "none", "null", "not found", ""):
        security_clearance = "Not Available"
        for pattern, normalized_level in CLEARANCE_PATTERNS:
            if re.search(pattern, text_to_scan, re.IGNORECASE):
                security_clearance = normalized_level
                break

    # Log explicit LinkedIn inspection results
    logger.info(f"[SET 2] Checking LinkedIn for Visa Status... Visa Status: {norm_visa}")
    logger.info(f"[SET 2] Checking LinkedIn for Security Clearance... Security Clearance: {security_clearance}")
    logger.info(f"[SET 2] Candidate saved. Missing optional fields do not block progression.")

    # Store normalized values back to profile
    profile["visa_status"] = norm_visa
    profile["security_clearance"] = security_clearance
    
    return True, None, None, visa_sponsorship_needed, security_clearance
