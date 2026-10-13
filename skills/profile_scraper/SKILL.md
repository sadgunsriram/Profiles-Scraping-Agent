       ---
name: profile-scraper
description: Scrape professional profiles for any domain. Runs python skills/profile_scraper/run.py with the user's query.
user-invocable: true
command-dispatch: "tool"
command-tool: exec
command-arg-mode: raw
command-exec: "python skills/profile_scraper/run.py"
metadata: {"openclaw": {"always": true, "emoji": "🎯"}}
---

# SKILL: Profile Scraper

## What This Skill Does

Searches Google directly for professional LinkedIn profiles (`site:linkedin.com/in/`) matching any domain or query, extracts comprehensive experience and contact data, and evaluates candidates through the 5-layer analysis and eligibility pipeline before saving results immediately to an Excel workbook (`profiles.xlsx`).

## When to Use

Invoke this skill whenever a user asks to:
- Find professionals in any field ("Find IAM engineers", "Find Python engineers")
- Search for people with specific skills, titles, or specializations
- Build a contact list for any domain

---

## How to Invoke — One Command Only

```
python skills/profile_scraper/run.py "query" [num_results]
```

**Examples:**
```
python skills/profile_scraper/run.py "IAM engineers"
python skills/profile_scraper/run.py "python engineers" 20
python skills/profile_scraper/run.py "data scientists"
python skills/profile_scraper/run.py "cloud architects" 15
```

**That is all.** Do not write Python scraping code. Do not call scraper functions directly.
Run the command above.

`run.py` handles everything internally:
1. Searches Google (Serper.dev / SerpAPI / Google CSE) directly for LinkedIn profile URLs
2. Scrapes full profile sections (Top card, About, Experience, Education, Skills) via Playwright / Bright Data
3. Normalizes candidate data and validates US location
4. Performs candidate analysis (career tenure, relevant tech tenure, skill relevance, Ollama qualitative analysis)
5. Evaluates eligibility rules (mandatory knockouts, non-C2C/bench sales verification)
6. Persists immediately to `profiles.xlsx` across 4 sheets (`ALL_RAW_PROFILES`, `ELIGIBLE_CANDIDATES`, `NEEDS_REVIEW`, `REJECTED_CANDIDATES`)
7. Prints campaign summary and metrics report

---

## Query Construction

Extract the core domain/role from the user's message and pass it as the query.

| User says | Command to run |
|-----------|---------------|
| "scrape profiles on python engineers" | `run.py "python engineers"` |
| "find IAM professionals" | `run.py "IAM engineers"` |
| "get me data scientists" | `run.py "data scientists"` |
| "scrape 20 cloud architects" | `run.py "cloud architects" 20` |

Do not append "USA" — `run.py` enforces USA automatically.

---

## After the Command

Once `run.py` finishes, report the summary to the user:
- How many profiles were saved
- How many were incomplete
- How many were rejected (non-USA)

---

## Environment Variables Required

```
EXCEL_OUTPUT_PATH=profiles.xlsx   # optional, defaults to profiles.xlsx in the working directory
SERPER_API_KEY=...               # Primary Google Search API (fastest, supports dorks)
SERPAPI_KEY=...                  # Alternative Google Search API
GOOGLE_CSE_API_KEY=...           # Optional fallback (Google CSE)
GOOGLE_CSE_ID=...
HUNTER_API_KEY=...
BRIGHTDATA_API_KEY=...
# Optional:
GITHUB_TOKEN=...
```

---

## Data Quality Rules

- A profile needs: **Name + Location + (Email OR LinkedIn OR GitHub URL)** for the main sheet
- Non-USA locations are hard-rejected — nothing stored
- Missing required fields → stored in the `Incomplete` sheet for Hunter.io enrichment
- Technology and Security Clearances are best-effort keyword matches, not verified facts — expect blanks and occasional misses
