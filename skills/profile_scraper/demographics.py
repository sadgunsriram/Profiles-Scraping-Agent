"""
demographics.py — Ethical personal information extraction for authorized LinkedIn profile scraping.

Compliance & Ethical Rules:
1. ZERO INFERENCE: Do NOT infer sensitive personal attributes from names, profile photographs, or other unreliable signals.
2. DATE OF BIRTH: Stored strictly when explicitly and voluntarily available in the public source.
   If not explicitly stated, store 'NOT_AVAILABLE' rather than guessing or calculating an age/birth date.
3. GENDER: Do NOT guess gender from first names or photographs. Record only explicitly self-identified values.
   If not explicitly self-identified, record 'NOT_SPECIFIED'.
4. PRONOUNS: Extracted and preserved as declared (e.g. 'he/him', 'she/her', 'they/them').
   Pronouns are linguistic preferences and do NOT automatically provide an authoritative gender classification.
"""

import re
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
from loguru import logger


# Common public pronoun sets
RECOGNIZED_PRONOUNS = {
    "he/him", "he/him/his",
    "she/her", "she/her/hers",
    "they/them", "they/them/theirs",
    "xe/xem", "ze/hir", "any/all"
}


def extract_declared_pronouns(profile_data: Dict[str, Any], page_html: str = "") -> str:
    """
    Extracts explicitly declared pronouns from LinkedIn Topcard or bio text.
    Returns: e.g. 'He/Him', 'She/Her', 'They/Them', or 'NOT_SPECIFIED'.
    """
    # 1. Check Topcard HTML for pronoun element
    if page_html:
        soup = BeautifulSoup(page_html, "html.parser")
        topcard = soup.find(attrs={"componentkey": lambda k: k and "Topcard" in str(k)})
        search_root = topcard if topcard else soup

        for tag in search_root.find_all(["p", "span"]):
            txt = tag.get_text().strip().lower()
            if txt in RECOGNIZED_PRONOUNS:
                logger.debug(f"[Demographics] Found explicitly declared pronoun: '{txt}'")
                return txt.title()

    # 2. Check bio / headline for declared pronouns in parentheses or brackets e.g. "(she/her)"
    combined_text = f"{profile_data.get('about', '')} {profile_data.get('headline', '')}".lower()
    for pronoun in RECOGNIZED_PRONOUNS:
        # Look for explicit patterns like (she/her) or [he/him] or "pronouns: they/them"
        pattern = rf'[\(\[\/]\s*{re.escape(pronoun)}\s*[\)\]\/]|pronouns?:\s*{re.escape(pronoun)}'
        if re.search(pattern, combined_text, re.IGNORECASE):
            logger.debug(f"[Demographics] Found declared pronoun in text: '{pronoun}'")
            return pronoun.title()

    return "NOT_SPECIFIED"


def extract_explicit_gender(profile_data: Dict[str, Any], page_html: str = "") -> str:
    """
    Extracts gender ONLY if explicitly self-identified by the candidate in public text.
    Never guesses from first names, photos, or pronouns.
    Returns: Explicitly stated gender string, or 'NOT_SPECIFIED'.
    """
    # Zero guessing: We search only for voluntary, explicit self-identifications
    combined_text = f"{profile_data.get('about', '')} {profile_data.get('headline', '')}".lower()

    explicit_patterns = [
        (r'\b(woman in tech|female engineer|female founder|female leader)\b', 'Female'),
        (r'\b(identifies as a woman|identifies as female)\b', 'Female'),
        (r'\b(identifies as a man|identifies as male)\b', 'Male'),
        (r'\b(non-binary individual|gender non-conforming|transgender woman|transgender man)\b', 'Non-Binary')
    ]

    for pattern, label in explicit_patterns:
        if re.search(pattern, combined_text, re.IGNORECASE):
            logger.debug(f"[Demographics] Found explicitly self-identified gender descriptor: '{label}'")
            return label

    return "NOT_SPECIFIED"


def extract_explicit_dob(modal_text: str = "", profile_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Extracts Date of Birth ONLY when explicitly and voluntarily published in the public source
    (e.g., Contact Info dialog 'Birthday' field).
    Never synthesizes or estimates age from education graduation or career start years.
    Returns: Explicit date of birth string, or 'NOT_AVAILABLE'.
    """
    if modal_text:
        lines = [l.strip() for l in modal_text.split("\n") if l.strip()]
        for idx, line in enumerate(lines):
            if "birthday" in line.lower() or "born" in line.lower():
                if idx + 1 < len(lines):
                    val = lines[idx + 1].strip()
                    if val and not any(kw in val.lower() for kw in ["contact", "profile", "dismiss"]):
                        logger.debug(f"[Demographics] Found explicit birthday field: '{val}'")
                        return val

    # Search About / Bio text for explicit birthdate mentions e.g. "Born on April 15, 1990"
    if profile_data:
        about = str(profile_data.get("about") or profile_data.get("bio") or "")
        dob_m = re.search(r'\b(born on|date of birth:?)\s+([A-Za-z]{3,}\s+\d{1,2}(?:,\s+\d{4})?|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', about, re.IGNORECASE)
        if dob_m:
            return dob_m.group(2).strip()

    return "NOT_AVAILABLE"


def extract_explicit_demographics(profile_data: Dict[str, Any], page_html: str = "", modal_text: str = "") -> Dict[str, str]:
    """
    Consolidated explicit demographic extractor.
    Returns:
        dict with keys: 'pronouns', 'gender', 'date_of_birth'
    """
    pronouns = extract_declared_pronouns(profile_data, page_html)
    gender = extract_explicit_gender(profile_data, page_html)
    dob = extract_explicit_dob(modal_text, profile_data)

    return {
        "pronouns": pronouns,
        "gender": gender,
        "date_of_birth": dob
    }


# --- Backward Compatibility Wrappers ---
def extract_gender(profile_data: Dict[str, Any], page_html: str = "") -> str:
    """
    Backward-compatible wrapper for extract_explicit_gender.
    Strictly ethical: returns declared gender or 'NOT_SPECIFIED'.
    """
    return extract_explicit_gender(profile_data, page_html)


def estimate_age(profile_data: Dict[str, Any]) -> str:
    """
    Backward-compatible wrapper. Returns 'NOT_AVAILABLE'.
    Per architectural requirements, synthetic age guessing from graduation or career start is deleted.
    """
    return "NOT_AVAILABLE"
