import os
import httpx
from dotenv import load_dotenv

load_dotenv()
serper_key = os.getenv("SERPER_API_KEY")
serpapi_key = os.getenv("SERPAPI_KEY")
cse_key = os.getenv("GOOGLE_CSE_API_KEY")
cse_id = os.getenv("GOOGLE_CSE_ID")
gh_token = os.getenv("GITHUB_TOKEN")

print("--- DIAGNOSTIC CHECK OF SEARCH PROVIDERS ---")
print(f"SERPER_API_KEY : {'Present' if serper_key else 'Missing'}")
print(f"SERPAPI_KEY    : {'Present' if serpapi_key else 'Missing'}")
print(f"GOOGLE_CSE_KEY : {'Present' if cse_key else 'Missing'}")
print(f"GITHUB_TOKEN   : {'Present' if gh_token else 'Missing'}")

# 1. Test Serper.dev
if serper_key:
    headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
    q_complex = 'site:github.com "Snowflake" ("Snowflake Engineer" OR "Snowflake Developer") "USA" -inurl:orgs'
    r1 = httpx.post("https://google.serper.dev/search", headers=headers, json={"q": q_complex, "num": 10})
    print("\n1. Serper.dev Complex Query:")
    print("   Status:", r1.status_code)
    try:
        data1 = r1.json()
        print("   Credits / Msg:", data1.get("message") or data1.get("credits"))
        print("   Organic Results Count:", len(data1.get("organic", [])))
        if "message" in data1:
            print("   Message:", data1.get("message"))
    except Exception as e:
        print("   Error:", e)

# 2. Test SerpAPI
if serpapi_key:
    params = {"engine": "google", "q": "Snowflake Engineer", "api_key": serpapi_key}
    r2 = httpx.get("https://serpapi.com/search", params=params)
    print("\n2. SerpAPI:")
    print("   Status:", r2.status_code)
    try:
        data2 = r2.json()
        if "error" in data2:
            print("   Error:", data2.get("error"))
        else:
            print("   Organic Results Count:", len(data2.get("organic_results", [])))
    except Exception as e:
        print("   Error:", e)

# 3. Test GitHub Search API directly
if gh_token:
    headers_gh = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
    r3 = httpx.get("https://api.github.com/search/users", headers=headers_gh, params={"q": "Snowflake location:USA type:user", "per_page": 5})
    print("\n3. GitHub Search API:")
    print("   Status:", r3.status_code)
    try:
        data3 = r3.json()
        print("   Total Count:", data3.get("total_count"))
        print("   Items Returned:", len(data3.get("items", [])))
        for item in data3.get("items", [])[:3]:
            print("   -", item.get("login"), item.get("html_url"))
    except Exception as e:
        print("   Error:", e)
