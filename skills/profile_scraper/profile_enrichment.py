import re
from typing import Dict, Any, Tuple, Optional, List
from loguru import logger
from email_validator import validate_email, EmailNotValidError
import phonenumbers

# Explicit Security Clearance Regex Patterns for LinkedIn inspection
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

# Explicit Visa / Work Authorization Regex Patterns for LinkedIn inspection
VISA_PATTERNS = [
    (r'\b(us citizen|u\.s\.\s+citizen|united states citizen)\b', 'US Citizen'),
    (r'\b(green card|permanent resident|gc-ead|gc ead)\b', 'Green Card'),
    (r'\b(no sponsorship required|does not require sponsorship|sponsorship not required|not requiring sponsorship)\b', 'No sponsorship required'),
    (r'\b(h1b|h-1b)\b', 'H1B'),
    (r'\b(stem opt|stem-opt)\b', 'STEM OPT'),
    (r'\b(opt|cpt)\b', 'OPT/CPT'),
    (r'\b(authorized to work in the us|authorized to work in the usa|authorized to work in us)\b', 'Authorized to work in US'),
    (r'\b(sponsorship required|requires sponsorship|seeking sponsorship|need sponsorship)\b', 'Requires Sponsorship')
]

# Junk email domain blacklist
JUNK_DOMAINS = {
    "example.com", "domain.com", "email.com", "test.com", "yoursite.com",
    "sentry.io", "wixpress.com", "sampleemail.com", "tempmail.com",
    "dispostable.com", "yopmail.com", "mailinator.com", "trashmail.com",
    "guerrillamail.com", "sharklasers.com", "10minutemail.com"
}


def extract_explicit_clearance_from_text(text: str) -> Optional[str]:
    """Scan LinkedIn text sections for strictly explicit security clearance mentions."""
    if not text:
        return None
    for pattern, label in CLEARANCE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


def extract_explicit_visa_from_text(text: str) -> Optional[str]:
    """Scan LinkedIn text sections for strictly explicit visa/work authorization mentions."""
    if not text:
        return None
    for pattern, label in VISA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


def extract_contacts_from_linkedin_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Scan LinkedIn text sections (e.g. About, summary) for voluntarily provided email or phone."""
    email = None
    phone = None
    if not text:
        return None, None

    # Email extraction
    email_re = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    for m in email_re.findall(text):
        domain = m.split("@")[-1].lower()
        if domain not in JUNK_DOMAINS and len(m) < 80:
            try:
                norm = validate_email(m, check_deliverability=False).normalized
                email = norm
                break
            except EmailNotValidError:
                continue

    # Phone extraction
    phone_re = re.compile(r'(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b')
    for p in phone_re.findall(text):
        try:
            parsed = phonenumbers.parse(p, "US")
            if phonenumbers.is_valid_number(parsed):
                phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                break
        except Exception:
            continue

    return email, phone


def inspect_and_extract_linkedin_fields(profile: dict) -> Tuple[dict, dict]:
    """
    LinkedIn-Only Profile Data Extraction and Progressive SET Field Inspection.
    
    Inspects all relevant LinkedIn sections:
    1. Headline
    2. About / Summary
    3. Experience history (Titles, Descriptions, Companies)
    4. Certifications / Licenses
    5. Skills
    6. Contact Info overlay (Email, Phone)
    7. Publicly visible text
    
    If found: extracts exact value.
    If not found: marks as 'Not Available'.
    Does NOT query Google, Serper, SerpAPI, Hunter.io, personal blogs, or external sites.
    """
    name = profile.get("full_name") or profile.get("name") or "Candidate"
    logger.info(f"[LINKEDIN EXTRACTION] Inspecting candidate LinkedIn profile for '{name}'.")

    # Aggregate all available LinkedIn text sections for comprehensive inspection
    headline = str(profile.get("headline") or "").strip()
    about = str(profile.get("bio") or profile.get("about") or profile.get("summary") or "").strip()
    
    exp_texts = []
    exp_history = profile.get("experience_history") or profile.get("experience") or []
    if isinstance(exp_history, list):
        for exp in exp_history:
            if isinstance(exp, dict):
                t = exp.get("title") or ""
                c = exp.get("company") or exp.get("company_name") or ""
                d = exp.get("description") or ""
                exp_texts.append(f"{t} at {c}. {d}")
            elif isinstance(exp, str):
                exp_texts.append(exp)
    exp_combined = " ".join(exp_texts)

    certs_list = profile.get("certifications") or []
    certs_combined = " ".join(certs_list) if isinstance(certs_list, list) else str(certs_list)

    skills_list = profile.get("skills") or []
    skills_combined = ", ".join(skills_list) if isinstance(skills_list, list) else str(skills_list)

    full_linkedin_text = f"{headline} {about} {exp_combined} {certs_combined} {skills_combined}"

    # Initialize inspection tracking
    linkedin_field_status = {
        "visa_status": {"checked": True, "found": False, "value": "Not Available"},
        "security_clearance": {"checked": True, "found": False, "value": "Not Available"},
        "email": {"checked": True, "found": False, "value": "Not Available"},
        "phone": {"checked": True, "found": False, "value": "Not Available"}
    }

    # 1. Inspect LinkedIn for Visa Status
    raw_visa = profile.get("visa_status")
    extracted_visa = None
    if raw_visa and str(raw_visa).strip().lower() not in ("unknown", "not available", "none", "null", ""):
        extracted_visa = str(raw_visa).strip()
    else:
        extracted_visa = extract_explicit_visa_from_text(full_linkedin_text)

    if extracted_visa:
        profile["visa_status"] = extracted_visa
        linkedin_field_status["visa_status"]["found"] = True
        linkedin_field_status["visa_status"]["value"] = extracted_visa
    else:
        profile["visa_status"] = "Not Available"
        linkedin_field_status["visa_status"]["found"] = False
        linkedin_field_status["visa_status"]["value"] = "Not Available"

    # 2. Inspect LinkedIn for Security Clearance
    raw_clearance = profile.get("security_clearance")
    extracted_clearance = None
    if raw_clearance and str(raw_clearance).strip().lower() not in ("not available", "unknown", "none", "null", "not found", ""):
        extracted_clearance = str(raw_clearance).strip()
    else:
        extracted_clearance = extract_explicit_clearance_from_text(full_linkedin_text)

    if extracted_clearance:
        profile["security_clearance"] = extracted_clearance
        linkedin_field_status["security_clearance"]["found"] = True
        linkedin_field_status["security_clearance"]["value"] = extracted_clearance
    else:
        profile["security_clearance"] = "Not Available"
        linkedin_field_status["security_clearance"]["found"] = False
        linkedin_field_status["security_clearance"]["value"] = "Not Available"

    # 3. Inspect LinkedIn for Email
    raw_email = profile.get("email") or ""
    contact_info = profile.get("contact_info") or {}
    ci_email = contact_info.get("email") if isinstance(contact_info, dict) else ""
    candidate_email = raw_email or ci_email
    
    final_email = None
    if candidate_email and str(candidate_email).strip().lower() not in ("not available", "unknown", "none", "null", ""):
        try:
            final_email = validate_email(candidate_email.strip(), check_deliverability=False).normalized
        except EmailNotValidError:
            final_email = None

    if not final_email:
        text_email, _ = extract_contacts_from_linkedin_text(about)
        if text_email:
            final_email = text_email

    if final_email:
        profile["email"] = final_email
        linkedin_field_status["email"]["found"] = True
        linkedin_field_status["email"]["value"] = final_email
    else:
        profile["email"] = "Not Available"
        linkedin_field_status["email"]["found"] = False
        linkedin_field_status["email"]["value"] = "Not Available"

    # 4. Inspect LinkedIn for Phone
    raw_phone = profile.get("mobile_phone") or profile.get("phone") or ""
    ci_phone = contact_info.get("phone") if isinstance(contact_info, dict) else ""
    candidate_phone = raw_phone or ci_phone
    
    final_phone = None
    if candidate_phone and str(candidate_phone).strip().lower() not in ("not available", "unknown", "none", "null", ""):
        try:
            parsed = phonenumbers.parse(str(candidate_phone).strip(), "US")
            if phonenumbers.is_valid_number(parsed):
                final_phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            else:
                final_phone = str(candidate_phone).strip()
        except Exception:
            final_phone = str(candidate_phone).strip()

    if not final_phone:
        _, text_phone = extract_contacts_from_linkedin_text(about)
        if text_phone:
            final_phone = text_phone

    if final_phone:
        profile["mobile_phone"] = final_phone
        profile["phone"] = final_phone
        linkedin_field_status["phone"]["found"] = True
        linkedin_field_status["phone"]["value"] = final_phone
    else:
        profile["mobile_phone"] = "Not Available"
        profile["phone"] = "Not Available"
        linkedin_field_status["phone"]["found"] = False
        linkedin_field_status["phone"]["value"] = "Not Available"

    profile["linkedin_field_status"] = linkedin_field_status
    return profile, linkedin_field_status
