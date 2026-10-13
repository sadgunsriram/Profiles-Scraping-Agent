# HEARTBEAT.md — Autonomous Maintenance Operations

## Scheduled Maintenance Tasks (Cron-Based)

The following automated tasks run on a fixed schedule to maintain agent efficiency and data quality. These operations require no judgment and are safe to run unattended.

### 1. Enrichment Retry (Hunter.io Pass on Incomplete Profiles)
- **Schedule**: Daily at 02:00 UTC (adjustable via configuration)
- **Trigger**: Time-based (cron)
- **Process**: 
  - Scans all `_Incomplete_*` sheets in the Excel workbook for profiles missing email addresses
  - Attempts enrichment using Hunter.io API (if `HUNTER_API_KEY` is configured)
  - Strategies:
    1. Extract LinkedIn handle from profile URL and use Hunter.io email-finder
    2. Parse first/last name from full name and use Hunter.io email-finder
  - On success: 
    - Updates email in the incomplete sheet
    - Appends complete profile to the corresponding technology's main sheet
    - Removes the row from the incomplete sheet
- **Output**: Summary posted to configured Slack channel (if webhook configured) showing number of profiles promoted
- **Safety**: 
  - Only runs if `HUNTER_API_KEY` is present in environment
  - Limited to 25 profiles per run by default (configurable)
  - Respects Hunter.io rate limits
  - Never modifies or creates data without API confirmation

### 2. Sheet Maintenance (Weekly Segregate Run)
- **Schedule**: Weekly, Sundays at 03:00 UTC (adjustable via configuration)
- **Trigger**: Time-based (cron)
- **Process**:
  - Executes the `segregate.py` script on the active Excel workbook
  - Reads all technology-specific sheets and `_Incomplete_*` sheets
  - Reorganizes workbook to ensure clean separation by technology
  - Creates/updates summary sheets (All Profiles, Incomplete Summary, etc.)
  - Handles sheet name sanitization and truncation to Excel limits (31 characters)
- **Output**: Summary posted to configured Slack channel (if webhook configured) showing sheets processed and any errors
- **Safety**:
  - Operates on a copy of the workbook first, then replaces original on success
  - Preserves all data - only reorganizes sheets
  - Logs any errors for manual review

## What Is NOT Scheduled (Important Restrictions)

The following operations are **NOT** configured to run automatically and must be triggered manually (typically via Slack):

### ❌ No Scheduled Scraping Runs
- **Reason**: SerpAPI, Google CSE, and Hunter.io have paid/rate-limited quotas
- **Risk**: Unattended scraping could consume quotas without oversight
- **Alternative**: Users initiate searches via Slack with specific queries
- **Future Consideration**: May enable scheduled scraping once usage patterns and costs are established

### ❌ No Ad-Hoc Enrichment Triggers
- Enrichment only occurs during the scheduled daily window
- Manual enrichment can be triggered by running `enrich_incomplete_profiles()` tool directly if needed between cycles

## Configuration Notes

All scheduled tasks respect these global settings from USER.md and agent configuration:
- **USA-only filtering**: All profiles still validated via `_is_usa_location()` before processing
- **Deduplication**: Checks against existing email/LinkedIn/GitHub in workbook before adding
- **Scoring threshold**: Profiles below 0.3 completeness/relevance score are filtered out (if applicable to the operation)
- **Slack notifications**: Completion summaries sent to configured webhook (if present)

## Manual Override Capability

Any scheduled task can be executed manually at any time by invoking the corresponding tool:
- `enrich_incomplete_profiles(limit=25)` 
- `segregate(workbook_path="skills/output/profiles.xlsx")`

Manual execution bypasses the schedule but follows all the same safety checks and logging.

---
_Automated maintenance ensures the agent remains efficient and data-rich between user-initiated scraping sessions._