# Persistent State for Profile-Scraping Agent

## Dedup Keys
Description: Normalized identifiers of profiles already processed to prevent redundant work across runs
Format: Sets of hashed/normalized values stored separately for each identifier type
- `email_hashes`: SHA256 hashes of lowercase email addresses (for privacy)
- `linkedin_hashes`: SHA256 hashes of normalized LinkedIn profile URLs (removing query parameters, trailing slashes)
- `github_hashes`: SHA256 hashes of normalized GitHub profile URLs (removing query parameters, trailing slashes)
Update Mechanism: Added when a profile is successfully saved to the Excel workbook (main or incomplete sheet)
Purpose: Prevents re-processing and re-scoring of identical profiles across separate Slack-triggered sessions

## Last Run Timestamp
Description: ISO 8601 UTC timestamp of the last completed scraping run
Format: "YYYY-MM-DDTHH:MM:SSZ" (e.g., "2026-07-29T14:30:00Z")
Update Mechanism: Set at the end of each successful `run()` execution
Purpose: Enables optional coordination with external systems and provides audit trail of activity frequency

## API Usage Counters
Description: counters tracking consumption of rate-limited API services
Counters ( reset daily at midnight UTC ):
- `serpapi_searches`: Number of SerpAPI search requests made
- `google_cse_searches`: Number of Google Custom Search API requests made
- `github_api_calls`: Number of GitHub API requests made (includes both search and user/profile endpoints)
- `hunterio_requests`: Number of Hunter.io API requests made
- `hunterio_credits_used`: Estimated credits consumed (Hunter.io charges per lookup, not per request)
Update Mechanism: Incremented immediately before each API call within the scraper modules
Purpose: Enables self-monitoring of quota usage to prevent unexpected service interruption; can trigger warnings when approaching limits

## Sheet Watermark (For Incremental Enrichment)
Description: Tracks processing state of `_Incomplete_*` sheets to enable incremental enrichment runs
Structure: Dictionary mapping sheet names to last-processed row numbers or content hashes
- Key: Sheet name (e.g., "Python Engineer_Incomplete")
- Value: Object containing:
  - `last_processed_row`: Integer row number (1-indexed, header is row 1)
  - `content_hash`: SHA256 hash of the sheet's used range (to detect external modifications)
Update Mechanism: Updated after each enrichment_run completes processing of a sheet
Purpose: Allows daily enrichment_cron job to only process newly added incomplete rows, improving efficiency and reducing API calls

## Config Hash
Description: SHA256 hash of the agent's configuration files to detect changes requiring reinitialization
Included Files:
- USER.md
- SOUL.md  
- TOOLS.md
- IDENTITY.md
- AGENTS.md
- skills/config/industry_domains.json (if used)
- .env (excluding actual secret values - only checks for presence/structure of required keys)
Update Mechanism: Computed and stored at agent startup; compared against stored value
Purpose: Triggers re-read of configuration and potential self-reinitialization when agent configuration is modified externally

## State Management Notes
- This file should be updated atomically to prevent corruption
- All timestamp values are in UTC to avoid timezone confusion
- Hash values use SHA256 for collision resistance
- The agent should gracefully handle missing or corrupted MEMORY_FILE by starting with empty state
- Never store actual API keys or secrets in this file - only usage metrics and non-sensitive identifiers