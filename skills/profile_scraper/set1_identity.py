import re
import os
import httpx
from dataclasses import dataclass
from typing import Optional, List, Tuple
from loguru import logger
import phonenumbers
from email_validator import validate_email, EmailNotValidError

import skills.profile_scraper.scraper as scraper


# Validation status constants
STATUS_MATCH = "MATCH"
STATUS_MISMATCH = "MISMATCH"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"
STATUS_EXTRACTION_FAILED = "EXTRACTION_FAILED"

@dataclass
class Set1Candidate:
    technology: str
    github_url: str
    linkedin_url: str
    joined_linkedin: Optional[int]
    full_name: str
    years_of_experience: Optional[float]
    experience_bracket: str
    location: str
    current_company: str
    email: str = "Not Available"
    phone: str = "Not Available"
    confidence_score: str = "High"
    experience_validation_status: str = "Valid"
    current_pipeline_stage: str = "Qualified"
    visa_sponsorship_needed: Optional[bool] = None
    security_clearance: str = "Not Available"
    skills: str = ""
    current_title: str = ""
    visa_status: str = "Not Available"
    relevance_score: Optional[int] = None
    discovery_score: Optional[int] = None
    relevance_band: str = "Unknown"
    location_status: str = "Unknown"
    rejection_category: str = "RELEVANT"
    enrichment_status: str = "SUCCESS"
    data_quality_status: str = "Good"
    website: str = ""
    portfolio: str = ""
    age: str = "Not Available"
    gender: str = "Not Available"
    ta_decision: str = "QUALIFIED"
    ta_score: Optional[int] = None
    ta_seniority: str = "Not Available"
    ta_fit_summary: str = "Not Available"
    ta_key_strengths: str = "Not Available"
    experience_source: str = "unavailable"
    experience_confidence: str = "NONE"
    title_source: str = "unavailable"
    skills_source: str = "unavailable"
    linkedin_field_status: Optional[dict] = None

# Load taxonomy configuration
TAXONOMY = {}
try:
    tax_path = os.path.join(os.path.dirname(__file__), "taxonomy.json")
    if os.path.exists(tax_path):
        import json
        with open(tax_path, "r") as f:
            TAXONOMY = json.load(f)
except Exception as e:
    logger.error(f"Failed to load taxonomy.json: {e}")

def get_synonyms_for_query(query: str) -> dict:
    """Resolve synonyms from taxonomy.json for the query."""
    q_lower = query.lower()
    group_key = None
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
    elif any(k in q_lower for k in ["ai", "ml", "machine learning", "artificial intelligence"]):
        group_key = "ai_ml"
        
    if group_key and group_key in TAXONOMY:
        return TAXONOMY[group_key]
        
    # Fallback default if not matching predefined groups
    query_words = [w.strip() for w in re.split(r'[\s,/]+', q_lower) if len(w.strip()) > 2]
    return {
        "strong": query_words,
        "related": [],
        "adjacent": [],
        "weak": ["developer", "engineer", "analyst"]
    }

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

def is_full_name_valid(name: str) -> bool:
    """Validate that candidate names are not abbreviated or represented only by initials."""
    if not name or not isinstance(name, str):
        return False
    name_clean = name.strip()
    parts = [p.strip().replace('.', '') for p in name_clean.split() if p.strip()]
    if len(parts) < 2:
        return False  # Must contain at least a first name and a last name
    for p in parts:
        if len(p) <= 1:
            return False  # Reject initials (e.g. M) or abbreviations (e.g. D.)
    return True

def parse_date_to_month_offset(date_str: str, is_end_date: bool = False) -> Optional[int]:
    """Parse date strings to monthly offsets: YYYY * 12 + MonthIndex (0-11)."""
    if not date_str or not isinstance(date_str, str):
        if is_end_date:
            return 2026 * 12 + 7  # Default present is August 2026
        return None
        
    date_str_clean = date_str.strip().lower()
    if 'present' in date_str_clean:
        return 2026 * 12 + 7
        
    year_m = re.search(r'\b(19\d{2}|20[0-2]\d)\b', date_str_clean)
    if not year_m:
        return None
    year = int(year_m.group(1))
    
    months_map = {
        'jan': 0, 'feb': 1, 'mar': 2, 'apr': 3, 'may': 4, 'jun': 5,
        'jul': 6, 'aug': 7, 'sep': 8, 'oct': 9, 'nov': 10, 'dec': 11,
        'january': 0, 'february': 1, 'march': 2, 'april': 3, 'june': 5,
        'july': 6, 'august': 7, 'september': 8, 'october': 9, 'november': 10, 'december': 11
    }
    month = None
    for m_name, m_idx in months_map.items():
        if m_name in date_str_clean:
            month = m_idx
            break
            
    if month is None:
        # Check for numeric formats YYYY-MM or MM/YYYY
        digits_m = re.findall(r'\b(0?[1-9]|1[0-2])\b', date_str_clean)
        for d in digits_m:
            if int(d) != year:
                month = int(d) - 1
                break
                
    if month is None:
        month = 11 if is_end_date else 0
        
    return year * 12 + month

def calculate_employment_months_union(history: list) -> set:
    """Calculate the union of all active employment month offsets to avoid double-counting overlapping positions."""
    union_months = set()
    if not history or not isinstance(history, list):
        return union_months
        
    for job in history:
        if not isinstance(job, dict):
            continue
        start_offset = parse_date_to_month_offset(job.get('start_date'), is_end_date=False)
        end_offset = parse_date_to_month_offset(job.get('end_date'), is_end_date=True)
        
        if start_offset and end_offset and start_offset <= end_offset:
            for m in range(start_offset, end_offset + 1):
                union_months.add(m)
    return union_months

KEYWORDS_MAP = {
    "network": {
        "strong": [
            "network engineer", "network administrator", "network analyst", "noc engineer",
            "infrastructure engineer", "network infrastructure", "cisco", "ccna", "ccnp", "ccie",
            "routing", "switching", "bgp", "ospf", "tcp/ip", "firewall", "vpn", "sd-wan",
            "fortinet", "palo alto", "juniper", "aruba", "meraki", "arista", "extreme networks",
            "wireless", "wifi", "voip", "sip", "telecom", "f5", "load balancer", "dns", "dhcp",
            "sdn", "mpls"
        ],
        "weak": ["systems engineer", "infrastructure", "telecommunications", "data center", "voice", "collaboration", "broadband", "fiber"],
        "negative": [
            "software engineer", "frontend", "backend", "full stack", "product manager",
            "project manager", "recruiter", "talent acquisition", "hr", "marketing", "sales",
            "business analyst", "scrum master"
        ]
    },
    "sap": {
        "strong": ["sap", "abap", "basis", "hana", "fico", "mm", "sd", "pp", "bw", "bo", "s4hana"],
        "weak": ["erp", "consultant", "analyst", "developer", "administrator", "specialist"],
        "negative": [
            "recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master",
            "project manager", "product manager"
        ]
    },
    "iam": {
        "strong": [
            "iam", "identity", "access management", "okta", "sailpoint", "ping", "cyberark",
            "active directory", "azure ad", "entra", "sso", "mfa"
        ],
        "weak": ["security", "engineer", "analyst", "administrator", "specialist"],
        "negative": [
            "recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master",
            "project manager", "product manager"
        ]
    },
    "cloud": {
        "strong": [
            "aws", "azure", "gcp", "kubernetes", "terraform", "cloud infrastructure", "ec2",
            "vpc", "eks", "aks", "docker"
        ],
        "weak": ["cloud engineer", "devops", "sre", "platform engineer", "infrastructure"],
        "negative": [
            "recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master",
            "project manager", "product manager"
        ]
    },
    "cybersecurity": {
        "strong": [
            "cybersecurity engineer", "cybersecurity analyst", "cybersecurity", "cyber security",
            "security engineer", "security analyst", "information security", "infosec",
            "soc", "siem", "splunk", "sentinel", "crowdstrike", "firewall",
            "incident response", "vulnerability", "penetration testing", "zero trust"
        ],
        "weak": ["analyst", "engineer"],
        "negative": [
            "recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master",
            "project manager", "product manager"
        ]
    },
    "snowflake": {
        "strong": ["snowflake", "dbt", "data warehouse", "etl", "elt", "sql", "airflow"],
        "weak": ["data engineer", "developer", "analyst"],
        "negative": [
            "recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master",
            "project manager", "product manager"
        ]
    },
    "data_engineering": {
        "strong": ["data engineer", "spark", "kafka", "databricks", "airflow", "snowflake", "sql", "python", "etl"],
        "weak": ["developer", "data warehouse", "database", "engineer"],
        "negative": [
            "recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master",
            "project manager", "product manager"
        ]
    },
    "ai_ml": {
        "strong": [
            "machine learning", "ai", "artificial intelligence", "llm", "langchain", "pytorch",
            "tensorflow", "hugging face", "rag", "vector database"
        ],
        "weak": ["data scientist", "scientist", "developer", "engineer"],
        "negative": [
            "recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master",
            "project manager", "product manager"
        ]
    }
}

def is_role_relevant(role_title: str, query: str) -> bool:
    """Check if a specific role title is relevant to the query/technology using taxonomy."""
    if not role_title:
        return False
    title_lower = str(role_title).lower()
    
    syns = get_synonyms_for_query(query)
    strong = syns.get("strong") or []
    related = syns.get("related") or []
    adjacent = syns.get("adjacent") or []
    
    # We want to match if it has any strong, related, or adjacent terms
    match_list = strong + related + adjacent
    
    # Deduct points / reject if recruiter/sales keywords are in it
    neg_kws = ["recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master"]
    for neg in neg_kws:
        if neg in title_lower:
            return False
            
    for kw in match_list:
        if len(kw) <= 4:
            pattern = rf'\b{re.escape(kw)}\b'
            if re.search(pattern, title_lower):
                return True
        else:
            if kw in title_lower:
                return True
                
    return False

def is_c_level_role(role_title: str) -> bool:
    """Check if the title represents a C-level corporate role, VP, director, or owner to exclude them."""
    title_lower = str(role_title or '').lower().strip()
    c_level_patterns = [
        r'\bcto\b', r'\bcio\b', r'\bceo\b', r'\bcfo\b', r'\bcoo\b', r'\bcpo\b', r'\bcro\b',
        r'\bchief\b', r'\bpresident\b', r'\bvp\b', r'\bvice\s+president\b', r'\bdirector\b',
        r'\bfounder\b', r'\bpartner\b', r'\bowner\b', r'\bhead\s+of\b'
    ]
    for pattern in c_level_patterns:
        if re.search(pattern, title_lower):
            return True
    return False

def calculate_relevant_experience_years(history: list, query: str) -> float:
    """Compute relevant experience years based only on relevant jobs."""
    relevant_history = []
    if history:
        for job in history:
            if isinstance(job, dict) and is_role_relevant(job.get('title'), query):
                relevant_history.append(job)
    relevant_months = calculate_employment_months_union(relevant_history)
    return round(len(relevant_months) / 12.0, 1)

def calculate_relevance_score(profile: dict, query: str) -> int:
    """Calculate candidate relevance score between 0 and 100 based on various fields."""
    syns = get_synonyms_for_query(query)
    strong_kws = syns.get("strong") or []
    related_kws = syns.get("related") or []
    adjacent_kws = syns.get("adjacent") or []
    weak_kws = syns.get("weak") or []
    neg_kws = ["recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master"]
    
    score_details = []
    
    # Helper for substring matching
    def has_any(text: str, kw_list: list) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        for kw in kw_list:
            if len(kw) <= 4:
                pattern = rf'\b{re.escape(kw)}\b'
                if re.search(pattern, text_lower):
                    return True
            else:
                if kw in text_lower:
                    return True
        return False

    def count_matches(text: str, kw_list: list) -> int:
        if not text:
            return 0
        text_lower = text.lower()
        count = 0
        for kw in kw_list:
            if len(kw) <= 4:
                pattern = rf'\b{re.escape(kw)}\b'
                if re.search(pattern, text_lower):
                    count += 1
            else:
                if kw in text_lower:
                    count += 1
        return count

    # A. Role Match (Max 40 points)
    role_score = 0
    history = profile.get("experience_history") or []
    current_title = ""
    if history and isinstance(history[0], dict):
        current_title = history[0].get("title") or ""
    if not current_title:
        current_title = (profile.get("current_company") or {}).get("title") if isinstance(profile.get("current_company"), dict) else ""
    current_title = current_title or profile.get("headline") or ""
    
    previous_titles = []
    if len(history) > 1:
        for job in history[1:]:
            if isinstance(job, dict) and job.get("title"):
                previous_titles.append(job["title"])
                
    headline = profile.get("headline") or ""
    
    # Current Title Match points
    if current_title:
        if has_any(current_title, strong_kws):
            role_score += 30
            score_details.append("+30 Current Title Strong Match")
        elif has_any(current_title, related_kws):
            role_score += 20
            score_details.append("+20 Current Title Related Match")
        elif has_any(current_title, adjacent_kws):
            role_score += 10
            score_details.append("+10 Current Title Adjacent Match")
        elif has_any(current_title, weak_kws):
            role_score += 5
            score_details.append("+5 Current Title Weak Match")
            
    # Previous Titles Match points
    prev_matches = 0
    for t in previous_titles:
        if has_any(t, strong_kws) or has_any(t, related_kws):
            prev_matches += 1
    if prev_matches > 0:
        added = min(prev_matches * 5, 10)
        role_score += added
        score_details.append(f"+{added} Previous Titles Match ({prev_matches} matched)")
        
    # Headline points
    if headline:
        if has_any(headline, strong_kws) or has_any(headline, related_kws):
            role_score += 5
            score_details.append("+5 Headline Match")
        elif has_any(headline, adjacent_kws):
            role_score += 3
            score_details.append("+3 Headline Adjacent Match")
            
    # Negative checks
    has_neg = False
    if current_title and has_any(current_title, neg_kws): has_neg = True
    if headline and has_any(headline, neg_kws): has_neg = True
    for t in previous_titles:
        if has_any(t, neg_kws): has_neg = True
        
    if has_neg:
        role_score -= 30
        score_details.append("-30 Negative keyword detected in titles/headline")
        
    role_score = max(0, min(role_score, 40))

    # B. Technical Match (Max 30 points)
    tech_score = 0
    skills_str = ", ".join(profile.get("skills", [])) if isinstance(profile.get("skills"), list) else str(profile.get("skills") or "")
    
    # LinkedIn skills list points
    if skills_str:
        matches = count_matches(skills_str, strong_kws) + count_matches(skills_str, related_kws)
        added = min(matches * 3, 10)
        tech_score += added
        if added > 0:
            score_details.append(f"+{added} LinkedIn Skills Match")
            
    # Certifications points
    certs = profile.get("certifications") or []
    certs_text = " ".join([c.get("title") or c.get("name") or "" for c in certs if isinstance(c, dict)])
    if certs_text:
        matches = count_matches(certs_text, strong_kws) + count_matches(certs_text, related_kws)
        added = min(matches * 5, 10)
        tech_score += added
        if added > 0:
            score_details.append(f"+{added} Certifications Match")
            
        c_text_lower = certs_text.lower()
        cert_bonus = 0
        if any(x in c_text_lower for x in ["ccie", "cissp", "cism", "ceh"]):
            cert_bonus += 5
            score_details.append("+5 Premium Certification Bonus")
        elif any(x in c_text_lower for x in ["ccnp", "aws", "azure", "gcp", "okta", "sailpoint"]):
            cert_bonus += 3
            score_details.append("+3 Technical Certification Bonus")
        tech_score += cert_bonus
        
    # GitHub Repos tech match
    repos = profile.get("repos") or []
    if repos:
        repo_text = " ".join([f"{r.get('name', '')} {r.get('description', '')}" for r in repos if isinstance(r, dict)])
        matches = count_matches(repo_text, strong_kws) + count_matches(repo_text, related_kws)
        added = min(matches * 2, 10)
        tech_score += added
        if added > 0:
            score_details.append(f"+{added} GitHub Repos Tech Match")
            
    tech_score = max(0, min(tech_score, 30))

    # C. Experience Match (Max 15 points)
    exp_score = 0
    relevant_years = calculate_relevant_experience_years(history, query)
    if relevant_years > 0:
        added = min(int(relevant_years * 2), 10)
        exp_score += added
        score_details.append(f"+{added} Relevant Exp Duration ({relevant_years} years)")
        
        is_curr = has_any(current_title, strong_kws) or has_any(current_title, related_kws)
        if is_curr:
            exp_score += 3
            score_details.append("+3 Current Title Role Fit")
            
    # Job descriptions keyword matches
    desc_text = " ".join([job.get("description") or "" for job in history if isinstance(job, dict)])
    if desc_text:
        matches = count_matches(desc_text, strong_kws) + count_matches(desc_text, related_kws)
        added = min(matches * 1, 5)
        exp_score += added
        if added > 0:
            score_details.append(f"+{added} Exp Description Keywords Match")
            
    exp_score = max(0, min(exp_score, 15))

    # D. Evidence Quality (Max 10 points)
    evidence_score = 0
    has_gh = bool(profile.get("github_url"))
    has_li = bool(profile.get("linkedin_url") or profile.get("profile_url"))
    if has_gh and has_li:
        evidence_score += 4
        score_details.append("+4 GitHub and LinkedIn Both Present")
    if profile.get("email") or profile.get("mobile_phone"):
        evidence_score += 2
        score_details.append("+2 Contact Sourced")
    if len(repos) >= 5:
        evidence_score += 2
        score_details.append("+2 Active GitHub Repositories (5+)")
    bio_text = profile.get("bio_text") or ""
    if len(bio_text) > 50:
        evidence_score += 2
        score_details.append("+2 Bio/About Section Populated")
        
    evidence_score = max(0, min(evidence_score, 10))

    # E. Company Match (Max 5 points)
    company_score = 0
    premium_companies = [
        "cisco", "arista", "juniper", "palo alto", "fortinet", "microsoft", "amazon", "google", 
        "meta", "apple", "netflix", "oracle", "ibm", "snowflake", "databricks"
    ]
    curr_comp = (profile.get("current_company") or {}).get("name") if isinstance(profile.get("current_company"), dict) else (profile.get("current_company_name") or "")
    if curr_comp and any(p in str(curr_comp).lower() for p in premium_companies):
        company_score += 5
        score_details.append("+5 Current Company Premium Match")
    else:
        prev_comps = [job.get("company") for job in history if isinstance(job, dict) and job.get("company")]
        if any(any(p in str(pc).lower() for p in premium_companies) for pc in prev_comps):
            company_score += 3
            score_details.append("+3 Previous Company Premium Match")
            
    company_score = max(0, min(company_score, 5))
    
    total_score = role_score + tech_score + exp_score + evidence_score + company_score
    profile['relevance_breakdown'] = {
        'role': role_score,
        'technical': tech_score,
        'experience': exp_score,
        'evidence': evidence_score,
        'company': company_score,
        'details': score_details
    }
    
    return max(0, min(100, total_score))


def has_explicit_negative_identity(profile: dict) -> Tuple[bool, str]:
    """Identify if the candidate themselves is explicitly working in recruiting, HR, staffing, sales, or biz dev."""
    neg_phrases = [
        "technical recruiter", "it recruiter", "staffing recruiter", "sales recruiter",
        "hr recruiter", "recruiting recruiter", "recruiter", "talent acquisition",
        "recruitment consultant", "account executive", "business development",
        "sales representative", "hr manager", "human resources specialist", "headhunter"
    ]
    
    title = str(profile.get("current_title") or profile.get("title") or "").strip().lower()
    bio = str(profile.get("bio_text") or profile.get("bio") or "").strip().lower()
    headline = str(profile.get("headline") or "").strip().lower()
    
    import re
    for phrase in neg_phrases:
        pattern = rf"\b{re.escape(phrase)}\b"
        if re.search(pattern, title) or re.search(pattern, headline):
            return True, f"Explicit negative role '{phrase}' found in title/headline"
        if re.search(pattern, bio):
            bio_match = False
            if any(pref in bio for pref in ["i am a", "i'm a", "working as", "recruiting for", "specialized in", "specialise in", "passionate recruiter"]):
                bio_match = True
            elif bio.startswith(phrase):
                bio_match = True
            elif re.search(rf"\b(recruiter|talent acquisition)\b", bio) and len(bio) < 100:
                bio_match = True
            
            if bio_match:
                return True, f"Explicit negative role '{phrase}' found in bio"
                
    return False, ""


def calculate_discovery_score(gh_profile: dict, query: str, search_context: dict = None) -> int:
    """Calculate pre-scrape Discovery Score (0-100) to check if GitHub candidate is worth live LinkedIn scraping."""
    syns = get_synonyms_for_query(query)
    strong_kws = syns.get("strong") or []
    related_kws = syns.get("related") or []
    adjacent_kws = syns.get("adjacent") or []
    neg_kws = ["recruiter", "talent acquisition", "hr", "marketing", "sales", "scrum master"]
    
    def count_matches(text: str, kw_list: list) -> int:
        if not text:
            return 0
        text_lower = text.lower()
        count = 0
        for kw in kw_list:
            if kw in text_lower:
                count += 1
        return count

    breakdown = {
        "Bio Match": 0,
        "Repository Match": 0,
        "Language Match": 0,
        "Company & Location Match": 0,
        "Search Context Match": 0,
        "Negative Penalties": 0,
        "Unknown Fields": []
    }
    
    # 1. Bio/Headline Match (Max 35 points)
    bio = gh_profile.get("bio_text") or gh_profile.get("bio") or ""
    if bio:
        b_strong = count_matches(bio, strong_kws)
        b_related = count_matches(bio, related_kws)
        b_adjacent = count_matches(bio, adjacent_kws)
        if b_strong > 0:
            breakdown["Bio Match"] = 35
        elif b_related > 0:
            breakdown["Bio Match"] = 20
        elif b_adjacent > 0:
            breakdown["Bio Match"] = 10
            
        if any(neg in bio.lower() for neg in neg_kws):
            breakdown["Negative Penalties"] -= 20
    else:
        breakdown["Unknown Fields"].append("Bio")
            
    # 2. GitHub Repositories (Max 35 points)
    repos = gh_profile.get("repos") or []
    if repos:
        repo_matches = 0
        for r in repos:
            if isinstance(r, dict):
                r_text = f"{r.get('name', '')} {r.get('description', '')}"
                if count_matches(r_text, strong_kws) > 0 or count_matches(r_text, related_kws) > 0:
                    repo_matches += 1
        breakdown["Repository Match"] = min(repo_matches * 7, 35)
    else:
        breakdown["Unknown Fields"].append("Repositories")
    
    # 3. Programming Languages (Max 15 points)
    languages = set()
    for r in repos:
        if isinstance(r, dict) and r.get("language"):
            languages.add(r["language"].lower())
            
    if languages:
        lang_matches = 0
        common_languages = ["python", "go", "golang", "typescript", "javascript", "c++", "rust", "bash", "shell"]
        for lang in languages:
            if lang in common_languages:
                lang_matches += 1
        breakdown["Language Match"] = min(lang_matches * 5, 15)
    else:
        breakdown["Unknown Fields"].append("Languages")
    
    # 4. Company & Location (Max 15 points)
    loc_val = gh_profile.get("location") or ""
    loc_score = 0
    if loc_val:
        is_us = False
        us_indicators = ["usa", "united states", "united states of america", "u s a", "u s"]
        if any(ind in loc_val.lower() for ind in us_indicators) or "us" in loc_val.lower().split():
            is_us = True
        if is_us:
            loc_score += 10
    else:
        breakdown["Unknown Fields"].append("Location")
            
    company = gh_profile.get("company") or ""
    company_score = 0
    if company:
        if any(kw in company.lower() for kw in strong_kws):
            company_score += 5
    else:
        breakdown["Unknown Fields"].append("Company")
        
    breakdown["Company & Location Match"] = loc_score + company_score
    
    # 5. Search Context Match (Max 25 points)
    if search_context:
        sc_score = 0
        
        # A. Query Match (+10 max)
        sc_query = str(search_context.get("query") or query or "").lower()
        if any(kw in sc_query for kw in strong_kws + related_kws):
            sc_score += 10
            
        # B. Title Match (+10 max)
        sc_title = str(search_context.get("title") or "").lower()
        if any(kw in sc_title for kw in strong_kws + related_kws):
            sc_score += 10
            
        # C. Snippet Match (+5 max)
        sc_snippet = str(search_context.get("snippet") or search_context.get("bio_text") or "").lower()
        if any(kw in sc_snippet for kw in strong_kws + related_kws):
            sc_score += 5
            
        breakdown["Search Context Match"] = min(sc_score, 25)
        
    total_score = (
        breakdown["Bio Match"] +
        breakdown["Repository Match"] +
        breakdown["Language Match"] +
        breakdown["Company & Location Match"] +
        breakdown["Search Context Match"] +
        breakdown["Negative Penalties"]
    )
    
    gh_profile["discovery_score_breakdown"] = breakdown
    
    return max(0, min(100, total_score))

def infer_experience_bracket(total_years: Optional[float], current_title: str, all_titles: list) -> str:
    if total_years is None:
        return "Unknown"
    current_title_lower = current_title.lower() if current_title else ""
    all_titles_lower = [t.lower() for t in all_titles if t]
    
    # 1. Direct current title checks
    if any(k in current_title_lower for k in ["director", "vp", "vice president", "head of"]):
        return "Director"
    if "manager" in current_title_lower:
        return "Manager"
    if "staff" in current_title_lower:
        return "Staff"
    if "principal" in current_title_lower:
        return "Principal"
    if "architect" in current_title_lower:
        return "Architect"
    if any(k in current_title_lower for k in ["lead", "leader", "chief"]):
        return "Lead"
    if any(k in current_title_lower for k in ["senior", "sr.", "sr\b"]):
        return "Senior"
        
    # 2. Check history titles
    has_historical_director = any(any(k in t for k in ["director", "vp", "head of"]) for t in all_titles_lower)
    has_historical_manager = any("manager" in t for t in all_titles_lower)
    has_historical_lead = any("lead" in t for t in all_titles_lower)
    has_historical_senior = any(any(k in t for k in ["senior", "sr.", "sr\b"]) for t in all_titles_lower)
    
    # 3. Incorporate total experience duration
    if total_years >= 12:
        if has_historical_director: return "Director"
        if has_historical_manager: return "Manager"
        if "architect" in "".join(all_titles_lower): return "Architect"
        return "Principal"
    if total_years >= 8:
        if has_historical_lead: return "Lead"
        return "Senior"
    if total_years >= 4:
        if has_historical_senior: return "Senior"
        return "Mid-Level"
    if total_years >= 1:
        if any(k in current_title_lower for k in ["junior", "jr", "intern", "entry"]):
            return "Junior"
        return "Junior"
        
    return "Entry Level"

def validate_us_location(profile: dict) -> Tuple[bool, str, str]:
    """Validate if candidate is located in the US using normalized checks."""
    loc_candidates = []
    
    # Layer 1: LinkedIn Location
    li_loc = profile.get("location")
    if li_loc:
        loc_candidates.append(("LinkedIn Location", str(li_loc)))
        
    # Layer 2: Current Company Location
    current_company = profile.get("current_company") or {}
    if isinstance(current_company, dict):
        comp_loc = current_company.get("location")
        if comp_loc:
            loc_candidates.append(("Company Location", str(comp_loc)))
            
    # Layer 3: Experience Locations
    history = profile.get("experience_history") or []
    for job in history:
        if isinstance(job, dict):
            job_loc = job.get("location")
            if job_loc:
                loc_candidates.append(("Experience Location", str(job_loc)))
                
    # Layer 4: Bio/Snippet plain text
    bio_text = profile.get("bio_text")
    if bio_text:
        loc_candidates.append(("Biography/Snippet", str(bio_text)[:300]))
        
    us_indicators = ["usa", "united states", "united states of america", "u s a", "u s", "u.s."]
    us_regions = [
        "bay area", "sf bay area", "silicon valley", "east coast", "west coast",
        "northeast", "north east", "northeast region", "northwest", "north west", "southeast", "south east",
        "southwest", "south west", "midwest", "mid west"
    ]
    # Expanded US cities list
    us_cities = [
        "san francisco", "new york", "seattle", "austin", "boston", "chicago",
        "los angeles", "denver", "atlanta", "dallas", "houston", "miami",
        "phoenix", "philadelphia", "detroit", "washington", "baltimore", "pittsburgh",
        "fort wayne", "portland", "san jose", "san diego", "las vegas", "charlotte",
        "indianapolis", "minneapolis", "st paul", "columbus", "cleveland", "cincinnati",
        "orlando", "tampa", "salt lake city", "nashville", "memphis", "st louis",
        "kansas city", "oklahoma city", "milwaukee", "raleigh", "durham"
    ]
    non_us_indicators = [
        "india", "uk", "united kingdom", "canada", "germany", "australia", "france",
        "brazil", "nigeria", "ukraine", "pakistan", "bangladesh", "russia", "china",
        "singapore", "netherlands", "sweden", "japan", "london", "bangalore", "hyderabad",
        "mumbai", "toronto", "vancouver", "berlin", "munich", "sydney", "melbourne"
    ]
    
    state_names_lower = {s.lower() for s in US_STATES}
    state_abbrevs_lower = {a.lower() for a in US_STATE_ABBREVS}
    
    reasons = []
    
    def clean_loc_str(val: str) -> str:
        val = str(val).lower()
        val = re.sub(r'[^\w\s]', ' ', val)
        return " ".join(val.split())
        
    def check_indicators(text: str) -> Tuple[bool, bool, List[str]]:
        has_us = False
        has_non_us = False
        found_reasons = []
        
        words = text.split()
        
        # Check explicit US terms
        if any(ind in text for ind in us_indicators) or "us" in words:
            has_us = True
            found_reasons.append("US Country code/name detected")
        if any(reg in text for reg in us_regions):
            has_us = True
            found_reasons.append("US Region name detected")
        for state in state_names_lower:
            if state in text:
                has_us = True
                found_reasons.append(f"US State name ({state}) detected")
        for city in us_cities:
            if city in text:
                has_us = True
                found_reasons.append(f"US City name ({city}) detected")
        for w in words:
            if w in state_abbrevs_lower:
                has_us = True
                found_reasons.append(f"US State Abbrev ({w.upper()}) detected")
                
        # Check non-US
        for non_ind in non_us_indicators:
            if non_ind in text:
                has_non_us = True
                found_reasons.append(f"Non-US Indicator ({non_ind}) detected")
                
        return has_us, has_non_us, found_reasons

    # Check LinkedIn Location (Primary indicator)
    li_loc_raw = profile.get("location") or ""
    if li_loc_raw.strip().lower() in ("not_available", "not available", "none", "unknown", "null", "undefined", "n/a", ""):
        li_loc_raw = ""
    JOB_HEADLINE_KEYWORDS = {'engineer', 'developer', 'analyst', 'specialist', 'technician', 'consultant', 'architect', 'manager', 'director', 'lead', 'support', 'administrator', 'looking for', 'seeking', 'open to work'}
    if '|' in li_loc_raw or (len(li_loc_raw) > 60 and any(kw in li_loc_raw.lower() for kw in JOB_HEADLINE_KEYWORDS)):
        li_loc_raw = ""

    li_loc_clean = clean_loc_str(li_loc_raw)
    li_us, li_non_us, li_reasons = check_indicators(li_loc_clean)
    
    status = None
    if li_loc_raw:
        if li_us and not li_non_us:
            status = "US_CONFIRMED"
            reasons.extend([f"LinkedIn Location confirmed: {r}" for r in li_reasons])
        elif li_non_us and not li_us:
            status = "NON_US"
            reasons.extend([f"LinkedIn Location Non-US: {r}" for r in li_reasons])
        elif li_us and li_non_us:
            status = "US_AMBIGUOUS"
            reasons.extend([f"LinkedIn Location mixed: {r}" for r in li_reasons])

    if not status:
        # Check current company and experience location
        comp_loc_raw = (profile.get("current_company") or {}).get("location") if isinstance(profile.get("current_company"), dict) else ""
        comp_loc_clean = clean_loc_str(comp_loc_raw)
        comp_us, comp_non_us, comp_reasons = check_indicators(comp_loc_clean)
        
        if comp_loc_raw and comp_us and not comp_non_us:
            status = "US_LIKELY"
            reasons.extend([f"Current Company Location: {r}" for r in comp_reasons])
        else:
            # Check experience locations
            exp_has_us = False
            exp_has_non_us = False
            exp_reasons = []
            for job in profile.get("experience_history") or []:
                if isinstance(job, dict):
                    job_loc_raw = job.get("location") or ""
                    job_loc_clean = clean_loc_str(job_loc_raw)
                    j_us, j_non_us, j_reasons = check_indicators(job_loc_clean)
                    if j_us: 
                        exp_has_us = True
                        exp_reasons.extend(j_reasons)
                    if j_non_us: 
                        exp_has_non_us = True
                        exp_reasons.extend(j_reasons)
            
            if exp_has_us and not exp_has_non_us:
                status = "US_LIKELY"
                reasons.extend([f"Historical Experience US: {r}" for r in exp_reasons])
            elif exp_has_us and exp_has_non_us:
                status = "US_AMBIGUOUS"
                reasons.extend([f"Historical Experience Mixed: {r}" for r in exp_reasons])
            else:
                # Check biography text
                bio_us, bio_non_us, bio_reasons = check_indicators(clean_loc_str(profile.get("bio_text") or ""))
                if bio_us and not bio_non_us:
                    status = "US_LIKELY"
                    reasons.extend([f"Bio Text US: {r}" for r in bio_reasons])
                elif bio_us and bio_non_us:
                    status = "US_AMBIGUOUS"
                    reasons.extend([f"Bio Text Mixed: {r}" for r in bio_reasons])
                else:
                    status = "NON_US"
                    reasons.append("No US indicators found across profile layers")
                    
    # Configurable location policy
    allowed_statuses = ["US_CONFIRMED", "US_LIKELY"]
    config_allowed = os.getenv("ALLOWED_LOCATION_STATUSES")
    if config_allowed:
        allowed_statuses = [s.strip().upper() for s in config_allowed.split(",")]
        
    is_us = status in allowed_statuses
    
    # Print location audit log
    print(f"[LOCATION AUDIT] Raw values check:")
    print(f"  LinkedIn Location Raw: '{li_loc_raw}'")
    print(f"  Final Decision Status: {status} | Allowed: {allowed_statuses} | Pass: {is_us}")
    
    return is_us, status, "; ".join(reasons)


def is_c2c_candidate(profile: dict, keywords: list = C2C_KEYWORDS) -> Tuple[bool, Optional[str]]:
    """Scan all bio, headline, skills, current company and experience history fields for C2C/C2H indicators."""
    text_parts = []
    text_parts.append(profile.get("full_name") or "")
    text_parts.append(profile.get("bio_text") or "")
    
    skills = profile.get("skills") or []
    if isinstance(skills, list):
        text_parts.append(" ".join(skills))
    else:
        text_parts.append(str(skills))
        
    current_company = profile.get("current_company") or {}
    if isinstance(current_company, dict):
        text_parts.append(current_company.get("name") or "")
        text_parts.append(current_company.get("title") or "")
        
    history = profile.get("experience_history") or []
    for job in history:
        if isinstance(job, dict):
            text_parts.append(job.get("company") or "")
            text_parts.append(job.get("title") or "")
            text_parts.append(job.get("description") or "")
            
    search_text = " ".join(text_parts).lower()
    
    for kw in keywords:
        pattern = rf'\b{re.escape(kw.lower())}\b'
        if re.search(pattern, search_text):
            return True, kw
    return False, None

def extract_and_validate_contacts(profile: dict) -> Tuple[str, str]:
    """Perform robust search of profile text and bio to extract and validate emails and phone numbers."""
    bio = profile.get("bio_text") or ""
    
    # 1. Email Extraction
    email_candidates = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', bio)
    if profile.get("email"):
        email_candidates.insert(0, profile["email"])
        
    valid_email = ""
    for email in email_candidates:
        email_clean = email.strip()
        try:
            validate_email(email_clean, check_deliverability=False)
            valid_email = email_clean
            break
        except EmailNotValidError:
            continue
            
    # 2. Phone Extraction
    phone_candidates = []
    if profile.get("mobile_phone"):
        phone_candidates.append(profile["mobile_phone"])
    # Find numbers inside bio
    phone_matches = phonenumbers.PhoneNumberMatcher(bio, "US")
    for match in phone_matches:
        phone_candidates.append(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164))
        
    valid_phone = ""
    for phone in phone_candidates:
        try:
            parsed = phonenumbers.parse(phone, "US")
            if phonenumbers.is_valid_number(parsed):
                valid_phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                break
        except Exception:
            continue
            
    return valid_email, valid_phone


def _get_displayed_experience(profile: dict) -> Optional[int]:
    val = profile.get("years_of_experience") or profile.get("years_of_exp")
    if val and val != "Not available" and str(val).strip() != "":
        # Try to extract first number
        digits = re.findall(r'\b\d+\b', str(val))
        if digits:
            return int(digits[0])
    return None


def _calculate_experience_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    # Calculate from year ranges in text
    year_ranges = re.findall(r'\b(200[3-9]|201[0-9]|202[0-6])\s*[-–—to]+\s*(200[3-9]|201[0-9]|202[0-6]|present)\b', text, re.IGNORECASE)
    if year_ranges:
        total_span = 0
        for start, end in year_ranges:
            start_yr = int(start)
            end_yr = 2026 if end.lower() == 'present' else int(end)
            span = end_yr - start_yr
            if span > 0:
                total_span += span
        if total_span > 0:
            return total_span
    return None


def _parse_experience_from_bio(text: str) -> Optional[int]:
    # Look for explicit statements like "X years of experience" or similar
    patterns = [
        r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
        r'(\d+)\+?\s*years?\s+(?:as\s+a\s+)?(?:engineer|developer|architect|consultant|manager)',
        r'(\d+)\+?\s*yrs?\s+(?:of\s+)?experience',
        r'experience[:\s]+(\d+)\+?\s*years?',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _parse_experience_from_recommendations(profile: dict) -> Optional[int]:
    recs = profile.get("recommendations") or []
    for rec in recs:
        if not isinstance(rec, str):
            continue
        m = re.search(r'\b(\d+)\+?\s*years?\b', rec, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _calculate_experience_from_education(profile: dict) -> Optional[int]:
    education = profile.get("education") or []
    if not education and isinstance(profile.get("education_details"), list):
        education = profile.get("education_details")
    
    end_years = []
    for edu in education:
        if not isinstance(edu, dict):
            continue
        end_yr = edu.get("end_year") or edu.get("end_date")
        if end_yr and str(end_yr).isdigit():
            end_years.append(int(end_yr))
    if end_years:
        grad_year = min(end_years)
        if grad_year < 2026:
            return 2026 - grad_year
    return None


def _calculate_experience_from_certifications(profile: dict) -> Optional[int]:
    certs = profile.get("certifications") or []
    years = []
    for cert in certs:
        if not isinstance(cert, dict):
            continue
        meta = cert.get("meta") or ""
        m = re.search(r'\b(19\d{2}|20\d{2})\b', meta)
        if m:
            years.append(int(m.group(1)))
    if years:
        oldest_cert = min(years)
        if oldest_cert < 2026:
            return 2026 - oldest_cert
    return None


def _calculate_experience_from_github_age(profile: dict) -> Optional[int]:
    created_at = profile.get("created_at")
    if created_at:
        try:
            year = int(created_at.split("-")[0])
            if year < 2026:
                return 2026 - year
        except Exception:
            pass
    return None


def qualify_candidate_set1(profile: dict, query: str) -> Optional[Set1Candidate]:
    """Qualify the candidate, run all pre-export validations, and log structured rejections."""
    bio_text = profile.get("bio_text") or ""
    
    # Check if this profile represents an Organization account (early filtering check)
    account_type = profile.get('account_type') or 'User'
    if account_type == 'Organization':
        logger.warning(f"Rejected: GitHub Organization account type filtered for candidate '{profile.get('full_name')}'")
        profile['rejection_stage'] = 'Identity Validation'
        profile['rejection_reason'] = 'GitHub account type is Organization'
        profile['rejection_category'] = 'ORGANIZATION'
        return None

    # 1. Name Check
    name = profile.get("full_name") or ""
    if not is_full_name_valid(name):
        logger.warning(f"Rejected: Missing Full Name for identifier '{profile.get('profile_url') or 'Unknown'}'")
        profile['rejection_stage'] = 'GitHub/LinkedIn Validation'
        profile['rejection_reason'] = 'Missing or invalid real full name'
        profile['rejection_category'] = 'INVALID_PROFILE'
        return None
        
    # Ensure BOTH LinkedIn URL and GitHub URL are present
    github_url = (profile.get("github_url") or "").strip()
    linkedin_url = (profile.get("linkedin_url") or profile.get("profile_url") or "").strip()

    is_direct_linkedin = (github_url.lower() == "not available" or (linkedin_url and not github_url))
    if not is_direct_linkedin and (not github_url or github_url.lower() == "not available"):
        logger.warning(f"Rejected: Missing GitHub URL for candidate '{name}'")
        profile['rejection_stage'] = 'GitHub Validation'
        profile['rejection_reason'] = 'Missing GitHub URL link'
        profile['rejection_category'] = 'INCOMPLETE_PROFILE'
        return None
    if is_direct_linkedin and not github_url:
        github_url = "Not Available"
        profile["github_url"] = "Not Available"
    if not linkedin_url:
        logger.warning(f"Rejected: Missing LinkedIn URL for candidate '{name}'")
        profile['rejection_stage'] = 'LinkedIn Validation'
        profile['rejection_reason'] = 'Missing LinkedIn URL link'
        profile['rejection_category'] = 'LINKEDIN_NOT_RESOLVED'
        return None
        
    # 3. C2C Check
    is_c2c, matched_kw = is_c2c_candidate(profile)
    if is_c2c:
        logger.warning(f"Rejected: C2C Candidate '{name}' matched keyword '{matched_kw}'")
        profile['rejection_stage'] = 'Employment Type Validation'
        profile['rejection_reason'] = f"C2C Candidate matched keyword '{matched_kw}'"
        profile['rejection_category'] = 'RECRUITER_OR_SALES'
        return None
        
    # 4. Extract Contacts (Optional in SET 1)
    email, phone = extract_and_validate_contacts(profile)
     # 5. Experience, Title, and Skills Sourced Strictly from Authoritative LinkedIn Profile
    history = profile.get("experience_history") or []
    
    def is_valid_data(val):
        if val is None:
            return False
        if isinstance(val, (str, list, dict)) and not val:
            return False
        if isinstance(val, str) and val.strip().lower() in ("unknown", "not available", "n/a", "null", "none", ""):
            return False
        return True

    # --- 5.1. Title Extraction (LinkedIn with Multi-Source Fallbacks) ---
    current_title = "Unknown"
    title_source = "unavailable"
    
    # 1. LinkedIn current position title
    if history and isinstance(history[0], dict):
        hist_title = history[0].get("title")
        if is_valid_data(hist_title):
            current_title = hist_title.strip()
            title_source = "linkedin_position"
        
    # 2. LinkedIn headline / position
    if current_title == "Unknown":
        bd_headline = profile.get("headline") or profile.get("position")
        if is_valid_data(bd_headline):
            current_title = bd_headline.strip()
            title_source = "linkedin_headline"

    # 3. Current employment entry
    if current_title == "Unknown":
        curr_company = profile.get("current_company")
        if isinstance(curr_company, dict) and curr_company.get("title"):
            comp_title = curr_company.get("title")
            if is_valid_data(comp_title):
                current_title = comp_title.strip()
                title_source = "linkedin_current_company"

    # 4. Fallback from bio, company, or search context
    if current_title == "Unknown":
        bio_candidate = profile.get("bio_text") or profile.get("bio") or ""
        company_val = profile.get("company") or ""
        m_title = re.search(r'\b((?:Senior\s+|Lead\s+|Principal\s+|Staff\s+|Chief\s+)?(?:Software\s+Engineer|Data\s+Engineer|Analytics\s+Engineer|Cloud\s+Architect|DevOps\s+Engineer|Full[- ]?Stack\s+Developer|Backend\s+Engineer|Frontend\s+Engineer|Machine\s+Learning\s+Engineer|Data\s+Scientist|Database\s+Administrator|Solutions\s+Architect|Platform\s+Engineer|Security\s+Engineer|Systems\s+Engineer|Consultant|Architect|Developer|Engineer))\b', bio_candidate, re.IGNORECASE)
        if m_title:
            current_title = m_title.group(1).title()
            title_source = "fallback_bio"
        elif is_valid_data(company_val):
            m_comp = re.search(r'\b((?:Senior\s+|Lead\s+|Principal\s+)?(?:Engineer|Developer|Architect|Scientist|Consultant|Specialist))\b', company_val, re.IGNORECASE)
            if m_comp:
                current_title = m_comp.group(1).title()
                title_source = "fallback_company"
            else:
                current_title = f"{query.title().rstrip('s')}"
                title_source = "fallback_query_role"
        else:
            current_title = f"{query.title().rstrip('s')}"
            title_source = "fallback_query_role"

    # --- 5.2. Experience Calculation (Multi-Tier Fallback Ladder) ---
    relevant_experience_years = None
    experience_source = "linkedin_experience_timeline"
    experience_confidence = "NONE"

    # 1. Primary: LinkedIn experience timeline union (High Confidence)
    if history:
        union_months = calculate_employment_months_union(history)
        if union_months:
            relevant_experience_years = round(len(union_months) / 12.0, 1)
            experience_confidence = "HIGH"
            experience_source = "linkedin_experience_timeline"

    # 2. Fallback: Pre-parsed / Displayed Experience (Medium Confidence)
    if relevant_experience_years is None:
        disp_exp = _get_displayed_experience(profile)
        if disp_exp and disp_exp > 0:
            relevant_experience_years = float(disp_exp)
            experience_confidence = "MEDIUM"
            experience_source = "displayed_experience"

    # 3. Fallback: Explicit Bio / Headline Statement (Medium Confidence)
    if relevant_experience_years is None:
        full_bio = f"{profile.get('bio_text', '')} {profile.get('headline', '')} {profile.get('about', '')} {profile.get('position', '')}"
        bio_exp = _parse_experience_from_bio(full_bio)
        if bio_exp and bio_exp > 0:
            relevant_experience_years = float(bio_exp)
            experience_confidence = "MEDIUM"
            experience_source = "bio_text_statement"

    # 4. Fallback: Text Year Ranges (e.g. 2018 - Present, 2016 - 2023) (Medium Confidence)
    if relevant_experience_years is None:
        full_bio = f"{profile.get('bio_text', '')} {profile.get('headline', '')} {profile.get('about', '')}"
        text_exp = _calculate_experience_from_text(full_bio)
        if text_exp and text_exp > 0:
            relevant_experience_years = float(min(text_exp, 35))
            experience_confidence = "MEDIUM"
            experience_source = "text_year_ranges"

    # 5. Fallback: Education Graduation Year (Medium Confidence)
    if relevant_experience_years is None:
        edu_list = profile.get("education") or []
        grad_years = []
        for edu in edu_list:
            if isinstance(edu, dict):
                ey = edu.get("end_year") or edu.get("start_year")
                if ey:
                    m_yr = re.search(r'\b(19\d{2}|20[0-2]\d)\b', str(ey))
                    if m_yr:
                        grad_years.append(int(m_yr.group(1)))
        if grad_years:
            latest_grad = max(grad_years)
            if 1980 <= latest_grad <= 2026:
                edu_exp = max(1, 2026 - latest_grad)
                relevant_experience_years = float(min(edu_exp, 35))
                experience_confidence = "MEDIUM"
                experience_source = "education_graduation_year"

    # 6. Fallback: GitHub Account Age (Medium Confidence)
    if relevant_experience_years is None:
        created_at = profile.get("created_at")
        if created_at:
            m_gh = re.search(r'\b(200[8-9]|201\d|202[0-6])\b', str(created_at))
            if m_gh:
                gh_exp = max(1, 2026 - int(m_gh.group(1)))
                relevant_experience_years = float(min(gh_exp, 25))
                experience_confidence = "MEDIUM"
                experience_source = "github_account_age"

    # 7. Fallback: Role Seniority Inference (Conservative Heuristic) (Medium Confidence)
    if relevant_experience_years is None:
        target_text = f"{current_title} {profile.get('headline', '')} {profile.get('bio_text', '')}".lower()
        if any(w in target_text for w in ["principal", "staff", "architect", "director", "head of", "chief"]):
            relevant_experience_years = 10.0
            experience_confidence = "MEDIUM"
            experience_source = "title_seniority_principal"
        elif any(w in target_text for w in ["lead", "manager", "tech lead"]):
            relevant_experience_years = 7.0
            experience_confidence = "MEDIUM"
            experience_source = "title_seniority_lead"
        elif any(w in target_text for w in ["senior", "sr.", "sr "]):
            relevant_experience_years = 5.0
            experience_confidence = "MEDIUM"
            experience_source = "title_seniority_senior"
        elif any(w in target_text for w in ["junior", "jr.", "entry", "intern", "associate"]):
            relevant_experience_years = 1.0
            experience_confidence = "MEDIUM"
            experience_source = "title_seniority_junior"
        else:
            relevant_experience_years = 3.0
            experience_confidence = "MEDIUM"
            experience_source = "title_seniority_mid"

    profile["current_title"] = current_title
    
    # --- 5.3. Skills Extraction (LinkedIn Sourced Only) ---
    skills_list = []
    skills_source = "unavailable"

    def extract_skills_from_text(text):
        if not text:
            return []
        found = []
        common_keywords = [
            "python", "go", "golang", "c++", "java", "rust", "terraform", "ansible", "cisco",
            "bgp", "ospf", "kubernetes", "docker", "aws", "azure", "gcp", "pytorch", "tensorflow",
            "machine learning", "deep learning", "neural networks", "nlp", "computer vision"
        ]
        for kw in common_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', str(text).lower()):
                found.append(kw.title() if kw != "nlp" else "NLP")
        return found

    # 1. LinkedIn skills section
    li_skills = profile.get("skills")
    if li_skills and isinstance(li_skills, list) and len(li_skills) > 0:
        real_skills = [s for s in li_skills if is_valid_data(s)]
        if real_skills:
            skills_list = real_skills
            skills_source = "linkedin_skills"

    # 2. LinkedIn text keywords
    if not skills_list:
        desc_texts = []
        if profile.get("headline"):
            desc_texts.append(profile.get("headline"))
        if profile.get("about"):
            desc_texts.append(profile.get("about"))
        if history:
            for job in history:
                if isinstance(job, dict) and job.get("description"):
                    desc_texts.append(job.get("description"))
        combined_text = " ".join(desc_texts)
        found = extract_skills_from_text(combined_text)
        if found:
            skills_list = found
            skills_source = "linkedin_text_inference"

    if skills_list:
        profile["skills"] = skills_list
        skills_str = ", ".join(skills_list)
    else:
        profile["skills"] = []
        skills_str = "NOT_AVAILABLE"
        skills_source = "unavailable"

    profile["experience_source"] = experience_source
    profile["experience_confidence"] = experience_confidence
    profile["title_source"] = title_source
    profile["skills_source"] = skills_source

    relevance_score = calculate_relevance_score(profile, query)

    # Determine validation statuses & explicit states
    title_status = STATUS_UNKNOWN
    if current_title and current_title != "Unknown":
        if is_role_relevant(current_title, query):
            title_status = STATUS_MATCH
        else:
            title_status = STATUS_MISMATCH
    else:
        if profile.get("enrichment_status") in ("ENRICHMENT_FAILED", "API_RATE_LIMITED"):
            title_status = STATUS_EXTRACTION_FAILED
        else:
            title_status = STATUS_NOT_AVAILABLE
            
    experience_status = STATUS_NOT_AVAILABLE
    if relevant_experience_years is not None and relevant_experience_years > 0:
        experience_status = STATUS_MATCH
    elif profile.get("enrichment_status") in ("ENRICHMENT_FAILED", "API_RATE_LIMITED"):
        experience_status = STATUS_EXTRACTION_FAILED
                
    skills_status = STATUS_UNKNOWN
    if skills_list:
        syns = get_synonyms_for_query(query)
        strong_kws = syns.get("strong") or []
        has_tech_skills = any(kw in ", ".join(skills_list).lower() for kw in strong_kws)
        if has_tech_skills:
            skills_status = STATUS_MATCH
        else:
            skills_status = STATUS_MISMATCH
    else:
        if profile.get("enrichment_status") in ("ENRICHMENT_FAILED", "API_RATE_LIMITED"):
            skills_status = STATUS_EXTRACTION_FAILED
        else:
            skills_status = STATUS_NOT_AVAILABLE

    relevance_band = "Not Relevant"
    if relevance_score >= 80:
        relevance_band = "Strong Match"
    elif relevance_score >= 65:
        relevance_band = "Qualified Match"
    elif relevance_score >= 50:
        relevance_band = "Enrichment / Review"
    elif relevance_score >= 35:
        relevance_band = "Weak Match"
        
    # SET 1 Field Availability Checks
    has_name = bool(name and is_full_name_valid(name))
    has_tech = bool(query)
    
    # Years of experience is valid if not None, status is not NOT_AVAILABLE / EXTRACTION_FAILED / UNKNOWN, and confidence is HIGH / MEDIUM
    has_exp = bool(
        relevant_experience_years is not None 
        and experience_status not in ("NOT_AVAILABLE", "EXTRACTION_FAILED", "UNKNOWN")
        and experience_confidence in ("HIGH", "MEDIUM")
    )
    
    has_linkedin = bool(linkedin_url)
    
    is_direct_linkedin = (github_url.lower() == "not available" or (linkedin_url and not github_url))
    has_github = bool(github_url and (github_url.lower() != "not available" or is_direct_linkedin))
    
    is_passed = has_name and has_tech and has_exp and has_linkedin and has_github
    
    missing_fields_list = []
    if not has_name: missing_fields_list.append("Full Name")
    if not has_tech: missing_fields_list.append("Technology")
    if not has_exp: missing_fields_list.append("Years of Experience")
    if not has_linkedin: missing_fields_list.append("LinkedIn URL")
    if not has_github: missing_fields_list.append("GitHub URL")
    
    # Print profile enrichment logs in exact template requested by user
    print("[PROFILE ENRICHMENT]")
    print()
    print(f"Name: {name}")
    print(f"LinkedIn: {linkedin_url}")
    bd_exp_log = "Available" if history else "Null"
    fb_exp_log = f"{relevant_experience_years} years ({experience_source})" if not history and relevant_experience_years is not None else "None"
    final_exp_log = f"{relevant_experience_years} years" if relevant_experience_years is not None else "None"
    print(f"Bright Data Experience: {bd_exp_log}")
    print(f"Fallback Experience: {fb_exp_log}")
    print(f"Final Experience: {final_exp_log}")
    print(f"Experience Source: {experience_source}")
    print(f"Experience Confidence: {experience_confidence}")
    print()
    bd_pos_log = profile.get("position") or "Null"
    fb_title_log = current_title if title_source not in ("linkedin_position", "linkedin_headline") else "None"
    print(f"Bright Data Position: {bd_pos_log}")
    print(f"Fallback Title: {fb_title_log}")
    print(f"Final Title: {current_title}")
    print(f"Title Source: {title_source}")
    print()
    bd_skills_log = "Available" if li_skills else "Null"
    fb_skills_log = ", ".join(skills_list) if skills_source != "linkedin_skills" and skills_list else "None"
    print(f"LinkedIn Skills: {bd_skills_log}")
    print(f"Fallback Skills: {fb_skills_log}")
    print(f"Final Skills: {skills_str}")
    print(f"Skills Source: {skills_source}")
    # Raw Bright Data Diagnostics Logging
    print("[RAW BRIGHT DATA RESPONSE DIAGNOSTICS]")
    provider_name = profile.get("data_source") or "Bright Data"
    print(f"Provider:\n{provider_name}")
    print()
    raw_exp = None
    if "linkedin_raw_response" in profile:
        raw_exp = profile["linkedin_raw_response"].get("experience")
    print(f"Raw Experience Field:\n{raw_exp}")
    print()
    print(f"Normalized Experience History Count:\n{len(history)}")
    print()
    print(f"Experience Source:\n{experience_source}")
    print()
    print(f"Experience Status:\n{'CALCULATED' if relevant_experience_years is not None else 'NOT_AVAILABLE'}")
    print()

    # Provider Diagnostics Logging
    print("[PROVIDER DIAGNOSTICS]")
    print(f"LinkedIn Provider: {provider_name}")
    print(f"Experience Source: {experience_source}")
    print(f"Experience Status: {experience_status}")
    print(f"Experience History Count: {len(history)}")
    print(f"Experience Calculation Status: {'CALCULATED' if relevant_experience_years is not None else 'NOT_AVAILABLE'}")
    print(f"Experience Data Available From LinkedIn: {'YES' if history else 'NO'}")
    print()

    print("[SET 1 FIELD VALIDATION]")
    print()
    print(f"Full Name          : {'PASS' if has_name else 'FAIL'}")
    print(f"Technology         : {'PASS' if has_tech else 'FAIL'}")
    print(f"Years Experience   : {'PASS' if has_exp else 'FAIL'}")
    print(f"LinkedIn URL       : {'PASS' if has_linkedin else 'FAIL'}")
    print(f"GitHub URL         : {'PASS' if has_github else 'FAIL'}")
    print()
    print(f"SET 1 RESULT       : {'PASS' if is_passed else 'REJECT'}")
    print(f"Missing Fields     : {', '.join(missing_fields_list) if missing_fields_list else 'None'}")
    print()
    
    if not is_passed:
        logger.warning(f"Rejected: Relevance check failed for candidate '{name}' (Missing: {', '.join(missing_fields_list)})")
        profile['rejection_stage'] = 'Identity Validation'
        profile['rejection_reason'] = f"Missing required fields: {', '.join(missing_fields_list)}"
        profile['rejection_category'] = 'INCOMPLETE_PROFILE'
        return None

    # Save scores and status info onto the profile dict so it goes to excel
    profile['relevance_score'] = relevance_score
    profile['discovery_score'] = profile.get('discovery_score')
    profile['relevance_band'] = relevance_band
    profile['location_status'] = profile.get('location_status') or "US_CONFIRMED"
    profile['rejection_category'] = "RELEVANT"
    
    # Bracket & Seniority calculation
    total_exp_rounded = None
    if relevant_experience_years is not None:
        total_exp_rounded = int(round(relevant_experience_years))
    
    all_titles = [job.get("title") for job in history if isinstance(job, dict)]
    bracket = infer_experience_bracket(total_exp_rounded, current_title, all_titles)
    
    # LinkedIn account age sanity check
    joined_linkedin = None
    m = re.search(r'joined\s+linkedin[:\s]+(\d{4})', bio_text, re.IGNORECASE)
    if m:
        joined_linkedin = int(m.group(1))
        
    is_valid = True
    if joined_linkedin is not None:
        linkedin_age = 2026 - joined_linkedin
        is_valid = (total_exp_rounded <= linkedin_age + 1)
        
    validation_status = "Valid" if is_valid else "Invalid"
    pipeline_stage = "Qualified" if is_passed else "Set 1 Failed"
    
    if not is_valid:
        logger.warning(f"Rejected: Low Confidence for candidate '{name}' (Joined: {joined_linkedin}, Exp: {total_exp_rounded} > Age: {linkedin_age} + 1)")
        profile['rejection_stage'] = 'Sanity Check'
        profile['rejection_reason'] = f'Scraped Experience ({total_exp_rounded}) exceeds LinkedIn Account Age ({linkedin_age}) by more than 1 year'
        profile['rejection_category'] = 'INVALID_PROFILE'
        return None
        
    logger.info(f"Candidate '{name}' Passed SET 1 with {total_exp_rounded} years ({bracket})")

    # 8. Local Ollama Talent Acquisition Specialist & Profile Analyzer
    from skills.profile_scraper.llm_analyzer import TalentAcquisitionAnalyzer
    ta_analyzer = TalentAcquisitionAnalyzer()
    ta_eval = ta_analyzer.evaluate_candidate(profile, query)

    ta_decision = ta_eval.get("decision", "QUALIFIED")
    ta_score = ta_eval.get("score", 70)
    ta_seniority = ta_eval.get("seniority", "Mid-Level")
    ta_fit_summary = ta_eval.get("fit_summary", "Not Available")
    ta_key_strengths = ta_eval.get("key_strengths", "Not Available")

    if ta_decision == "REJECTED":
        rejection_reason = ta_eval.get("rejection_reason") or f"TA Specialist rejected: Low technical relevance ({ta_score}/100)"
        logger.warning(f"[SET 1] TA Specialist Rejected candidate '{name}': {rejection_reason}")
        profile['rejection_stage'] = 'TA Specialist Evaluation'
        profile['rejection_reason'] = rejection_reason
        profile['rejection_category'] = 'NOT_RELEVANT'
        return None

    skills_str = ", ".join(skills_list) if isinstance(skills_list, list) else str(skills_list)
    curr_comp = (profile.get("current_company") or {}).get("name") if isinstance(profile.get("current_company"), dict) else (profile.get("current_company_name") or "")
    
    field_status = profile.get("linkedin_field_status") or {}
    
    clr_val = profile.get("security_clearance")
    if not clr_val or str(clr_val).strip().lower() in ("not available", "unknown", "none", "null", "not found", ""):
        clr_val = "Not Available"
        
    visa_val = profile.get("visa_status")
    if not visa_val or str(visa_val).strip().lower() in ("unknown", "not available", "none", "null", ""):
        visa_val = "Not Available"

    return Set1Candidate(
        technology=query,
        github_url=profile.get("github_url") or "Not Available",
        linkedin_url=profile.get("linkedin_url") or profile.get("profile_url") or "",
        joined_linkedin=joined_linkedin,
        full_name=name,
        years_of_experience=total_exp_rounded,
        experience_bracket=bracket,
        location=profile.get("location") or "USA",
        current_company=curr_comp or "Not Available",
        email=email or "Not Available",
        phone=phone or "Not Available",
        confidence_score="High",
        experience_validation_status=validation_status,
        current_pipeline_stage=pipeline_stage,
        skills=skills_str,
        current_title=current_title or "Not Available",
        security_clearance=clr_val,
        visa_status=visa_val,
        relevance_score=relevance_score,
        discovery_score=profile.get("discovery_score"),
        relevance_band=relevance_band,
        location_status=profile.get("location_status") or "US_CONFIRMED",
        rejection_category="RELEVANT",
        enrichment_status=profile.get("enrichment_status") or "SUCCESS",
        data_quality_status="Good",
        website=profile.get("website") or "",
        portfolio=profile.get("portfolio") or "",
        age=profile.get("age") or "Not Available",
        gender=profile.get("gender") or "Not Available",
        ta_decision=ta_decision,
        ta_score=ta_score,
        ta_seniority=ta_seniority,
        ta_fit_summary=ta_fit_summary,
        ta_key_strengths=ta_key_strengths,
        experience_source=experience_source,
        experience_confidence=experience_confidence,
        title_source=title_source,
        linkedin_field_status=field_status
    )


def is_search_result_open_to_work(result: dict) -> Tuple[bool, str]:
    """
    Evaluates whether a search result's title or snippet contains active Open to Work terminology.
    Prevents launching Playwright browser sessions for candidates who are not actively seeking work.
    """
    if not isinstance(result, dict):
        return False, "Not a dictionary"

    title = str(result.get("title") or "")
    snippet = str(result.get("snippet") or result.get("description") or "")
    combined = f"{title} {snippet}".lower()

    # Authoritative Open to Work patterns
    otw_patterns = [
        r'#?open_?to_?work',
        r'\bopen to (?:work|opportunities|new opportunities|roles|new roles|relocat\w+|contracts?)\b',
        r'\bactively looking\b',
        r'\bactively seeking\b',
        r'\bseeking (?:new )?(?:opportunit\w+|roles?|positions?|jobs?|c2c|employment)\b',
        r'\blooking for (?:new )?(?:opportunit\w+|roles?|positions?|jobs?|c2c|employment)\b',
        r'\bavailable for (?:hire|roles?|work|opportunities|new roles?)\b',
        r'\bavailable immediately\b',
        r'\bimmediate joiner\b',
        r'\bready to work\b',
        r'\bin transition\b',
        r'\bopen for (?:new )?(?:opportunit\w+|roles?|positions?)\b'
    ]

    for pat in otw_patterns:
        m = re.search(pat, combined, re.IGNORECASE)
        if m:
            return True, f"Search context matched: '{m.group(0)}'"

    return False, "No Open to Work indicators in search snippet or title"

