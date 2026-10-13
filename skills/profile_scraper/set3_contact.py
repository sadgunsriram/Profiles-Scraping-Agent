import re
from typing import Optional, Tuple
from loguru import logger
from email_validator import validate_email, EmailNotValidError
import phonenumbers

# Import Set1Candidate
from skills.profile_scraper.set1_identity import Set1Candidate

# List of common junk/disposable email domains to flag
JUNK_DOMAINS = {
    "example.com", "domain.com", "email.com", "test.com", "yoursite.com",
    "sentry.io", "wixpress.com", "sampleemail.com", "tempmail.com",
    "dispostable.com", "yopmail.com", "mailinator.com", "trashmail.com",
    "guerrillamail.com", "sharklasers.com", "10minutemail.com"
}


def qualify_candidate_set3(candidate: Set1Candidate, profile: dict) -> Tuple[bool, Optional[str], Optional[str], str, str, str, str]:
    """
    Qualify candidate for SET 3: Contact Details (LinkedIn-Only Extraction).
    
    Rules:
    - Inspects candidate's LinkedIn profile (Contact Info overlay, About/Bio section) for Email and Phone.
    - If found on LinkedIn: saves validated email / formatted phone number.
    - If not found on LinkedIn: assigns 'Not Available'.
    - NEVER rejects a candidate for missing Email or Phone.
    - Always saves profile in SET 3.
    
    Returns: (is_passed, rejection_stage, rejection_reason, validated_email, formatted_phone, website, portfolio)
    """
    # 1. Inspect LinkedIn Contact Info overlay and profile attributes for Email
    raw_email = (profile.get("email") or getattr(candidate, "email", "") or "").strip()
    contact_info = profile.get("contact_info") or {}
    ci_email = contact_info.get("email") if isinstance(contact_info, dict) else ""
    candidate_email = raw_email or ci_email

    validated_email = "Not Available"
    if candidate_email and candidate_email.lower() not in ("not available", "unknown", "none", "null", ""):
        domain = candidate_email.split("@")[-1].lower() if "@" in candidate_email else ""
        if domain not in JUNK_DOMAINS:
            try:
                norm = validate_email(candidate_email, check_deliverability=False).normalized
                validated_email = norm
            except EmailNotValidError:
                validated_email = "Not Available"

    # Fallback: scan LinkedIn About / Bio text if email was not in contact info overlay
    if validated_email == "Not Available":
        about_text = str(profile.get("bio") or profile.get("about") or profile.get("summary") or "")
        email_re = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        for m in email_re.findall(about_text):
            domain = m.split("@")[-1].lower()
            if domain not in JUNK_DOMAINS and len(m) < 80:
                try:
                    norm = validate_email(m, check_deliverability=False).normalized
                    validated_email = norm
                    break
                except EmailNotValidError:
                    continue

    # 2. Inspect LinkedIn Contact Info overlay and profile attributes for Phone Number
    raw_phone = (profile.get("phone") or profile.get("mobile_phone") or getattr(candidate, "phone", "") or "").strip()
    ci_phone = contact_info.get("phone") if isinstance(contact_info, dict) else ""
    candidate_phone = raw_phone or ci_phone

    formatted_phone = "Not Available"
    if candidate_phone and candidate_phone.lower() not in ("not available", "unknown", "none", "null", ""):
        try:
            parsed = phonenumbers.parse(candidate_phone, "US")
            if phonenumbers.is_valid_number(parsed):
                formatted_phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            else:
                formatted_phone = candidate_phone
        except Exception:
            formatted_phone = candidate_phone

    # Fallback: scan LinkedIn About / Bio text for voluntarily provided phone number
    if formatted_phone == "Not Available":
        about_text = str(profile.get("bio") or profile.get("about") or profile.get("summary") or "")
        phone_re = re.compile(r'(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b')
        for p in phone_re.findall(about_text):
            try:
                parsed = phonenumbers.parse(p, "US")
                if phonenumbers.is_valid_number(parsed):
                    formatted_phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                    break
            except Exception:
                continue

    # Websites from LinkedIn profile (if present)
    website = (profile.get("website") or "").strip()
    if website.lower() in ("not available", "unknown", "n/a", "null"):
        website = ""

    portfolio = (profile.get("portfolio") or "").strip()
    if portfolio.lower() in ("not available", "unknown", "n/a", "null"):
        portfolio = ""

    # Log explicit LinkedIn contact inspection results
    logger.info(f"[SET 3] Checking LinkedIn Contact Info for Email... Email: {validated_email}")
    logger.info(f"[SET 3] Checking LinkedIn Contact Info for Phone... Phone: {formatted_phone}")
    logger.info(f"[SET 3] Candidate saved successfully.")

    # Retain final contact & demographic information in profile dictionary and candidate object
    profile["email"] = validated_email
    profile["phone"] = formatted_phone
    profile["mobile_phone"] = formatted_phone

    if profile.get("age"):
        candidate.age = profile["age"]
    if profile.get("gender"):
        candidate.gender = profile["gender"]

    return True, None, None, validated_email, formatted_phone, website, portfolio
