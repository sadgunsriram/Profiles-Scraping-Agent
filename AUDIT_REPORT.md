# Profile Scraping Agent - Audit Report

## Executive Summary
The talent sourcing scraper has fundamental architectural flaws that cause the reported issues:
1. **Irrelevant profiles** due to superficial keyword matching without role/domain validation
2. **Fabricated data** from heuristic estimations presented as factual data
3. **Missing mobile number field** in the data model
4. **No validation** of contact information before output

## Pipeline Overview
```
Input Handling → Source Search → Result Parsing → Scoring → Deduplication → Excel Output
                ↓              ↓             ↓              ↓              ↓
auto_scrape.py  scraper.py   run.py (_parse_*)  run.py (_score_profile)  scraper.py (save_profile)
                │              │               │              ↓
         (SerpAPI,          (GitHub,         (email/phone   segregate.py
         Google CSE,        BrightData       extraction)    (technology
         GitHub)            LinkedIn)                            mapping)
```

## Detailed Findings

### 1. Irrelevant Profile Problem (False Positives)
**Root Cause**: Superficial keyword matching without semantic role validation

**Location & Evidence**:
- `run.py` lines 149-157: Relevance scoring based solely on term frequency in bio/skills
- `scraper.py` lines 2041-2060: `_extract_technology()` uses hardcoded keyword mapping
- Example: Query "Cybersecurity" matches any text containing "security" (security guards, food security, financial security)

**Specific Issues**:
- No validation that the person actually WORKS in the technology domain
- No role/title analysis - a lawyer mentioning "cybersecurity compliance" gets scored as relevant
- No distinction between casual mentions vs professional expertise

### 2. Fabricated/Dummy Data Problem
**Root Cause**: Heuristic estimations presented as factual data without user disclosure

**Location & Evidence**:
- `scraper.py` lines 1013-1015: Years of experience estimated from GitHub activity
  ```python
  years_exp = min(max(1, (followers + following + public_repos) // 50), 30)
  ```
  - Presented as factual "years_of_experience with no indication it's an estimate
  
- `scraper.py` lines 1017-1034: Skills extracted from repo languages
  - Reasonable for GitHub, but presented as comprehensive skill set
  
- `scraper.py` lines 1448-1493: `brightdata_linkedin_profile()` returns placeholder error
  ```python
  return {
      'error': 'Bright Data LinkedIn scraping implementation pending - this is a placeholder for the function signature',
      'url': url
  }
  ```
  - Code continues to process this "profile" despite the error indicator
  
- `run.py` lines 285-286: Cross-referencing lookup for LinkedIn/GitHub URLs without validation
  ```python
  linkedin_url = scraper._search_linkedin_url(profile.get("full_name", ""), profile.get("location", ""))
  ```
  - Returns any LinkedIn URL matching name, not necessarily the correct person

### 3. Missing Mobile Number Field
**Location & Evidence**:
- `scraper.py` lines 1584-1587: COLUMNS definition missing "Mobile No"
  ```python
  COLUMNS = [
      "Name", "Technology", "Years of exp", "LinkedIn", "GitHub",
      "Email", "Location", "Security Clearances", "Skill set",
  ]
  ```
  
- `run.py` lines 54-56: `_extract_phone()` function exists but is unused
  ```python
  def _extract_phone(text: str):
      matches = _PHONE_RE.findall(text)
      return matches[0].strip() if matches else None
  ```
  
- No field for mobile number in profile parsing or saving functions

### 4. Missing Validation Layer
**Location & Evidence**:
- `run.py` lines 46-51: Basic email extraction with junk domain filtering only
  ```python
  def _extract_email(text: str):
      for match in _EMAIL_RE.findall(text):
          domain = match.split('@')[-1].lower()
          if domain not in _JUNK_DOMAINS and 6 < len(match) < 100:
              return match
      return None
  ```
  - No RFC 5322 compliance check
  - No MX record validation
  
- `run.py` lines 54-56: Phone extraction with no validation
  ```python
  def _extract_phone(text: str):
      matches = _PHONE_RE.findall(text)
      return matches[0].strip() if matches else None
  ```
  - No format validation (length, country codes, etc.)
  - No line-type detection (mobile vs landline vs VoIP)
  
- `scraper.py` save_profile function: No validation before Excel write

### 5. Data Source Limitations Assessment

| Source | Realistically Providable Fields | Legally/ToS Compliant? | Mobile Number Availability |
|--------|--------------------------------|------------------------|----------------------------|
| **SerpAPI/Google CSE** (web search) | Name, title, snippet, URL, possibly email/phone if publicly posted on scraped pages | Generally OK for public web pages | Very low - only if user published mobile on indexed pages |
| **GitHub API** | Username, name, public email, location, bio, repos, followers, created_at | Yes (official API) | Never - GitHub ToS prohibits sharing personal contact info |
| **Bright Data LinkedIn** | Name, headline, experience, education, skills (if properly implemented) | **Questionable** - LinkedIn ToS prohibits scraping without explicit permission | Very low - Even if available, scraping LinkedIn contact info violates ToS |
| **Cross-reference lookups** (_search_linkedin_url, _search_github_url) | Potential profile URLs | Depends on source - scraping search engines may violate ToS | Not applicable |

**Conclusion on Mobile Numbers**: 
Mobile number extraction at meaningful scale is **not feasible** from these sources:
1. GitHub: Never provides phone numbers (ToS restriction)
2. LinkedIn: Technically possible but violates ToS to scrape contact info
3. Web search: Extremely low yield - only if user published mobile on indexed pages
4. Public records: Would require external APIs not currently integrated

### 6. Additional Critical Issues

**Duplicate Detection Flaws**:
- `scraper.py` lines 1632-1650: Only checks exact matches on email/LinkedIn/GitHub
- No fuzzy matching for names (e.g., "Bob Smith" vs "Robert Smith")
- No normalization of URLs (tracking parameters, http/https)

**Technology Mapping Issues**:
- `segregate.py` lines 17-27: Hardcoded TECH_TO_SHEET_MAP
- Does not generalize to arbitrary user-input technologies
- Requires manual update for new technologies

**Security Clearance Extraction**:
- `scraper.py` lines 2061-2069: Simple keyword matching for clearance terms
- No context awareness (e.g., "no security clearance required" would still match)

## Recommended Fixes by Phase

### Phase 1: Immediate Fixes (No Rewrites)
1. **Add mobile number column** to COLUMNS in scraper.py
2. **Integrate phone extraction** into profile parsing pipelines
3. **Add basic email/phone validation** using standard libraries
4. **Mark estimated fields** clearly in output (e.g., "Years of exp (est)")

### Phase 2: Relevance Fixes (Requires Algorithm Changes)
1. **Replace keyword matching** with role-title validation
2. **Implement LLM-based relevancy scoring** as requested
3. **Add confidence scoring** and manual review flags

### Phase 3: Mobile Number Realism
1. **Document extremely low expected yield** for mobile numbers
2. **Only populate from high-confidence sources** (explicitly listed contact info on personal domains)
3. **Never generate or guess** phone numbers
4. **Add external enrichment hook** for paid services (NumVerify, etc.)

### Phase 4: Validation Layer
1. **Email**: RFC validation + optional API verification (Hunter/ZeroBounce)
2. **Phone**: Google's libphonenumber for format/carrier/type validation
3. **Add validation status columns** to output
4. **Make API keys configurable** via environment variables

## Files Requiring Modification
1. `skills/profile_scraper/run.py` - scoring, parsing, validation
2. `skills/profile_scraper/scraper.py` - source searching, saving, column definitions
3. `skills/profile_scraper/segregate.py` - technology mapping (for generalization)
4. `auto_scrape.py`, `batch_databricks.py`, etc. - input handling (minimal changes needed)

## Critical Path Forward
Do NOT proceed with Phase 2-5 until Phase 1 audit findings are acknowledged and confirmed. The current foundation produces unreliable data that any "enhancements" would merely build upon a faulty base.

Next step: Review this audit report and confirm which Phase 1 improvements to implement first.