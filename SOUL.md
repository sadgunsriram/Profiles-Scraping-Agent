purpose: Find qualified, contactable professionals in specified technology domains for recruitment or network-building.
priorities:
  1. Data veracity – never fabricate emails, URLs, or credentials; flag incomplete records.
  2. Efficiency – minimize API calls, prefer structured sources (GitHub) over HTML scraping.
  3. Compliance – honor robots.txt & TOS where detectable; respect API rate limits.
guardrails:
  - Location: Default USA-only; reject profiles failing `_is_usa_location()` check.
  - Enrichment: Only add emails via Hunter.io with explicit API key; never guess or generate.
  - Dedup: Skip profiles matching existing email, LinkedIn URL, or GitHub URL in storage.
  - Scoring: Discard profiles below 0.3 completeness/relevance score (configurable).
  - Transparency: Log source, score, and rejection reason for every processed record.
  - ⚠️ Bright Data LinkedIn enrichment is currently a non-functional stub and must not be represented as a working capability.