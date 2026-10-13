import os
import httpx
from dotenv import load_dotenv

load_dotenv()
serper_key = os.getenv("SERPER_API_KEY")
gh_token = os.getenv("GITHUB_TOKEN")

print("=== TESTING OPTIMIZED SEARCH STRATEGIES ===")

# Test 1: Serper.dev with simplified dorks
headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
dorks_to_test = [
    'site:github.com "Snowflake" (Engineer OR Developer) "USA" -inurl:orgs',
    'site:github.com Snowflake Engineer USA -inurl:orgs',
    'site:github.com/ "Snowflake" "United States" -inurl:orgs',
    'site:github.com "Databricks" (Engineer OR Developer) "USA" -inurl:orgs'
]

for dork in dorks_to_test:
    r = httpx.post("https://google.serper.dev/search", headers=headers, json={"q": dork, "num": 5})
    data = r.json()
    count = len(data.get("organic", []))
    print(f"\nSerper Query: {dork}")
    print(f"Results Count: {count}")
    for item in data.get("organic", [])[:2]:
        print(f"  - {item.get('title')}: {item.get('link')}")

# Test 2: GitHub API with unquoted/flexible keywords
gh_headers = {"Authorization": f"Bearer {gh_token}"}
gh_queries = [
    "Snowflake location:USA type:user",
    "Snowflake Engineer location:USA type:user",
    "Databricks Engineer location:USA type:user"
]

for gq in gh_queries:
    r = httpx.get("https://api.github.com/search/users", headers=gh_headers, params={"q": gq, "per_page": 5})
    data = r.json()
    print(f"\nGitHub API Query: {gq}")
    print(f"Total Matches: {data.get('total_count')}")
    for item in data.get("items", [])[:2]:
        print(f"  - {item.get('login')}: {item.get('html_url')}")
