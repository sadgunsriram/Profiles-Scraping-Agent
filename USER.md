# User Preferences and Configuration

## Default Technology Domains
Suggested starting points for queries (can be overridden per request):
- python engineer
- cloud engineer
- cybersecurity
- databricks engineer
- snowflake engineer
- sap consultant
- network engineer

## Geographic Filter
- usa_only: true (non-negotiable - agent will only process profiles with confirmed USA locations)

## Scoring & Quality Thresholds
- min_score_threshold: 0.3 (profiles below this completeness/relevance score are filtered out)
- max_results_per_query: 20 (maximum number of results to return per search query)

## Output Configuration
- default_output_path: skills/output/profiles.xlsx
- file_format: Excel workbook with technology-specific sheets
- sheet_naming: Technology names sanitized for Excel (max 31 chars, special characters replaced)

## Slack Notifications
- enabled: true
- channel: #recruiting-alerts
- events:
  - run_start: Notification when a scraping search begins
  - run_complete: Summary of profiles saved, incomplete, enriched, and duplicates skipped
  - enrichment_complete: Count of profiles promoted from incomplete to main sheets via Hunter.io
  - error: Alerts for missing API keys, Excel lock failures, or other critical issues

## Enrichment Preferences
- hunterio_enabled: true (when HUNTER_API_KEY is configured)
- enrichment_limit: 25 (max incomplete profiles to process per enrichment cycle)
- promotion_on_enrichment: true (profiles moved to main sheets when email found)

## Duplicate Handling
- strategy: Skip profiles matching existing email, LinkedIn URL, or GitHub URL in the workbook
- location: Check performed during save_profile() before writing to Excel
- fields_checked: email (lowercase), linkedin_url (normalized), github_url (normalized)

## Safety & Compliance
- usa_location_filter: Strictly enforced - no overrides
- data_integrity: Never fabricate or infer missing contact information
- rate_limiting: Respect API limits via built-in delays and backoff (where implemented)
- api_priority: Prefer official APIs over browser scraping when available