single-agent design rationale:
- The pipeline is linear and state-dependent (preflight_check → search → parse → score → save → enrich)
- Splitting would introduce complex inter-agent messaging (e.g., passing partial profiles, deduplication state)
- Current codebase is modest (~1.5k LOC) and cohesive; agent-boundary overhead outweighs benefits
- Future consideration: if Bright Data or Hunter.io become bottlenecks, could off-load enrichment to a sub-agent, but not needed for MVP.

decision: Keep as **one agent** (`profile-scraping-agent`) exposing the **seven tools above**.