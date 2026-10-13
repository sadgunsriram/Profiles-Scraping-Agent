#!/usr/bin/env python
"""
run.py — Profile Scraping CLI Entrypoint

OpenClaw calls this as a single command. gpt-5.4 extracts the query
from the Slack message and passes it here. This script handles everything:
search all sources, scrape pages, parse contacts, save to DB, enrich emails.

Usage (run from workspace root):
    python skills/profile_scraper/run.py "python engineers"
    python skills/profile_scraper/run.py "IAM security engineers"
    python skills/profile_scraper/run.py "data scientists" 20
"""

import os
import sys
import re
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load .env file relative to this script directory (2 levels up)
_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
load_dotenv(dotenv_path=_env_path, override=True)

# Ensure workspace root is on path so scraper imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import skills.profile_scraper.scraper as scraper
import skills.profile_scraper.set1_identity as set1_identity
import skills.profile_scraper.set2_clearance as set2_clearance
import skills.profile_scraper.set3_contact as set3_contact
import skills.profile_scraper.profile_enrichment as profile_enrichment
import skills.profile_scraper.excel_manager as excel_manager
from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    ExperienceEntry,
    EducationEntry,
    CertificationEntry,
    ProjectEntry,
    EligibilityDecision,
    CandidateQualificationDecision
)
from skills.profile_scraper.candidate_analyzer import CandidateAnalysisEngine
from skills.profile_scraper.eligibility_engine import EligibilityRulesEngine, JobRequirements
from skills.profile_scraper.excel_repository import ExcelCandidateRepository
from skills.profile_scraper.campaign_orchestrator import CampaignOrchestrator
from skills.profile_scraper.campaign_manager import CampaignManager, create_job_requirements
from skills.profile_scraper.workflow_state import WorkflowStage, WorkflowStateTracker
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from rapidfuzz import fuzz

from typing import Optional

def _find_matching_candidate(profile: dict, candidates_list: list) -> Optional[dict]:
    """Finds if a profile already exists in candidates_list by comparing unique identifiers."""
    p_gh = str(profile.get("github_url") or "").strip().lower()
    p_li = str(profile.get("linkedin_url") or profile.get("profile_url") or "").strip().lower()
    p_email = str(profile.get("email") or "").strip().lower()
    p_name = str(profile.get("full_name") or "").strip().lower()
    
    p_company = ""
    curr_company = profile.get("current_company")
    if isinstance(curr_company, dict):
        p_company = curr_company.get("name") or ""
    elif isinstance(curr_company, str):
        p_company = curr_company
    if not p_company:
        p_company = profile.get("current_company_name") or ""
    p_company = str(p_company).strip().lower()
    
    p_loc = str(profile.get("location") or "").strip().lower()
    
    for c in candidates_list:
        c_gh = str(c.get("github_url") or "").strip().lower()
        c_li = str(c.get("linkedin_url") or c.get("profile_url") or "").strip().lower()
        c_email = str(c.get("email") or "").strip().lower()
        c_name = str(c.get("full_name") or "").strip().lower()
        
        c_company = ""
        c_curr_comp = c.get("current_company")
        if isinstance(c_curr_comp, dict):
            c_company = c_curr_comp.get("name") or ""
        elif isinstance(c_curr_comp, str):
            c_company = c_curr_comp
        if not c_company:
            c_company = c.get("current_company_name") or ""
        c_company = str(c_company).strip().lower()
        
        c_loc = str(c.get("location") or "").strip().lower()
        
        if p_gh and c_gh and p_gh == c_gh:
            return c
        if p_li and c_li and p_li == c_li:
            return c
        if p_email and c_email and p_email == c_email:
            return c
        if p_name and c_name and p_name == c_name:
            if p_company and c_company and p_company == c_company:
                return c
            if p_loc and c_loc and p_loc == c_loc:
                return c
    return None

def _merge_candidate_details(dest: dict, src: dict) -> dict:
    """Merge src candidate dict details into dest dict."""
    for k, v in src.items():
        if v and not dest.get(k):
            dest[k] = v
        elif isinstance(v, list) and isinstance(dest.get(k), list):
            dest[k] = list(set(dest[k] + v))
    return dest

# ---------------------------------------------------------------------------
# Regex extractors — no LLM involved
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r'[\w.+\-]+@[\w\-]+\.[\w.]{2,}')

_JUNK_DOMAINS = {
    'example.com', 'domain.com', 'email.com', 'test.com',
    'yoursite.com', 'sentry.io', 'wixpress.com', 'sampleemail.com',
}

_STATE_ABBREVS = (
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID',
    'IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS',
    'MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK',
    'OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV',
    'WI','WY','DC',
)


def _extract_email(text: str):
    for match in _EMAIL_RE.findall(text):
        domain = match.split('@')[-1].lower()
        if domain not in _JUNK_DOMAINS and 6 < len(match) < 100:
            return match
    return None


def _sanitize_explicit_phone(phone_val: str) -> str:
    """Validate and format an explicitly provided phone number using Abstract Phone API or local fallback."""
    if not phone_val:
        return ""
    from skills.profile_scraper.scraper import _validate_phone_with_abstract
    return _validate_phone_with_abstract(phone_val)


def _extract_name(title: str):
    # Strip platform suffixes: "John Smith — GitHub", "Jane Doe | LinkedIn"
    name = re.split(r'\s*[|—–\-]\s*', title)[0].strip()
    parts = name.split()
    if 2 <= len(parts) <= 4 and len(name) < 60 and re.fullmatch(r"[A-Za-z .'\-]+", name):
        return name
    return None


def _extract_location(text: str):
    """Look for a US location pattern in page text."""
    # Pattern: "City, ST" or "City, State" or "Location: ..."
    state_alts = '|'.join(_STATE_ABBREVS)
    patterns = [
        rf'(?:location|based in|lives?\s+in|from)[:\s]+([A-Z][a-zA-Z\s,]{{3,40}})',
        rf'([A-Z][a-zA-Z\s]+,\s*(?:{state_alts}))',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().rstrip(',')
            if scraper._is_usa_location(loc):
                return loc
    return None


def _source_platform(url: str) -> str:
    netloc = urlparse(url).netloc.replace('www.', '')
    if 'github.com' in netloc:
        return 'github'
    if 'linkedin.com' in netloc:
        return 'linkedin'
    return netloc or 'web'


# ---------------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------------

def _score_profile(profile: dict, query: str) -> float:
    """
    Score a profile based on completeness, relevance, and source trustworthiness.
    Returns a score between 0.0 and 1.0.
    """
    # Weights for different scoring components
    w_completeness = 0.5
    w_relevance = 0.3
    w_source = 0.2

    # 1. Completeness score: how many of the 9 required fields are filled?
    # Note: We need to compute the technology and security clearance here
    # since they might not be set yet in the profile dict from parsing.

    # Extract basic fields from profile
    full_name = profile.get("full_name")
    email = profile.get("email")
    location = profile.get("location")
    years_of_experience = profile.get("years_of_experience") or profile.get("years_of_exp")
    linkedin_url = profile.get("linkedin_url")
    github_url = profile.get("github_url")
    bio_text = profile.get("bio_text", "")
    skills = profile.get("skills", [])
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]

    # Compute technology
    technology = profile.get("technology") or query
    scan_text = f"{full_name or ''}\n{bio_text or ''}"

    # Compute security clearance using the improved extraction
    security_clearance = scraper._extract_security_clearance(scan_text)

    # Build the 9 fields for completeness checking
    fields = [
        full_name,           # Name
        technology,          # Technology
        years_of_experience, # Years of exp
        linkedin_url,        # LinkedIn
        github_url,          # GitHub
        email,               # Email
        location,            # Location
        security_clearance,  # Security Clearances
        ", ".join(skills) if skills else ""  # Skill set
    ]

    # Count non-empty fields (None or empty string counts as empty)
    filled_count = sum(1 for f in fields if f is not None and str(f).strip() != "")
    completeness_score = filled_count / 9.0

    # 2. Relevance score: how well does the profile match the query?
    query_terms = set(query.lower().split())
    if not query_terms:
        relevance_score = 0.5  # Neutral score if no query terms
    else:
        # Check for query terms in bio_text and skills
        text_to_search = (bio_text + " " + " ".join(skills)).lower()
        matched_terms = sum(1 for term in query_terms if term in text_to_search)
        relevance_score = min(matched_terms / len(query_terms), 1.0)  # Cap at 1.0

    # 3. Source trust score: how trustworthy is the source?
    source_platform = (profile.get("source_platform") or "").lower()
    source_scores = {
        'linkedin (bright data)': 1.0,
        'github': 0.9,
        'linkedin (fallback)': 0.8,
        'web': 0.5,
    }
    source_score = source_scores.get(source_platform, 0.5)  # Default to 0.5 if unknown

    # Calculate weighted score
    total_score = (
        w_completeness * completeness_score +
        w_relevance * relevance_score +
        w_source * source_score
    )

    # Ensure score is between 0 and 1
    return max(0.0, min(1.0, total_score))


def _merge_profiles(primary: dict, secondary: dict) -> dict:
    """Merge two profiles. If secondary (LinkedIn) is present, it is authoritative for professional fields."""
    merged = dict(primary)

    is_linkedin_secondary = "linkedin" in (secondary.get("source_platform") or "").lower() or "linkedin.com" in (secondary.get("profile_url") or "").lower() or "linkedin.com" in (secondary.get("url") or "").lower()

    if is_linkedin_secondary:
        # LinkedIn is authoritative for professional fields only when it provides non-empty data:
        if secondary.get("full_name"):
            merged["full_name"] = secondary.get("full_name")
        if secondary.get("experience_history"):
            merged["experience_history"] = secondary.get("experience_history")
            
        sec_exp = secondary.get("years_of_experience")
        if sec_exp and str(sec_exp).strip().lower() not in ("not available", "unknown", "none", "null", ""):
            merged["years_of_experience"] = sec_exp
            
        sec_loc = secondary.get("location")
        if sec_loc and str(sec_loc).strip().lower() not in ("not available", "not_available", "none", "unknown", "null", ""):
            merged["location"] = sec_loc
        if secondary.get("skills"):
            merged["skills"] = secondary.get("skills")
        if secondary.get("headline"):
            merged["headline"] = secondary.get("headline")
        if secondary.get("bio_text") or secondary.get("about"):
            merged["bio_text"] = secondary.get("bio_text") or secondary.get("about")
        elif primary.get("bio_text"):
            merged["bio_text"] = primary.get("bio_text")
            
        if primary.get("search_context") and not merged.get("search_context"):
            merged["search_context"] = primary.get("search_context")
        
        # Merge other fields from secondary
        for field in ["certifications", "recommendations", "education", "languages", "projects", "security_clearance", "visa_status", "current_company", "current_company_name"]:
            if secondary.get(field):
                merged[field] = secondary.get(field)
            
        # Fill in discovery fields from secondary only if blank in primary
        for key in ["email", "mobile_phone"]:
            if not merged.get(key) and secondary.get(key):
                merged[key] = secondary.get(key)
    else:
        # Standard merge if secondary is not LinkedIn
        for key in list(secondary.keys()):
            if not merged.get(key) and secondary.get(key):
                merged[key] = secondary.get(key)
                
    # Merge URLs
    for key in ["linkedin_url", "github_url"]:
        if not merged.get(key):
            sec_url = secondary.get(key) or (secondary.get("profile_url") if key.split("_")[0] in (secondary.get("source_platform") or "").lower() else None)
            if sec_url:
                merged[key] = sec_url

    return merged


def _parse_github(result: dict, query: str) -> dict:
    """
    GitHub results can come pre-structured from github_search_users()
    with email, location, skills, and years_of_experience, or fall back to snippet parsing.
    """
    title   = result.get('title', '')
    snippet = result.get('snippet', '')
    url     = result.get('link', '') or result.get('profile_url', '')

    name  = _extract_name(title)
    profile = None

    # If already fully structured (from github_search_users)
    if result.get('source_platform') == 'github' and (result.get('skills') or result.get('location')):
        profile = {
            'full_name':           result.get('title') or result.get('full_name') or name,
            'email':               result.get('email'),
            'location':            result.get('location'),
            'skills':              result.get('skills', []),
            'profile_url':         url,
            'source_platform':     'github',
            'bio_text':            result.get('bio_text', '') or snippet,
            'years_of_experience': result.get('years_of_experience'),
            'linkedin_url':        result.get('linkedin_url'),
        }

    # If not fully structured (e.g. from organic web search), extract username and fetch details from API!
    if not profile and url:
        try:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split('/') if p]
            username = path_parts[0] if path_parts else None
            # Avoid generic github paths or subpages
            if username and username.lower() not in ('settings', 'explore', 'trending', 'notifications', 'repositories', 'stars', 'topics'):
                print(f"  [Luffy] Fetching GitHub profile details via API: {url}")
                gh_profile = scraper.fetch_github_user_profile(url)
                if gh_profile and 'error' not in gh_profile:
                    profile = gh_profile
                else:
                    err = gh_profile.get('error') if gh_profile else 'Unknown error'
                    print(f"  [Luffy] Skipping GitHub profile due to error: {err}")
                    profile = {'error': f"GitHub API error: {err}"}
                    return profile
        except Exception:
            pass

    if not profile:
        email    = result.get('email')
        location = result.get('location')

        if not email or not location:
            parts = [p.strip() for p in snippet.split('|')]
            for part in parts:
                if not email and '@' in part:
                    email = _extract_email(part)
                if not location and scraper._is_usa_location(part):
                    if len(part) < 60:  # Restrict to short strings to avoid bio matching
                        location = part.strip()

            if not email:
                email = _extract_email(snippet)

        # GitHub queries include location:USA so fallback is safe
        if not location:
            location = 'USA'

        profile = {
            'full_name':           name,
            'email':               email,
            'location':            location,
            'skills':              result.get('skills', []),
            'profile_url':         url,
            'source_platform':     'github',
            'bio_text':            snippet,  # feeds Technology / Security Clearance keyword matching
            'years_of_experience': result.get('years_of_experience'),
            'linkedin_url':        result.get('linkedin_url'),
        }

    # Cross-referencing lookup fallback if still missing linkedin_url
    if profile and not profile.get('linkedin_url'):
        linkedin_url = scraper._search_linkedin_url(profile.get("full_name", ""), profile.get("location", ""), profile.get("username", ""))
        if linkedin_url:
            profile['linkedin_url'] = linkedin_url

    # Enrich with LinkedIn details if we have linkedin_url and Bright Data API key is configured
    if profile and profile.get('linkedin_url') and os.getenv('BRIGHTDATA_API_KEY'):
        linkedin_url = profile['linkedin_url']
        print(f"  [Luffy] Enriching GitHub candidate using found LinkedIn profile: {linkedin_url}")
        li_profile = scraper.brightdata_linkedin_profile(linkedin_url)
        if li_profile and 'error' not in li_profile:
            profile = _merge_profiles(profile, li_profile)
        else:
            err = li_profile.get('error') if li_profile else 'Unknown error'
            print(f"  [Luffy] Skipping LinkedIn profile due to error: {err}")
            li_profile = None   # discard

    if profile:
        profile['github_url'] = url or profile.get('profile_url') or ""

    if profile and not profile.get('mobile_phone'):
        profile['mobile_phone'] = _sanitize_explicit_phone(result.get('phone') or result.get('mobile'))

    return profile


def _parse_linkedin(result: dict, query: str) -> dict:
    """
    LinkedIn results can come from Bright Data search (pre-structured) or from
    organic search results (which need single-profile scraping via Bright Data).
    """
    url = result.get('link', '') or result.get('profile_url', '')
    profile = None

    # If already structured (has skills or specific source platform)
    if result.get('source_platform') == 'LinkedIn (Bright Data)' and (result.get('skills') or result.get('location')):
        profile = {
            'full_name':           result.get('title') or result.get('full_name') or None,
            'email':               result.get('email'),
            'location':            result.get('location'),
            'skills':              result.get('skills', []),
            'profile_url':         url,
            'source_platform':     'LinkedIn (Bright Data)',
            'years_of_experience': result.get('years_of_experience'),
            'bio_text':            result.get('bio_text', ''),
            'github_url':          result.get('github_url'),
        }

    # If not structured, but we have a key, scrape it synchronously!
    if not profile and os.getenv('BRIGHTDATA_API_KEY') and url:
        print(f"  [Luffy] Scraping LinkedIn profile via Bright Data: {url}")
        li_profile = scraper.brightdata_linkedin_profile(url)
        if li_profile and 'error' not in li_profile:
            profile = li_profile
        else:
            err = li_profile.get('error') if li_profile else 'Unknown error'
            print(f"  [Luffy] Bright Data scrape error: {err}. Falling back to basic snippet parsing.")

    if not profile:
        # Fallback to basic extraction from snippet
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        name = _extract_name(title)
        location = _extract_location(snippet)

        profile = {
            'full_name':           name,
            'email':               _extract_email(snippet),
            'location':            location,
            'skills':              [],
            'profile_url':         url,
            'source_platform':     'LinkedIn (Fallback)',
            'years_of_experience': None,
            'bio_text':            snippet,
            'github_url':          None,
        }

    # Fallback to search snippet location if profile location is missing/None
    if profile and (not profile.get('location') or str(profile.get('location')).lower() in ('', 'none')):
        snippet = result.get('snippet', '')
        snippet_loc = _extract_location(snippet)
        if snippet_loc:
            profile['location'] = snippet_loc
            print(f"  [Luffy] Resolved location from search snippet: {snippet_loc}")

    # Cross-referencing lookup fallback if still missing github_url
    if profile and not profile.get('github_url') and profile.get('full_name'):
        github_url = scraper._search_github_url(profile['full_name'], profile.get('location') or '')
        if github_url:
            profile['github_url'] = github_url

    # Enrich with GitHub details if we have github_url
    if profile and profile.get('github_url'):
        github_url = profile['github_url']
        print(f"  [Luffy] Enriching LinkedIn candidate using found GitHub profile: {github_url}")
        gh_profile = scraper.fetch_github_user_profile(github_url)
        if gh_profile and 'error' not in gh_profile:
            profile = _merge_profiles(profile, gh_profile)
        else:
            err = gh_profile.get('error') if gh_profile else 'Unknown error'
            print(f"  [Luffy] Skipping GitHub profile due to error: {err}")
            gh_profile = None   # discard

    if profile and not profile.get('mobile_phone'):
        profile['mobile_phone'] = _sanitize_explicit_phone(result.get('phone') or result.get('mobile'))

    return profile


def _parse_web(result: dict, query: str) -> dict:
    """
    Web results (SerpAPI / Google CSE) need page scraping for contact extraction.
    """
    url     = result.get('link', '')
    title   = result.get('title', '')
    snippet = result.get('snippet', '')

    page_text = scraper.scrape_page(url, fallback_snippet=snippet)
    full_text = f"{title}\n{page_text}"

    return {
        'full_name':       _extract_name(title),
        'email':           _extract_email(full_text),
        'location':        _extract_location(full_text),
        'mobile_phone':    _sanitize_explicit_phone(result.get('phone') or result.get('mobile')),
        'skills':          [],
        'profile_url':     url,
        'source_platform': _source_platform(url),
        'bio_text':        full_text,  # feeds Technology / Security Clearance keyword matching
    }


# ---------------------------------------------------------------------------
# Gemini Relevance Helpers
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Ollama Relevance Helpers
# ---------------------------------------------------------------------------
def _call_ollama(prompt: str, system_prompt: str = None, max_tokens: int = 300, temperature: float = 0.3) -> str:
    """Helper to query local Ollama OpenAI-compatible endpoint with model fallback."""
    import httpx
    
    url = "http://localhost:11434/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    # Try qwen2.5:7b first, fallback to llama3.1:8b, then llama3:latest, then phi:latest
    models_to_try = ["qwen2.5:7b", "llama3.1:8b", "llama3:latest", "phi:latest"]
    
    last_err = None
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        try:
            # 60s timeout to allow local model loading/warmup
            response = httpx.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content'].strip()
            else:
                last_err = f"Ollama {model} returned status {response.status_code}: {response.text[:150]}"
        except httpx.ConnectError:
            raise ConnectionError("Ollama is not running on localhost:11434")
        except Exception as e:
            last_err = f"Ollama {model} request failed: {type(e).__name__}: {str(e)}"
            
    raise RuntimeError(f"All Ollama models failed: {last_err}")


# Query local Ollama with tenacity retry for transient network errors
@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=4),
    retry=retry_if_exception_type((ConnectionError, httpx.HTTPError, httpx.TimeoutException)),
    reraise=True
)
def _call_ollama_with_retry(prompt: str, system_prompt: str = None, max_tokens: int = 300, temperature: float = 0.3) -> str:
    return _call_ollama(prompt, system_prompt, max_tokens, temperature)


def _is_fuzzy_duplicate(profile: dict, processed_profiles: list) -> tuple:
    """Check if profile is a duplicate of any processed profile using fuzzy name/company matching."""
    name = str(profile.get("full_name", "")).strip().lower()
    company = str(profile.get("bio_text", "")).strip().lower()
    
    if not name:
        return False, ""
        
    for p in processed_profiles:
        p_name = str(p.get("full_name", "")).strip().lower()
        p_company = str(p.get("bio_text", "")).strip().lower()
        
        name_ratio = fuzz.token_sort_ratio(name, p_name)
        if name_ratio >= 90:
            # If name matches closely, check bio/headline/company similarity
            bio_ratio = fuzz.partial_token_sort_ratio(company, p_company)
            if bio_ratio >= 85:
                return True, f"Fuzzy name match ({name_ratio:.0f}%) and bio match ({bio_ratio:.0f}%) with {p.get('full_name')}"
                
    return False, ""


def _expand_query_with_openai(query: str) -> list:
    """Expand search query into job titles, skills, and keywords using local Ollama."""
    prompt = (
        f"Expand the technology role '{query}' into a JSON list of related job titles, "
        "keywords, and core skills (e.g. ['Databricks Developer', 'Apache Spark', 'PySpark']). "
        "Provide ONLY the raw JSON array of strings. Do not include markdown formatting or backticks."
    )
    
    try:
        import json
        text = _call_ollama_with_retry(prompt, max_tokens=300, temperature=0.3)
        if "```" in text:
            try:
                parts = text.split("```")
                for p in parts:
                    p_clean = p.strip()
                    if p_clean.startswith("json"):
                        p_clean = p_clean[4:].strip()
                    if p_clean.startswith("[") and p_clean.endswith("]"):
                        text = p_clean
                        break
            except Exception:
                pass
        
        keywords = json.loads(text)
        if isinstance(keywords, list):
            normalized = [str(k).strip().lower() for k in keywords if k]
            if query.lower() not in normalized:
                normalized.append(query.lower())
            print(f"  [Luffy] Ollama expanded '{query}' to: {normalized}")
            return normalized
    except ConnectionError as e:
        print(f"  [Luffy] WARNING: Ollama connection failed, falling back to query keywords: {e}")
    except Exception as e:
        print(f"  [Luffy] WARNING: Ollama query expansion failed: {e}")
        
    import re
    tokens = [t.strip().lower() for t in re.split(r'[\s,/]+', query) if len(t.strip()) > 2]
    return list(dict.fromkeys([query.lower()] + tokens))


def _parse_loose_json(text: str) -> dict:
    """Attempt to parse loose/malformed JSON string from local LLMs."""
    import json
    import re
    
    text = text.strip()
    
    # 1. Quick try
    try:
        return json.loads(text)
    except Exception:
        pass
        
    # 2. Strip trailing commas
    cleaned = re.sub(r',\s*([\]}])', r'\1', text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
        
    # 3. Use regex to extract matched fields
    res = {}
    matched_match = re.search(r'"matched"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
    if matched_match:
        res["matched"] = matched_match.group(1).strip()
        
    conf_match = re.search(r'"confidence_score"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
    if conf_match:
        res["confidence_score"] = conf_match.group(1).strip()
        
    reason_match = re.search(r'"match_reason"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
    if reason_match:
        res["match_reason"] = reason_match.group(1).strip()
        
    if "matched" in res:
        return res
        
    raise ValueError("Failed to extract JSON fields from model output")


def _classify_relevance_with_openai(profile: dict, query: str) -> dict:
    """Classify candidate profile relevance against search query using local Ollama."""
    name = profile.get("full_name", "")
    bio = profile.get("bio_text", "")
    skills = profile.get("skills", [])
    skills_str = ", ".join(skills) if isinstance(skills, list) else str(skills)
    
    prompt = (
        f"Given the technology role '{query}' and the following parsed candidate profile:\n"
        f"Name: {name}\n"
        f"Headline/Bio: {bio}\n"
        f"Skills: {skills_str}\n\n"
        f"Does this person's actual professional role/skillset genuinely match the technology role '{query}'?\n"
        "Analyze carefully. A candidate should only match if their actual profession matches (e.g. searching 'Cybersecurity' should reject lawyers or farmers even if the page text mentions the word).\n\n"
        "Respond ONLY with a JSON object in this format:\n"
        "{\n"
        '  "matched": "yes" | "no" | "uncertain",\n'
        '  "confidence_score": "High" | "Low",\n'
        '  "match_reason": "<one line reasoning explaining the decision>"\n'
        "}\n"
        "Provide ONLY the raw JSON object. Do not include markdown formatting or backticks."
    )
    
    import json
    
    try:
        text = _call_ollama_with_retry(prompt, max_tokens=200, temperature=0.1)
        if "```" in text:
            try:
                parts = text.split("```")
                for p in parts:
                    p_clean = p.strip()
                    if p_clean.startswith("json"):
                        p_clean = p_clean[4:].strip()
                    if p_clean.startswith("{") and p_clean.endswith("}"):
                        text = p_clean
                        break
            except Exception:
                pass
        
        res = _parse_loose_json(text)
        if isinstance(res, dict) and "matched" in res:
            return res
        else:
            raise ValueError(f"Malformed JSON output: {text[:100]}")
    except ConnectionError as e:
        print(f"  [Luffy] ERROR: Ollama unreachable: {e}")
        return {
            "matched": "error",
            "confidence_score": "Classification Error",
            "match_reason": f"Ollama connection failure: {e}"
        }
    except Exception as e:
        print(f"  [Luffy] ERROR: Ollama relevance classification failed: {e}")
        return {
            "matched": "error",
            "confidence_score": "Classification Error",
            "match_reason": f"Ollama failure: {e}"
        }


def _local_prefilter_match(profile: dict, expanded_keywords: list) -> bool:
    """Run a fast keyword pre-filter matching candidate headline, bio, or skills."""
    name       = str(profile.get("full_name", "")).lower()
    bio        = str(profile.get("bio_text", "")).lower()
    skills     = profile.get("skills", [])
    skills_str = ", ".join(skills).lower() if isinstance(skills, list) else str(skills).lower()

    text_to_scan = f"{name} {bio} {skills_str}"

    for keyword in expanded_keywords:
        if keyword in text_to_scan:
            return True

    return False


def _save_set1_excel(candidates: list):
    from loguru import logger
    import openpyxl
    from openpyxl.utils import get_column_letter
    import os
    
    excel_path = os.getenv("EXCEL_OUTPUT_PATH", "skills/output/profiles.xlsx")
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)
    
    logger.info(f"Saving SET 1 candidates to {excel_path}...")
    wb = openpyxl.Workbook()
    # Remove default sheet
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])
        
    ws = wb.create_sheet(title="SET_1")
    COLUMNS = ["Technology", "GitHub URL", "LinkedIn URL", "Full Name", "Years of Experience"]
    ws.append(COLUMNS)
    
    for candidate in candidates:
        ws.append([
            candidate.technology,
            candidate.github_url,
            candidate.linkedin_url,
            candidate.full_name,
            candidate.years_of_experience if candidate.years_of_experience is not None else "Unknown"
        ])
        
    for i in range(1, len(COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 20
        
    try:
        wb.save(excel_path)
        logger.info("Successfully saved SET 1 spreadsheet.")
    except Exception as e:
        logger.error(f"Error saving spreadsheet: {e}")


def _get_absolute_excel_path() -> str:
    excel_path = os.getenv("EXCEL_OUTPUT_PATH", "skills/output/profiles.xlsx")
    if not os.path.isabs(excel_path):
        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        excel_path = os.path.abspath(os.path.join(workspace_root, excel_path))
    return excel_path


INVALID_CANDIDATE_KEYS = {
    "", "none", "null", "not available", "not_available", "n/a",
    "unknown", "undefined", "not_specified", "not specified"
}


def is_valid_url_key(val: str, domain: str) -> bool:
    if not val or not isinstance(val, str):
        return False
    v = val.strip().lower()
    if v in INVALID_CANDIDATE_KEYS:
        return False
    return domain in v and len(v) > len(domain) + 8


def is_valid_email_key(val: str) -> bool:
    if not val or not isinstance(val, str):
        return False
    v = val.strip().lower()
    if v in INVALID_CANDIDATE_KEYS:
        return False
    return "@" in v and "." in v and len(v) > 5


def _load_existing_candidate_keys() -> set:
    keys = set()
    import os
    import openpyxl
    excel_path = _get_absolute_excel_path()
    if os.path.exists(excel_path):
        try:
            wb = openpyxl.load_workbook(excel_path, read_only=True)
            for sheet_name in ["ELIGIBLE_CANDIDATES", "NEEDS_REVIEW", "SET_1", "SET_2", "SET_3"]:
                if sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    rows = list(ws.iter_rows(values_only=True))
                    if len(rows) > 1:
                        headers = [str(h or '').strip().lower() for h in rows[0]]
                        github_idx = -1
                        linkedin_idx = -1
                        email_idx = -1
                        for idx, h in enumerate(headers):
                            if "github" in h:
                                github_idx = idx
                            elif "linkedin" in h or "profile url" in h:
                                linkedin_idx = idx
                            elif "email" in h:
                                email_idx = idx
                        for row in rows[1:]:
                            if not row or not any(row):
                                continue
                            if github_idx != -1 and github_idx < len(row) and row[github_idx]:
                                gh = str(row[github_idx]).strip().lower()
                                if is_valid_url_key(gh, "github.com"):
                                    keys.add(gh)
                            if linkedin_idx != -1 and linkedin_idx < len(row) and row[linkedin_idx]:
                                li = str(row[linkedin_idx]).strip().lower()
                                if is_valid_url_key(li, "linkedin.com"):
                                    keys.add(li)
                            if email_idx != -1 and email_idx < len(row) and row[email_idx]:
                                em = str(row[email_idx]).strip().lower()
                                if is_valid_email_key(em):
                                    keys.add(em)
            wb.close()
        except Exception:
            pass
    return keys


def run(query: str, num: int = 10, mode: str = "linkedin", require_open_to_work: Optional[bool] = None) -> None:
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    from loguru import logger
    # Configure Loguru
    logger.remove()
    logger.add(sys.stderr, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:8s}</level> | {message}", level="INFO")
    
    # Resolve paths relative to workspace root
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    log_dir = os.path.join(workspace_root, "skills/output")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(os.path.join(log_dir, "pipeline.log"), rotation="10 MB", retention="10 days", compression="zip", format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:8s} | {message}")

    # Load configuration parameters
    discovery_enabled = os.getenv("DISCOVERY_SCORE_ENABLED", "true").lower() == "true"
    discovery_hard_rejection = os.getenv("DISCOVERY_HARD_REJECTION", "false").lower() == "true"
    discovery_threshold = int(os.getenv("DISCOVERY_THRESHOLD", "40"))
    discovery_diagnostic_mode = os.getenv("DISCOVERY_DIAGNOSTIC_MODE", "true").lower() == "true"

    logger.info(f"Query   : {query}")
    logger.info(f"Region  : USA only")
    logger.info(f"Mode    : {mode}")
    logger.info(f"Config  : DISCOVERY_SCORE_ENABLED={discovery_enabled}, DISCOVERY_HARD_REJECTION={discovery_hard_rejection}, DISCOVERY_THRESHOLD={discovery_threshold}, DISCOVERY_DIAGNOSTIC_MODE={discovery_diagnostic_mode}")
    
    if not query or not query.strip():
        logger.warning("Rejected: Missing Technology")
        return

    # Load keys of candidates already exported
    existing_keys = _load_existing_candidate_keys()

    # Initialize Campaign Manager and 5-Layer Orchestrator
    otw_active = True if require_open_to_work is None else require_open_to_work
    campaign_mgr = CampaignManager(target_role=query, target_count=num)
    if otw_active:
        campaign_mgr.requirements.require_open_to_work = True
        print("\n" + "=" * 80)
        print("  [Luffy] OPEN TO WORK FILTER: ACTIVE (Strict Mode)")
        print("  Search dorks & qualification strictly require active #OpenToWork candidates.")
        print("  Profiles without Open to Work status will be skipped and rejected.")
        print("=" * 80 + "\n")
    else:
        campaign_mgr.requirements.require_open_to_work = False

    orchestrator = CampaignOrchestrator()

    set1_passed = []
    set2_passed = []
    set3_passed = []
    rejected_candidates = {
        "Set1": [],
        "Set2": [],
        "Set3": []
    }
    processed_urls = set()
    page = 1
    max_pages = int(os.getenv("MAX_SEARCH_PAGES", 30))

    # Track discovered profiles for evidence merging
    discovered_profiles = []

    # Rejection Analytics variables
    analytics = {
        "Total Candidates Discovered": 0,
        "Eligible Count": 0,
        "Needs Review Count": 0,
        "Rejected Count": 0,
        "GitHub Organizations Filtered": 0,
        "Non-USA Location Rejections": 0,
        "Duplicate Candidates Merged": 0,
        "Invalid Profiles Filtered": 0,
        "Incomplete Profiles Filtered": 0,
        "LinkedIn URL Resolution Failures": 0,
        "Bright Data Scraping Failures": 0,
        "API Rate Limits Triggered": 0,
        "Not Relevant / Weak Match Rejections": 0,
        "Set 1 Passed Count": 0,
        "Set 2 Passed Count": 0,
        "Set 3 Passed Count": 0
    }

    def _log_rejection(name, url, stage, reason, raw_payload=None):
        logger.warning(
            f"\nCandidate:\n{name}\n\n"
            f"Profile URL:\n{url}\n\n"
            f"Stage:\n{stage}\n\n"
            f"Reason:\n{reason}\n"
        )
        try:
            cand = NormalizedCandidateProfile(
                full_name=name or "Unknown Candidate",
                linkedin_url=url or f"https://github.com/{name}",
                location=raw_payload.get("location") if isinstance(raw_payload, dict) else "NOT_AVAILABLE",
                raw_payload=raw_payload or {"rejection_reason": reason, "stage": stage}
            )
            from skills.profile_scraper.candidate_models import CandidateAnalysisResult
            analysis = CandidateAnalysisResult(
                total_experience_years=0.0,
                relevant_technology_years=0.0,
                primary_professional_domain="General Technology",
                skill_relevance_score=0
            )
            decision = CandidateQualificationDecision(
                candidate=cand,
                analysis=analysis,
                decision=EligibilityDecision.REJECTED,
                decision_reasons=[reason],
                failed_mandatory_rules=[reason]
            )
            orchestrator.excel_repository.save_candidate_decision(decision)
        except Exception as ex:
            logger.debug(f"[ExcelRepository] Note recording early rejection: {ex}")

    while not campaign_mgr.is_goal_reached() and page <= max_pages:
        needed_count = num - campaign_mgr.eligible_count
        batch_size = max(needed_count * 2, 10)
        
        print(f"\n--- [PAGE {page}] Searching for candidates (target: {num} ELIGIBLE, gathered: {campaign_mgr.eligible_count}) ---")
        results = scraper.search_all_sources(
            query,
            num=batch_size,
            page=page,
            mode=mode,
            require_open_to_work=campaign_mgr.requirements.require_open_to_work
        )
        
        if not results:
            print("  [Luffy] No more search results returned from sources. Search avenues exhausted.")
            break
            
        new_results_found = False
        for result in results:
            url = result.get('link') or result.get('profile_url') or ''
            if not url:
                continue
                
            is_direct_linkedin = "linkedin.com" in url.lower()
            
            # Check candidate duplication using our comparison helper before any API calls
            existing_match = _find_matching_candidate(result, discovered_profiles)
            if existing_match:
                print(f"  [Luffy] Duplicate candidate detected: {result.get('title') or url}. Merging details.")
                _merge_candidate_details(existing_match, result)
                analytics["Duplicate Candidates Merged"] += 1
                
                # If we already have both github and linkedin resolved, skip fetching/scraping again
                if existing_match.get("linkedin_url") and existing_match.get("github_url"):
                    continue
                # Otherwise, continue processing using the merged profile
                profile = existing_match
            else:
                profile = result
                discovered_profiles.append(profile)
                analytics["Total Candidates Discovered"] += 1
            
            if is_direct_linkedin:
                # Check for international subdomains to save scrape API credits
                parsed_url = urlparse(url)
                hostname = parsed_url.hostname or ""
                parts = hostname.split(".")
                if len(parts) >= 3 and parts[0] not in ("www", "linkedin"):
                    logger.info(f"Skipped Non-US LinkedIn Subdomain: {url}")
                    analytics["Non-USA Location Rejections"] += 1
                    continue
                
                # Direct LinkedIn URL path
                linkedin_url = url
                github_url = profile.get("github_url") or "not available"
                username = url.split("/in/")[-1].strip("/").split("/")[0]
                
                # Early recruiter identity check from search result context
                is_recruitment, neg_reason = set1_identity.has_explicit_negative_identity(result)
                if is_recruitment:
                    logger.info(f"Skipped direct LinkedIn candidate '{username}' due to explicit recruiter/sales identity in search result: {neg_reason}")
                    _log_rejection(username, linkedin_url, 'LinkedIn Validation', f'Explicit negative role identity detected in search context: {neg_reason}')
                    analytics["Not Relevant / Weak Match Rejections"] += 1
                    continue

                # Check Open to Work indicators in search snippet
                if campaign_mgr.requirements.require_open_to_work:
                    otw_match, otw_reason = set1_identity.is_search_result_open_to_work(result)
                    if otw_match:
                        logger.info(f"Open to Work indicator in search snippet for '{username}': {otw_reason}")
                
                if linkedin_url.lower() in processed_urls:
                    continue
                processed_urls.add(linkedin_url.lower())
                new_results_found = True
                
                raw_title = result.get("title") or ""
                parsed_name = ""
                if raw_title:
                    clean_title = raw_title.replace(" | LinkedIn", "").replace(" - LinkedIn", "")
                    if " - " in clean_title:
                        parsed_name = clean_title.split(" - ")[0].strip()
                    elif " | " in clean_title:
                        parsed_name = clean_title.split(" | ")[0].strip()
                    elif ":" in clean_title:
                        parsed_name = clean_title.split(":")[0].strip()

                full_name_cand = parsed_name or username.replace("-", " ").title()

                gh_profile = {
                    "username": username,
                    "full_name": full_name_cand,
                    "location": "",
                    "linkedin_url": linkedin_url,
                    "github_url": github_url,
                    "email": profile.get("email"),
                    "account_type": "User",
                    "search_context": result,
                    "bio_text": result.get("snippet", "")
                }
            else:
                # Original GitHub URL path
                parsed = urlparse(url)
                path_parts = [p for p in parsed.path.split('/') if p]
                username = path_parts[0] if path_parts else None
                if not username or username.lower() in ('settings', 'explore', 'trending', 'notifications', 'repositories', 'stars', 'topics', 'orgs'):
                    continue
                github_url = f"https://github.com/{username}".lower()
                
                if github_url in processed_urls:
                    continue
                processed_urls.add(github_url)
                new_results_found = True
                
                # Step 3: GitHub API (Fetch basic user profile details)
                print(f"  [Luffy] Fetching GitHub profile details via API: {github_url}")
                gh_profile = scraper.fetch_github_user_profile(github_url)
                if not gh_profile:
                    _log_rejection(username, github_url, 'GitHub Fetch', 'Empty profile data')
                    analytics["Incomplete Profiles Filtered"] += 1
                    continue
                elif gh_profile.get('account_type') == 'Organization' or gh_profile.get('error') == 'GitHub account type is Organization':
                    logger.info(f"Skipped GitHub Organization: {github_url}")
                    _log_rejection(gh_profile.get('full_name') or username, github_url, 'GitHub Validation', 'GitHub account type is Organization')
                    analytics["GitHub Organizations Filtered"] += 1
                    continue
                elif 'error' in gh_profile:
                    err = gh_profile.get('error')
                    _log_rejection(username, github_url, 'GitHub Fetch', f'GitHub API error: {err}')
                    analytics["Incomplete Profiles Filtered"] += 1
                    continue
                    
                # Step 4: Organization Check immediately after API retrieval
                account_type = gh_profile.get('account_type') or 'User'
                if account_type == 'Organization':
                    logger.info(f"Skipped GitHub Organization: {github_url}")
                    _log_rejection(gh_profile.get('full_name') or username, github_url, 'GitHub Validation', 'GitHub account type is Organization')
                    analytics["GitHub Organizations Filtered"] += 1
                    continue
                    
                # Step 5: Recruiter/Sales Identity Check
                is_recruitment, neg_reason = set1_identity.has_explicit_negative_identity(gh_profile)
                if is_recruitment:
                    logger.info(f"Skipped candidate '{gh_profile.get('full_name') or username}' due to explicit recruiter/sales identity: {neg_reason}")
                    _log_rejection(gh_profile.get('full_name') or username, github_url, 'GitHub Validation', f'Explicit negative role identity detected: {neg_reason}')
                    analytics["Not Relevant / Weak Match Rejections"] += 1
                    continue

                # Early Open to Work check on search context
                if campaign_mgr.requirements.require_open_to_work:
                    otw_match, otw_reason = set1_identity.is_search_result_open_to_work(result)
                    if not otw_match:
                        # Check bio / profile text
                        bio_text = str(gh_profile.get("bio") or gh_profile.get("bio_text") or "")
                        otw_bio, _ = set1_identity.is_search_result_open_to_work({"snippet": bio_text})
                        if not otw_bio:
                            logger.info(f"Skipped GitHub candidate '{username}': search context does not indicate active Open to Work status")
                            _log_rejection(gh_profile.get('full_name') or username, github_url, 'Open to Work Pre-Filter', 'GitHub bio/snippet does not indicate active Open to Work status', raw_payload=gh_profile)
                            analytics["Rejected Count"] += 1
                            continue

                # Step 6: GitHub pre-scrape screening using Discovery Score (saves api key cost)
                discovery_score = set1_identity.calculate_discovery_score(gh_profile, query, search_context=result)
                gh_profile['discovery_score'] = discovery_score
                
                # Prioritize:
                # 80-100: HIGH PRIORITY ENRICHMENT
                # 50-79: NORMAL ENRICHMENT
                # 20-49: LOW PRIORITY ENRICHMENT
                # 0-19: INSUFFICIENT GITHUB EVIDENCE
                priority = "INSUFFICIENT GITHUB EVIDENCE"
                if discovery_score >= 80: priority = "HIGH PRIORITY ENRICHMENT"
                elif discovery_score >= 50: priority = "NORMAL ENRICHMENT"
                elif discovery_score >= 20: priority = "LOW PRIORITY ENRICHMENT"
                gh_profile['discovery_priority'] = priority
                
                # Print Breakdown Details
                breakdown = gh_profile.get('discovery_score_breakdown', {})
                print(f"  [Luffy] Discovery Score: {discovery_score}/100 ({priority}) for '{gh_profile.get('full_name') or username}'")
                print(f"    Breakdown:")
                for k, v in breakdown.items():
                    if k == "Unknown Fields":
                        print(f"      - Unknown Fields: {', '.join(v) if v else 'None'}")
                    else:
                        print(f"      - {k}: {v}")
                
                # Enforce config rules:
                if discovery_enabled and discovery_hard_rejection:
                    # Reject only if score is below threshold AND search context has no matches
                    sc_matches = breakdown.get("Search Context Match", 0)
                    if discovery_score < discovery_threshold and sc_matches == 0:
                        logger.info(f"Skipped candidate '{gh_profile.get('full_name')}' (Discovery Score: {discovery_score}) due to low score and no search context matches in hard-rejection mode.")
                        _log_rejection(gh_profile.get('full_name') or username, github_url, 'GitHub Discovery', f'Discovery Score {discovery_score} is below threshold {discovery_threshold} with no search-context matches')
                        analytics["Not Relevant / Weak Match Rejections"] += 1
                        continue
                    
                # Early USA Location Check (based on GitHub location to avoid scraping non-USA candidates)
                gh_loc = gh_profile.get('location') or ''
                if gh_loc:
                    is_us, status, reasons = set1_identity.validate_us_location({'location': gh_loc})
                    gh_profile['location_status'] = status
                    if not is_us:
                        _log_rejection(gh_profile.get('full_name') or username, github_url, 'Location Validation', f'GitHub profile location ({gh_loc}) is outside the USA (Status: {status})')
                        analytics["Non-USA Location Rejections"] += 1
                        continue

            # Step 7: LinkedIn Search
            linkedin_url = gh_profile.get('linkedin_url') or profile.get('linkedin_url') or scraper._search_linkedin_url(gh_profile.get('full_name', ''), gh_profile.get('location', ''), gh_profile.get('username', ''))
            if not linkedin_url or "linkedin.com" not in linkedin_url.lower():
                _log_rejection(gh_profile.get('full_name') or username, github_url, 'LinkedIn Validation', 'Could not resolve LinkedIn URL link')
                analytics["LinkedIn URL Resolution Failures"] += 1
                continue
                
            gh_profile['linkedin_url'] = linkedin_url
            gh_profile['github_url'] = github_url
            
            # Step 8: Bright Data Scrape (Enrichment)
            print(f"  [Luffy] Enriching candidate using LinkedIn profile: {linkedin_url}")
            li_profile = scraper.brightdata_linkedin_profile(
                linkedin_url,
                require_open_to_work=campaign_mgr.requirements.require_open_to_work
            )
            
            # Check for proactive session termination from session monitor
            if li_profile and li_profile.get("session_terminated"):
                err_msg = li_profile.get('error')
                term_reason = li_profile.get('reason')
                print(f"  [Luffy] CRITICAL: Session monitor halted authorized session ({term_reason}: {err_msg})")
                print("  [Luffy] Saving current candidate progress to Excel before clean exit...")
                excel_path = _get_absolute_excel_path()
                excel_manager.batch_save_profiles(set1_passed, set2_passed, set3_passed, rejected_candidates, excel_path)
                print(f"  [Luffy] Existing progress saved cleanly to {excel_path}. Halting pipeline.")
                break

            enrichment_status = "SUCCESS"
            if not li_profile or 'error' in li_profile:
                err = li_profile.get('error') if li_profile else 'Unknown error'
                print(f"  [Luffy] WARNING: LinkedIn scraping failed ({err}). Proceeding with partial profile details.")
                enrichment_status = "API_RATE_LIMITED" if "429" in str(err) or "rate limit" in str(err).lower() else "ENRICHMENT_FAILED"
                analytics["Bright Data Scraping Failures"] += 1
                if enrichment_status == "API_RATE_LIMITED":
                    analytics["API Rate Limits Triggered"] += 1
                    
                li_profile = {
                    'enrichment_status': enrichment_status,
                    'relevance_score': 0,
                    'relevance_band': 'Unknown'
                }
                
            # Step 9: Experience Resolution (Merge profiles)
            merged_profile = _merge_profiles(gh_profile, li_profile)
            merged_profile['enrichment_status'] = enrichment_status
            
            # Explicit location check on merged data
            is_us, status, reasons = set1_identity.validate_us_location(merged_profile)
            if not is_us and "No US indicators found" in reasons:
                # Fallback: check search result snippet or title
                search_ctx = merged_profile.get("search_context") or {}
                ctx_text = f"{search_ctx.get('title', '')} {search_ctx.get('snippet', '')}"
                ctx_is_us, ctx_status, ctx_reasons = set1_identity.validate_us_location({"location": ctx_text, "bio_text": ctx_text})
                if ctx_is_us:
                    is_us = True
                    status = ctx_status
                    if not merged_profile.get("location") or merged_profile.get("location") == "NOT_AVAILABLE":
                        merged_profile["location"] = "USA"
            
            merged_profile['location_status'] = status
            if not is_us:
                _log_rejection(merged_profile.get('full_name') or username, linkedin_url or github_url, 'Location Validation', f'Merged profile location ({merged_profile.get("location")}) is outside the USA (Status: {status})')
                analytics["Non-USA Location Rejections"] += 1
                continue
            
            # Final duplicate check against exported profiles
            github_url_clean = str(merged_profile.get("github_url") or "").strip().lower()
            linkedin_url_clean = str(merged_profile.get("linkedin_url") or merged_profile.get("profile_url") or "").strip().lower()
            email_clean = str(merged_profile.get("email") or "").strip().lower()
            
            is_duplicate = False
            if is_valid_url_key(github_url_clean, "github.com") and github_url_clean in existing_keys:
                is_duplicate = True
            if is_valid_url_key(linkedin_url_clean, "linkedin.com") and linkedin_url_clean in existing_keys:
                is_duplicate = True
            if is_valid_email_key(email_clean) and email_clean in existing_keys:
                is_duplicate = True
            
            for passed in set3_passed:
                p_github = str(passed.github_url or "").strip().lower()
                p_linkedin = str(passed.linkedin_url or "").strip().lower()
                p_email = str(passed.email or "").strip().lower()
                if is_valid_url_key(github_url_clean, "github.com") and is_valid_url_key(p_github, "github.com") and github_url_clean == p_github:
                    is_duplicate = True
                if is_valid_url_key(linkedin_url_clean, "linkedin.com") and is_valid_url_key(p_linkedin, "linkedin.com") and linkedin_url_clean == p_linkedin:
                    is_duplicate = True
                if is_valid_email_key(email_clean) and is_valid_email_key(p_email) and email_clean == p_email:
                    is_duplicate = True
                
            if is_duplicate:
                _log_rejection(merged_profile.get('full_name') or username, linkedin_url or github_url, 'Duplicate Check', 'Duplicate candidate already processed or exported')
                analytics["Duplicate Candidates Merged"] += 1
                continue
                
            # Step 9.5: Extract or construct full NormalizedCandidateProfile
            candidate_obj = None
            if isinstance(li_profile, dict):
                candidate_obj = li_profile.get("normalized_candidate_object")

            if candidate_obj is None:
                exp_entries = []
                for rexp in merged_profile.get("experience_history") or []:
                    if isinstance(rexp, ExperienceEntry):
                        exp_entries.append(rexp)
                    elif isinstance(rexp, dict):
                        exp_entries.append(ExperienceEntry(
                            title=rexp.get("title") or "Role",
                            company=rexp.get("company") or rexp.get("company_name") or "Company",
                            start_date=rexp.get("start_date") or "",
                            end_date=rexp.get("end_date") or "Present",
                            duration_text=rexp.get("duration_text") or "",
                            description=rexp.get("description") or ""
                        ))

                candidate_obj = NormalizedCandidateProfile(
                    full_name=merged_profile.get("full_name") or username,
                    linkedin_url=linkedin_url or merged_profile.get("profile_url") or f"https://github.com/{username}",
                    headline=merged_profile.get("headline") or merged_profile.get("bio") or "NOT_AVAILABLE",
                    location=merged_profile.get("location") or "NOT_AVAILABLE",
                    current_title=merged_profile.get("current_title") or merged_profile.get("position") or "NOT_AVAILABLE",
                    current_company=merged_profile.get("current_company") or merged_profile.get("company") or "NOT_AVAILABLE",
                    about=merged_profile.get("about") or merged_profile.get("bio") or "NOT_AVAILABLE",
                    experience_history=exp_entries,
                    skills=merged_profile.get("skills") or [],
                    email=merged_profile.get("email") or "NOT_AVAILABLE",
                    phone=merged_profile.get("phone") or "NOT_AVAILABLE",
                    websites=merged_profile.get("websites") or [],
                    github_url=github_url or "NOT_AVAILABLE",
                    raw_payload=merged_profile
                )
            else:
                # Ensure merged contact information is preserved if missing from LinkedIn
                if not candidate_obj.github_url or candidate_obj.github_url == "NOT_AVAILABLE":
                    candidate_obj.github_url = github_url or "NOT_AVAILABLE"
                if (not candidate_obj.email or candidate_obj.email == "NOT_AVAILABLE") and merged_profile.get("email"):
                    candidate_obj.email = merged_profile.get("email")
                if (not candidate_obj.phone or candidate_obj.phone == "NOT_AVAILABLE") and merged_profile.get("phone"):
                    candidate_obj.phone = merged_profile.get("phone")

            # Step 10: Execute Decoupled 5-Layer Pipeline: Analysis -> Eligibility -> Immediate Excel Persistence
            decision: CandidateQualificationDecision = orchestrator.process_candidate_profile(
                candidate=candidate_obj,
                requirements=campaign_mgr.requirements
            )
            campaign_mgr.record_candidate(decision)

            # Record decision metrics and track candidate object
            if decision.decision == EligibilityDecision.ELIGIBLE:
                analytics["Eligible Count"] += 1
                analytics["Set 1 Passed Count"] += 1
                analytics["Set 2 Passed Count"] += 1
                analytics["Set 3 Passed Count"] += 1
                set1_passed.append(candidate_obj)
                set2_passed.append(candidate_obj)
                set3_passed.append(candidate_obj)
            elif decision.decision == EligibilityDecision.NEEDS_REVIEW:
                analytics["Needs Review Count"] += 1
                analytics["Set 1 Passed Count"] += 1
                analytics["Set 2 Passed Count"] += 1
                set1_passed.append(candidate_obj)
                set2_passed.append(candidate_obj)
            elif decision.decision == EligibilityDecision.REJECTED:
                analytics["Rejected Count"] += 1
                rejected_candidates["Set1"].append(merged_profile)

            # Step 11: Apply Pacing & Cooldown
            campaign_mgr.apply_inter_profile_pacing()
            campaign_mgr.check_batch_cooldown()

            if campaign_mgr.is_goal_reached():
                print(f"  [Luffy] Campaign target reached: {campaign_mgr.eligible_count}/{num} ELIGIBLE candidates qualified.")
                break
                
        if not new_results_found:
            print("  [Luffy] No new unique candidates found on this page. Search avenues exhausted.")
            break
            
        page += 1

    # Synchronize rate limit analytics
    rate_limits_total = (
        scraper.PROVIDER_REQUEST_COUNTS.get("Google CSE Rate Limits", 0) +
        scraper.PROVIDER_REQUEST_COUNTS.get("Serper.dev Rate Limits", 0) +
        scraper.PROVIDER_REQUEST_COUNTS.get("SerpAPI Rate Limits", 0) +
        scraper.PROVIDER_REQUEST_COUNTS.get("Bright Data LinkedIn API Rate Limits", 0)
    )
    analytics["API Rate Limits Triggered"] = rate_limits_total

    # Print Campaign Performance Report Summary
    summary = campaign_mgr.get_summary()
    print("\n" + "="*80)
    print("                      CAMPAIGN PERFORMANCE REPORT SUMMARY")
    print("="*80)
    print(f"  Target Role                             : {summary['target_role']}")
    print(f"  Target Count Required                   : {summary['target_count']}")
    print(f"  Total Candidates Discovered             : {summary['total_processed']}")
    print(f"  ELIGIBLE Candidates Qualified           : {summary['eligible_count']}")
    print(f"  NEEDS_REVIEW Candidates Identified      : {summary['needs_review_count']}")
    print(f"  REJECTED Candidates Filtered            : {summary['rejected_count']}")
    print(f"  Total Elapsed Campaign Time             : {summary['elapsed_seconds']}s")
    print(f"  Campaign Goal Achieved                  : {'YES' if summary['goal_reached'] else 'NO'}")
    print("="*80)

    # Print Rejection Analytics Report Summary
    print("                      DETAILED SOURCING METRICS")
    print("="*80)
    for category, count in analytics.items():
        print(f"  {category:<40}: {count}")
    print("="*80)
    
    # Print search API request summary
    print("                      SEARCH PROVIDER REQUEST METRICS")
    print("="*80)
    for provider, count in scraper.PROVIDER_REQUEST_COUNTS.items():
        print(f"  {provider:<40}: {count} requests")
    print("="*80 + "\n")

    excel_path = _get_absolute_excel_path()
    print(f"  [Luffy] Verified 4-Sheet Lifecycle: ALL_RAW_PROFILES, ELIGIBLE_CANDIDATES, NEEDS_REVIEW, REJECTED_CANDIDATES\n")
    # Legacy backward-compatibility batch save
    excel_manager.batch_save_profiles(set1_passed, set2_passed, set3_passed, rejected_candidates, excel_path)


if __name__ == '__main__':
    import argparse
    from skills.profile_scraper.query_builder import prompt_interactive_query, repair_cli_argv

    parser = argparse.ArgumentParser(description="LinkedIn & GitHub Sourcing Agent")
    parser.add_argument("query", nargs="?", default=None, help="Job role query or Boolean search string (e.g. 'IAM Engineer' or '(\"SailPoint\" OR \"CyberArk\")')")
    parser.add_argument("num", type=int, nargs="?", default=None, help="Target number of profiles to qualify (default: 10)")
    parser.add_argument("--mode", choices=["linkedin", "github"], default=None, help="Sourcing mode: linkedin (direct) or github")
    parser.add_argument("--diagnostic", action="store_true", help="Run in single-profile live diagnostic mode")
    parser.add_argument("--profile-url", type=str, default="", help="Direct profile URL for diagnostic mode")
    parser.add_argument("--open-to-work", action="store_true", default=True, help="Strictly require candidates to be actively Open to Work (default: True)")
    parser.add_argument("--include-all-profiles", action="store_true", default=False, help="Disable strict Open to Work requirement (search all profiles)")

    repaired_args = repair_cli_argv(sys.argv[1:])
    args = parser.parse_args(repaired_args)

    # If query is omitted and not in diagnostic direct-URL mode, prompt interactively
    if not args.query and not args.profile_url:
        query, num, mode = prompt_interactive_query()
    else:
        query = args.query or "Network Engineer"
        num = args.num if args.num is not None else 10
        mode = args.mode or "linkedin"

    otw_flag = False if args.include_all_profiles else True

    if args.diagnostic or args.profile_url:
        from skills.profile_scraper.diagnostic_runner import run_diagnostic_scrape
        diag_url = args.profile_url
        if not diag_url:
            print(f"  [Luffy] Resolving first candidate profile URL for diagnostic mode: query='{query}' (require_open_to_work={otw_flag})...")
            raw_res = scraper.search_all_sources(query, num=1, mode="linkedin", require_open_to_work=otw_flag)
            if raw_res:
                diag_url = raw_res[0].get("link") or raw_res[0].get("profile_url") or ""
        if diag_url:
            run_diagnostic_scrape(diag_url, query=query)
        else:
            print(f"  [Luffy] Could not resolve candidate URL for diagnostic test.")
    else:
        run(query, num, mode, require_open_to_work=otw_flag)