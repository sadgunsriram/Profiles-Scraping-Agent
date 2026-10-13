import sys
sys.path.insert(0, ".")
from skills.profile_scraper.query_builder import build_search_dorks, is_raw_boolean_query

q = '("CCNA" OR "CCNP" OR "CCIE") AND "Network Engineer" AND "open to work"'
print("Is raw boolean:", is_raw_boolean_query(q))
dorks = build_search_dorks(q, target_count=5, mode="linkedin", require_open_to_work=True)
print(f"\nGenerated Dorks ({len(dorks)}):")
for d in dorks:
    print(" ", d)
