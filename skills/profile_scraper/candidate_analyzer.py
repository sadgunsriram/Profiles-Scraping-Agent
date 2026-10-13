"""
candidate_analyzer.py — Candidate Analysis Engine.

Analyzes the entire professional history to evaluate candidates:
1. Calculates Total Experience (mathematical union of all employment date intervals).
2. Calculates Relevant Technology Experience (intervals matching target tech/domain).
3. Classifies Primary Professional Domain & Technology Specialization.
4. Computes Skill Relevance Score against target requisition.
5. Identifies Highest Education Level.
6. Scans for Explicit Work Authorization & Security Clearance (strictly explicit; never guessed).
7. Invokes Local Ollama TA Specialist for qualitative fit assessment and red flag detection.
"""

import os
import re
import json
from typing import Dict, Any, List, Optional, Set, Tuple
from loguru import logger

from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    CandidateAnalysisResult,
    ExperienceEntry
)
from skills.profile_scraper.llm_analyzer import TalentAcquisitionAnalyzer


CURRENT_YEAR = 2026
CURRENT_MONTH = 8  # August 2026

# Load taxonomy
TAXONOMY: Dict[str, Any] = {}
try:
    tax_path = os.path.join(os.path.dirname(__file__), "taxonomy.json")
    if os.path.exists(tax_path):
        with open(tax_path, "r") as f:
            TAXONOMY = json.load(f)
except Exception as e:
    logger.warning(f"[CandidateAnalyzer] Failed to load taxonomy.json: {e}")

# Security Clearance Regex Patterns
CLEARANCE_PATTERNS: List[Tuple[str, str]] = [
    (r'\b(ts/sci|ts-sci|top secret/sci|top secret-sci|tssci)\b', 'TS/SCI'),
    (r'\b(active top secret|top secret clearance|top secret)\b', 'TOP SECRET'),
    (r'\b(active secret clearance|secret clearance|active secret|interim secret)\b', 'SECRET'),
    (r'\b(public trust|public trust clearance)\b', 'PUBLIC TRUST'),
    (r'\b(q clearance|q-cleared|l clearance)\b', 'DOE Q/L'),
    (r'\b(polygraph|ci poly|full scope poly|lifestyle poly)\b', 'TS/SCI (Poly)'),
    (r'\b(confidential clearance|active confidential)\b', 'CONFIDENTIAL'),
    (r'\b(dod security clearance|active dod clearance|dod clearance)\b', 'DoD Clearance')
]

# Explicit Visa / Work Authorization Regex Patterns
VISA_PATTERNS: List[Tuple[str, str]] = [
    (r'\b(us citizen|u\.s\.\s+citizen|united states citizen)\b', 'US Citizen'),
    (r'\b(green card|permanent resident|gc-ead|gc ead)\b', 'Green Card'),
    (r'\b(no sponsorship required|does not require sponsorship|sponsorship not required|not requiring sponsorship)\b', 'No sponsorship required'),
    (r'\b(h1b|h-1b)\b', 'H1B'),
    (r'\b(stem opt|stem-opt)\b', 'STEM OPT'),
    (r'\b(opt|cpt)\b', 'OPT/CPT'),
    (r'\b(ead|employment\s+authorization\s+document)\b', 'EAD'),
    (r'\b(tn visa|tn status)\b', 'TN Visa'),
    (r'\b(e-?3 visa|e-?3 status)\b', 'E3 Visa'),
    (r'\b(l-?1 visa|l-?1a|l-?1b)\b', 'L1 Visa'),
    (r'\b(o-?1 visa)\b', 'O1 Visa'),
    (r'\b(authorized to work in the us|authorized to work in the usa|authorized to work in us|work authorized|us work authorized)\b', 'Authorized to work in US'),
    (r'\b(sponsorship required|requires sponsorship|seeking sponsorship|need sponsorship)\b', 'Requires Sponsorship')
]

MONTH_MAP = {
    'jan': 0, 'january': 0, 'feb': 1, 'february': 1, 'mar': 2, 'march': 2,
    'apr': 3, 'april': 3, 'may': 4, 'jun': 5, 'june': 5, 'jul': 6, 'july': 6,
    'aug': 7, 'august': 7, 'sep': 8, 'september': 8, 'oct': 9, 'october': 9,
    'nov': 10, 'november': 10, 'dec': 11, 'december': 11
}


def _parse_month_offset(date_str: str, is_end_date: bool = False) -> Optional[int]:
    """
    Parses date string into absolute month offset: (year * 12 + month_index).
    Handles formats: 'Jan 2021', '2019', 'Present', 'current'.
    """
    if not date_str:
        return (CURRENT_YEAR * 12 + CURRENT_MONTH) if is_end_date else None

    clean = date_str.strip().lower()
    if 'present' in clean or 'current' in clean or 'now' in clean:
        return CURRENT_YEAR * 12 + CURRENT_MONTH

    year_m = re.search(r'\b(19\d{2}|20[0-2]\d)\b', clean)
    if not year_m:
        return None
    year = int(year_m.group(1))

    # Identify month
    month_idx = 0
    for m_name, idx in MONTH_MAP.items():
        if re.search(r'\b' + re.escape(m_name) + r'\b', clean):
            month_idx = idx
            break
    else:
        # Default to middle of year if only year is specified
        month_idx = 11 if is_end_date else 0

    return year * 12 + month_idx


def calculate_career_timeline_months(roles: List[ExperienceEntry]) -> Set[int]:
    """
    Builds the mathematical union of all employment month intervals across career history.
    Completely eliminates double-counting of overlapping positions.
    """
    months_union: Set[int] = set()
    for role in roles:
        s_offset = _parse_month_offset(role.start_date, is_end_date=False)
        e_offset = _parse_month_offset(role.end_date, is_end_date=True)

        if s_offset and e_offset and s_offset <= e_offset:
            # Add all months in interval
            for m in range(s_offset, e_offset + 1):
                months_union.add(m)
        elif s_offset and not e_offset:
            # Default to 12 months duration if end date unknown
            for m in range(s_offset, min(s_offset + 12, CURRENT_YEAR * 12 + CURRENT_MONTH)):
                months_union.add(m)

    return months_union


DOMAIN_TECHNOLOGY_TOOLS: Dict[str, List[str]] = {
    "cloud": ["aws", "azure", "gcp", "cloud", "terraform", "kubernetes", "docker", "ansible", "ci/cd", "devops", "linux", "helm", "iam", "eks", "ecs", "lambda", "infrastructure"],
    "network": ["cisco", "bgp", "ospf", "routing", "switching", "firewall", "network", "lan", "wan", "ccna", "ccnp", "juniper", "arista", "tcp/ip"],
    "cybersecurity": ["security", "cyber", "soc", "siem", "penetration", "vulnerability", "cissp", "firewall", "ids", "ips", "incident response", "splunk"],
    "data_engineering": ["snowflake", "databricks", "spark", "sql", "etl", "kafka", "airflow", "python", "data warehouse", "dbt", "hadoop"],
    "ai_ml": ["pytorch", "tensorflow", "machine learning", "deep learning", "nlp", "llm", "python", "computer vision", "scikit-learn"],
    "iam": ["sailpoint", "okta", "cyberark", "ping", "identity", "saml", "oauth", "active directory", "ldap"],
    "sap": ["sap", "abap", "basis", "hana", "fico", "mm", "sd", "ecc", "s/4hana"]
}


def get_target_synonyms(target_role: str) -> Dict[str, List[str]]:
    """Retrieves domain and technology keywords from taxonomy or query terms."""
    q_lower = target_role.lower()
    group_key = None

    # 1. Dynamic matching against all domains defined in taxonomy.json
    for key, data in TAXONOMY.items():
        clean_key = key.lower()
        key_space = clean_key.replace("_", " ")
        if clean_key in q_lower or key_space in q_lower:
            group_key = key
            break
        for term in data.get("strong", []):
            if term.lower() in q_lower:
                group_key = key
                break
        if group_key:
            break

    # 2. Fallback heuristic aliases
    if not group_key:
        if any(k in q_lower for k in ["network", "noc", "cisco", "switching", "routing"]):
            group_key = "network"
        elif "sap" in q_lower:
            group_key = "sap"
        elif "iam" in q_lower or "identity" in q_lower:
            group_key = "iam"
        elif "cloud" in q_lower or "aws" in q_lower or "azure" in q_lower or "gcp" in q_lower:
            group_key = "cloud"
        elif any(k in q_lower for k in ["security", "cyber", "pentest", "vulnerability"]):
            group_key = "cybersecurity"
        elif "snowflake" in q_lower:
            group_key = "snowflake"
        elif "databricks" in q_lower or "data engineer" in q_lower or "data engineering" in q_lower:
            group_key = "data_engineering"
        elif any(k in q_lower for k in ["ai", "ml", "machine learning"]):
            group_key = "ai_ml"

    strong_terms: List[str] = []
    related_terms: List[str] = []
    adjacent_terms: List[str] = []

    if group_key and group_key in TAXONOMY:
        strong_terms.extend(TAXONOMY[group_key].get("strong", []))
        related_terms.extend(TAXONOMY[group_key].get("related", []))
        adjacent_terms.extend(TAXONOMY[group_key].get("adjacent", []))

    if group_key and group_key in DOMAIN_TECHNOLOGY_TOOLS:
        strong_terms.extend(DOMAIN_TECHNOLOGY_TOOLS[group_key])

    words = [w.strip() for w in re.split(r'[\s,/]+', q_lower) if len(w.strip()) > 2]
    strong_terms.extend(words)

    return {
        "strong": list(dict.fromkeys(strong_terms)),
        "related": list(dict.fromkeys(related_terms)),
        "adjacent": list(dict.fromkeys(adjacent_terms)),
        "weak": ["developer", "engineer", "architect"]
    }


def calculate_relevant_technology_months(roles: List[ExperienceEntry], target_role: str) -> Set[int]:
    """
    Calculates non-overlapping months spent specifically in roles matching target technology keywords.
    """
    syns = get_target_synonyms(target_role)
    all_kws = syns.get("strong", []) + syns.get("related", []) + syns.get("adjacent", [])
    relevant_months: Set[int] = set()

    for role in roles:
        role_text = f"{role.title} {role.description} {' '.join(role.skills_used)}".lower()
        if any(re.search(rf'\b{re.escape(kw.lower())}\b', role_text) for kw in all_kws):
            s_offset = _parse_month_offset(role.start_date, is_end_date=False)
            e_offset = _parse_month_offset(role.end_date, is_end_date=True)
            if s_offset and e_offset and s_offset <= e_offset:
                for m in range(s_offset, e_offset + 1):
                    relevant_months.add(m)
            elif s_offset:
                for m in range(s_offset, min(s_offset + 12, CURRENT_YEAR * 12 + CURRENT_MONTH)):
                    relevant_months.add(m)

    return relevant_months


def classify_primary_domain(profile: NormalizedCandidateProfile) -> Tuple[str, str]:
    """
    Classifies the primary professional domain and technology specialization by
    analyzing role titles, summary, and skills across the complete career.
    """
    all_titles = " ".join([r.title.lower() for r in profile.experience_history])
    all_text = f"{profile.headline} {profile.about} {all_titles} {' '.join(profile.skills)}".lower()

    # Domain indicators
    domain_scores = {
        "Cloud / DevOps / Infrastructure": len(re.findall(r'\b(cloud|aws|azure|gcp|devops|kubernetes|docker|terraform|sre|infrastructure)\b', all_text)),
        "Software Engineering / Full-Stack": len(re.findall(r'\b(software engineer|developer|full[- ]?stack|backend|frontend|java|python|react|golang|node)\b', all_text)),
        "Data Engineering / AI / ML": len(re.findall(r'\b(data engineer|snowflake|databricks|spark|etl|machine learning|ai|nlp|data science)\b', all_text)),
        "Cybersecurity / InfoSec": len(re.findall(r'\b(security|cyber|soc|siem|cissp|penetration|incident response|vulnerability|infosec)\b', all_text)),
        "Network Engineering": len(re.findall(r'\b(network engineer|cisco|bgp|ospf|ccna|ccnp|routing|switching|firewall)\b', all_text)),
        "Recruitment / HR / Sales": len(re.findall(r'\b(recruiter|talent acquisition|sourcer|staffing|account executive|sales manager|hr|human resources)\b', all_text))
    }

    # Dynamic domains from taxonomy.json (SAP, Snowflake, IAM, and future domains)
    for dom_k, dom_v in TAXONOMY.items():
        label = dom_k.replace("_", " ").title()
        if label not in domain_scores and isinstance(dom_v, dict):
            terms = dom_v.get("strong", []) + dom_v.get("related", [])
            if terms:
                patt = r'\b(' + '|'.join(re.escape(t.lower()) for t in terms[:12]) + r')\b'
                domain_scores[label] = len(re.findall(patt, all_text))

    primary_domain = max(domain_scores, key=domain_scores.get)
    if domain_scores[primary_domain] == 0:
        primary_domain = "General Technology"

    top_skills = profile.skills[:5] if profile.skills else []
    specialization = ", ".join(top_skills) if top_skills else "General Practitioner"

    return primary_domain, specialization


def compute_skill_relevance(profile: NormalizedCandidateProfile, target_role: str) -> Tuple[int, List[str], List[str]]:
    """
    Computes a weighted skill relevance score (0-100) combining:
    - Skills section (40%)
    - Experience role descriptions & titles (40%)
    - Certifications (20%)
    """
    syns = get_target_synonyms(target_role)
    strong_kws = syns.get("strong", [])
    related_kws = syns.get("related", [])

    matched: List[str] = []
    missing: List[str] = []

    exp_text = " ".join([f"{r.title} {r.description}" for r in profile.experience_history]).lower()
    skills_text = " ".join(profile.skills).lower()
    certs_text = " ".join([c.name for c in profile.certifications]).lower()
    headline_text = profile.headline.lower()

    score = 0.0
    for kw in strong_kws[:15]:
        kw_lower = kw.lower()
        kw_found = False
        if kw_lower in skills_text:
            score += 8.0
            kw_found = True
        if kw_lower in exp_text or kw_lower in headline_text:
            score += 8.0
            kw_found = True
        if kw_lower in certs_text:
            score += 6.0
            kw_found = True

        if kw_found:
            matched.append(kw)
        else:
            missing.append(kw)

    for kw in related_kws[:10]:
        kw_lower = kw.lower()
        if kw_lower in skills_text or kw_lower in exp_text:
            score += 3.0
            if kw not in matched:
                matched.append(kw)

    final_score = int(min(max(score, 10), 100))
    return final_score, matched, missing


def extract_explicit_clearance_and_visa(profile: NormalizedCandidateProfile) -> Tuple[str, str]:
    """
    Scans entire profile text (Headline, About, Experience descriptions, Certifications)
    for strictly explicit public mentions of Security Clearance and Work Authorization.
    Never infers or guesses.
    """
    combined_text = " ".join([
        profile.headline,
        profile.about,
        " ".join([f"{r.title} {r.description}" for r in profile.experience_history]),
        " ".join([c.name for c in profile.certifications])
    ]).lower()

    # 1. Security Clearance
    clearance = "Not Available"
    for pattern, label in CLEARANCE_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            clearance = label
            break

    # 2. Work Authorization / Visa (saved as 'Not Available' if missing)
    visa = "Not Available"
    for pattern, label in VISA_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            visa = label
            break

    return clearance, visa


def determine_highest_education(profile: NormalizedCandidateProfile) -> str:
    """Identifies highest academic credential from the Education section."""
    all_edu_text = " ".join([f"{e.degree or ''} {e.field_of_study or ''} {e.institution}" for e in profile.education]).lower()
    if re.search(r'\b(ph\.?d|doctorate|doctor of philosophy)\b', all_edu_text):
        return "Doctorate"
    if re.search(r'\b(master|m\.?s|m\.?tech|m\.?b\.?a|m\.?eng)\b', all_edu_text):
        return "Master's"
    if re.search(r'\b(bachelor|b\.?s|b\.?tech|b\.?e|b\.?a|undergraduate)\b', all_edu_text):
        return "Bachelor's"
    if re.search(r'\b(associate|diploma)\b', all_edu_text):
        return "Associate"
    if re.search(r'\b(bootcamp|certificate)\b', all_edu_text):
        return "Bootcamp / Certificate"
    return "NOT_SPECIFIED"


class CandidateAnalysisEngine:
    """
    Coordinates end-to-end candidate career analysis across the full profile.
    """
    def __init__(self):
        self.ta_analyzer = TalentAcquisitionAnalyzer()

    def analyze_candidate(self, profile: NormalizedCandidateProfile, target_role: str) -> CandidateAnalysisResult:
        """
        Runs comprehensive analysis over the complete NormalizedCandidateProfile.
        """
        logger.info(f"[CandidateAnalyzer] Analyzing candidate '{profile.full_name}' for target role '{target_role}'...")

        # 1. Timeline Union Math
        all_months = calculate_career_timeline_months(profile.experience_history)
        total_exp_years = round(len(all_months) / 12.0, 1)

        # Fallback if no experience timeline: education graduation year estimation
        if total_exp_years == 0.0 and profile.education:
            grad_years = [e.end_year for e in profile.education if e.end_year]
            if grad_years:
                latest_grad = max(grad_years)
                if 1980 <= latest_grad <= CURRENT_YEAR:
                    total_exp_years = float(max(1, CURRENT_YEAR - latest_grad))

        # Fallback if dates were unparsed but roles exist: parse duration_text or default 1 yr per role
        if total_exp_years == 0.0 and profile.experience_history:
            role_dur_months = 0
            for r in profile.experience_history:
                dt = r.duration_text or ""
                m_yr = re.search(r'(\d+)\s*(?:yr|year)', dt, re.I)
                m_mo = re.search(r'(\d+)\s*(?:mo|month)', dt, re.I)
                if m_yr or m_mo:
                    role_dur_months += (int(m_yr.group(1)) * 12 if m_yr else 0) + (int(m_mo.group(1)) if m_mo else 0)
                else:
                    role_dur_months += 12
            if role_dur_months > 0:
                total_exp_years = round(role_dur_months / 12.0, 1)

        # 2. Relevant Technology Experience
        rel_months = calculate_relevant_technology_months(profile.experience_history, target_role)
        rel_tech_years = round(len(rel_months) / 12.0, 1)
        if rel_tech_years == 0.0 and total_exp_years > 0.0:
            # If target role matches headline or primary domain, assign conservative base
            if any(w.lower() in profile.headline.lower() for w in target_role.split()):
                rel_tech_years = min(total_exp_years, 3.0)

        # 3. Domain & Specialization
        primary_domain, specialization = classify_primary_domain(profile)

        # 4. Skill Relevance
        skill_score, matched_skills, missing_skills = compute_skill_relevance(profile, target_role)

        # 5. Highest Education
        highest_edu = determine_highest_education(profile)

        # 6. Explicit Clearance & Visa Status
        clearance, visa = extract_explicit_clearance_and_visa(profile)

        # 7. Local Ollama TA Specialist Assessment
        profile_dict_for_ta = profile.to_dict()
        profile_dict_for_ta["years_of_experience"] = total_exp_years
        llm_decision = self.ta_analyzer.evaluate_candidate(profile_dict_for_ta, target_role)

        ta_fit_summary = "NOT_AVAILABLE"
        ta_score = None
        seniority = "NOT_SPECIFIED"
        red_flags = "None"

        if llm_decision:
            ta_fit_summary = llm_decision.get("ta_fit_summary") or "NOT_AVAILABLE"
            ta_score = llm_decision.get("relevance_score")
            seniority = llm_decision.get("seniority_level") or "NOT_SPECIFIED"
            red_flags = llm_decision.get("red_flags") or "None"
        else:
            # Heuristic seniority if LLM disabled
            if total_exp_years >= 10.0 or any(t in profile.current_title.lower() for t in ["principal", "staff", "architect"]):
                seniority = "Lead / Principal"
            elif total_exp_years >= 5.0 or "senior" in profile.current_title.lower():
                seniority = "Senior"
            elif total_exp_years >= 2.0:
                seniority = "Mid-Level"
            else:
                seniority = "Junior"

        # Explicit experience bracket (<5 years vs >5 years)
        exp_bracket = ">5 years (Senior)" if total_exp_years >= 5.0 else "<5 years (Junior/Mid)"

        result = CandidateAnalysisResult(
            total_experience_years=total_exp_years,
            relevant_technology_years=rel_tech_years,
            experience_bracket=exp_bracket,
            primary_professional_domain=primary_domain,
            technology_specialization=specialization,
            skill_relevance_score=skill_score,
            seniority_level=seniority,
            highest_education=highest_edu,
            work_authorization=visa,
            security_clearance=clearance,
            ta_fit_summary=ta_fit_summary,
            ta_score=ta_score,
            red_flags=red_flags,
            matched_skills=matched_skills,
            missing_skills=missing_skills
        )

        logger.info(
            f"[CandidateAnalyzer] Completed analysis for '{profile.full_name}': "
            f"Total Exp={total_exp_years} yrs ({exp_bracket}), Relevant Exp={rel_tech_years} yrs, "
            f"Domain='{primary_domain}', Skill Score={skill_score}/100, Visa='{visa}', Clearance='{clearance}'."
        )
        return result
