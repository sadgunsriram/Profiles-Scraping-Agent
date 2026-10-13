# preflight_check
Input:  - None (runs automatically at start of scraping run)
Output: 
        - If all required keys present: Returns "READY" and allows execution to continue
        - If any required key missing: Returns error message and stops execution
Behavior:
- Checks for presence of REQUIRED environment variables:
    - SERPAPI_API_KEY
    - CSE_ID  
    - CSE_KEY
- If ANY required key is missing:
    - Returns clear error message specifying which key(s) are missing
    - Example: "Missing SERPAPI_API_KEY — cannot run search"
    - Prevents execution of search_all_sources and downstream tools
- Also checks for OPTIONAL keys and logs warnings if missing:
    - GITHUB_TOKEN (enables authenticated GitHub API, higher rate limits)
    - HUNTER_API_KEY (enables email enrichment via Hunter.io)
    - BRIGHTDATA_API_KEY (enables LinkedIn enrichment - CURRENTLY NON-FUNCTIONAL STUB)
- This check runs automatically at the very beginning of any scraping workflow
- Does not consume any API credits or make external calls
- File location: skills/profile_scraper/scraper.py (function: preflight_check)

# search_all_sources
Input:  - `query` (string) – e.g. "python engineers"
        - `num` (int, default 10) – max total results to return
Output: List of dicts, each with:
        - `title`, `link`, `snippet`, `source_platform` (SerpAPI/Google CSE/GitHub/Bright Data)
        - For GitHub results: may include `email`, `location`, `skills`, `years_of_experience`
Requires: SERPAPI_API_KEY, CSE_ID, CSE_KEY (for web); GITHUB_TOKEN optional; BRIGHTDATA_API_KEY optional (⚠️ non-functional / stub)
Behavior:
- Automatically runs preflight_check() to validate required API keys
- Searches SerpAPI (if key configured)
- Searches Google CSE (if keys configured)
- Searches GitHub user API (always works, unauthenticated)
- Optionally searches Bright Data LinkedIn (if key configured - currently non-functional)
- Combines and deduplicates results from all sources
- Returns empty list if preflight check fails
- File location: skills/profile_scraper/scraper.py (function: search_all_sources)

# _parse_github / _parse_linkedin / _parse_web
Input:  - `result` dict from search_all_sources
        - `query` string (for scoring/context)
Output: Normalized profile dict with keys:
        - `full_name`, `email`, `location`, `technology`, `years_of_experience`,
          `linkedin_url`, `github_url`, `security_clearance`, `skill set`,
          - `source_platform`, `bio_text`, `profile_url`
Notes:
- Parsers fill missing `technology` via `_extract_technology(skills, bio_text, query)`
- Parsers fill missing `security_clearance` via `_extract_security_clearance(bio_text)`
- GitHub parser may call `fetch_github_user_profile()` for details if pre-structured data missing
- LinkedIn parser calls Bright Data enrichment when `BRIGHTDATA_API_KEY` set (⚠️ non-functional / stub)
- Web parser calls `scrape_page()` (Playwright → requests fallback) to extract contact info
- File location: skills/profile_scraper/scraper.py

# _score_profile
Input:  - `profile` dict (as above)
        - `query` string
Output: Float score 0.0–1.0 (higher = better)
Breakdown:
  - Completeness (0.5 weight): proportion of 9 required fields non-empty
  - Relevance (0.3 weight): fraction of query terms found in `bio_text` + `skills`
  - Source Trust (0.2 weight): mapping → LinkedIn(Bright Data):1.0, GitHub:0.9, LinkedIn(fallback):0.8, Web:0.5
- File location: skills/profile_scraper/run.py (function: _score_profile)

# save_profile
Input:  - `profile` dict (must have `full_name` and pass USA location check)
Output: Status string:
        - `"Profile saved to <Tech> sheet"` (complete record)
        - `"Incomplete: Missing email"` (saved to `<Tech=Technology, e.g. "Python Engineer")
        - `"Incomplete: Missing email"` (saved to `<Tech>_Incomplete` sheet)
        - `"Rejected: <reason>"` (non-USA, missing name, etc.)
        - `"Duplicate skipped: <field> <value> already exists"`
        - `"Error saving profile: <exception>"`
Behavior:
- Creates/opens Excel workbook at `EXCEL_OUTPUT_PATH` (default: skills/output/profiles.xlsx)
- Infers missing `technology`/`security_clearance` via helpers from scraper.py
- Dedupes by checking existing sheets for matching email, LinkedIn URL, or Github URL
- Appends row to appropriate sheet (main or `_Incomplete`)
- File location: skills/profile_scraper/scraper.py (function: save_profile)

# enrich_incomplete_profiles
Input:  - `limit` (int, default 25) – max incomplete profiles to attempt enrichment on
Output: Dict with keys:
        - `promoted` (int): count of profiles successfully enriched & moved to main sheet
        - `message` or `error` (string)
Requires: `HUNTER_API_KEY`
Process:
- Scans all `_Incomplete_*` sheets for rows lacking email
- Tries enrichment via:
   1. LinkedIn handle (if URL present) → Hunter.io email-finder
   2. First + last name from `full_name` → Hunter.io email-finder
- On success: updates email in incomplete sheet, appends full row to main `<Tech>` sheet, deletes row from incomplete sheet
- File location: skills/profile_scraper/scraper.py (function: enrich_incomplete_profiles)

# segregate
Input:  - Excel workbook path (default: skills/output/profiles.xlsx)
Behavior:
- Reads all sheets, groups rows by inferred technology
- Rewrites workbook with one sheet per technology (plus Summary, All Profiles, etc.)
- Handles sheet-name sanitization & truncation to Excel limits
- Applies technology mapping from TECH_TO_SHEET_MAP in segregate.py
- File location: segregate.py (in workspace root) - function: main()