import os
import re
import httpx
import json
import time
import random
import base64
from typing import List, Dict, Any
from urllib.parse import urlparse
from dotenv import load_dotenv
_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
load_dotenv(dotenv_path=_env_path, override=True)

# Map environment variables for compatibility with various key names
if not os.getenv("SERPAPI_API_KEY") and os.getenv("SERPAPI_KEY"):
    os.environ["SERPAPI_API_KEY"] = os.getenv("SERPAPI_KEY")
if not os.getenv("SERPAPI_KEY") and os.getenv("SERPAPI_API_KEY"):
    os.environ["SERPAPI_KEY"] = os.getenv("SERPAPI_API_KEY")
if not os.getenv("CSE_ID") and os.getenv("GOOGLE_CSE_ID"):
    os.environ["CSE_ID"] = os.getenv("GOOGLE_CSE_ID")
if not os.getenv("CSE_KEY") and os.getenv("GOOGLE_CSE_API_KEY"):
    os.environ["CSE_KEY"] = os.getenv("GOOGLE_CSE_API_KEY")


import skills.profile_scraper.role_expansion as role_expansion

# Global provider request counters for Rejection Analytics
PROVIDER_REQUEST_COUNTS = {
    "Google CSE": 0,
    "Google CSE Rate Limits": 0,
    "Serper.dev": 0,
    "Serper.dev Rate Limits": 0,
    "SerpAPI": 0,
    "SerpAPI Rate Limits": 0,
    "GitHub REST API": 0,
    "Bright Data LinkedIn API": 0,
    "Bright Data LinkedIn API Rate Limits": 0
}

SERPAPI_EXHAUSTED = False

def query_with_backoff(func, *args, max_retries=3, initial_delay=2.0, **kwargs):
    """Executes a function with exponential backoff for network queries."""
    import time
    import random
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            resp = func(*args, **kwargs)
            if hasattr(resp, "status_code") and resp.status_code == 429:
                import httpx
                raise httpx.HTTPStatusError("API Rate Limited", request=getattr(resp, 'request', None), response=resp)
            return resp
        except Exception as e:
            status_code = None
            if hasattr(e, 'response') and e.response is not None:
                status_code = getattr(e.response, 'status_code', None)
                
            if status_code == 429 or "429" in str(e).lower() or "rate limit" in str(e).lower():
                fn_str = str(func).lower()
                if "serper" in fn_str:
                    PROVIDER_REQUEST_COUNTS["Serper.dev Rate Limits"] += 1
                elif "serpapi" in fn_str or "serp" in fn_str:
                    PROVIDER_REQUEST_COUNTS["SerpAPI Rate Limits"] += 1
                elif "google" in fn_str or "cse" in fn_str:
                    PROVIDER_REQUEST_COUNTS["Google CSE Rate Limits"] += 1
                elif "brightdata" in fn_str or "linkedin" in fn_str:
                    PROVIDER_REQUEST_COUNTS["Bright Data LinkedIn API Rate Limits"] += 1
                print(f"  [Luffy] API Rate Limited (HTTP {status_code or 429}). Retrying in {delay:.1f}s...")
                
            if attempt == max_retries - 1:
                if hasattr(e, 'response') and e.response is not None:
                    return e.response
                raise e
            time.sleep(delay + random.uniform(0.1, 0.5))
            delay *= 2.0

def search_all_sources(query: str, num: int = 10, page: int = 1, mode: str = "linkedin", require_open_to_work: bool = True) -> list:
    """
    Search all available sources and return combined results with per-technology routing.
    Sources: SerpAPI / Serper.dev / Google CSE (Direct LinkedIn) + GitHub (if mode == 'github')
    If require_open_to_work is True (default), injects Open to Work keywords into search queries.
    """
    results = []
    sources = []
    
    # Check if query is an explicit raw Boolean search query
    from skills.profile_scraper.query_builder import (
        is_raw_boolean_query,
        build_search_dorks,
        OPEN_TO_WORK_DORK_CLAUSE,
        OPEN_TO_WORK_GH_CLAUSE,
        is_open_to_work_query
    )

    if is_raw_boolean_query(query):
        dork_queries = build_search_dorks(query, target_count=num, mode=mode, require_open_to_work=require_open_to_work)
        classification = "BOOLEAN_EXPRESSION"
        category = "CUSTOM_BOOLEAN"
        tech_constraint = query
        roles_chunk = [query]
        print(f"  [Luffy] Sourcing Input   : '{query}' (Raw Boolean Syntax, require_open_to_work={require_open_to_work})")
        print(f"  [Luffy] Classification   : {classification}")
        print(f"  [Luffy] Dorks Generated  : {len(dork_queries)} regional dorks")
    else:
        # Classify and expand user input query
        expansion = role_expansion.classify_and_expand_query(query)
        
        classification = expansion["classification"]
        category = expansion["category"]
        tech_constraint = expansion["tech_constraint"]
        expanded_titles = expansion["expanded_list"]
        
        # Build unified parenthesized dork queries with Open to Work clauses
        dork_queries = build_search_dorks(query, target_count=num, mode=mode, require_open_to_work=require_open_to_work)
        
        print(f"  [Luffy] Sourcing Input   : '{query}' (require_open_to_work={require_open_to_work})")
        print(f"  [Luffy] Classification   : {classification}")
        print(f"  [Luffy] Category         : {category}")
        print(f"  [Luffy] Dorks Generated  : {len(dork_queries)} regional dorks")

    otw_clause = ""
    if require_open_to_work and not is_open_to_work_query(query):
        otw_clause = f" {OPEN_TO_WORK_DORK_CLAUSE}" if mode == "linkedin" else f" {OPEN_TO_WORK_GH_CLAUSE}"

    # Clearance-targeted dork queries if query mentions clearance or federal defense
    query_lower = query.lower()
    is_clearance_search = any(k in query_lower for k in [
        "clearance", "cleared", "security clearance", "secret", "ts/sci", "top secret", "public trust", "polygraph"
    ])
    if is_clearance_search:
        clearance_dork = '("Security Clearance" OR "TS/SCI" OR "Secret Clearance" OR "Top Secret" OR "Public Trust")'
        if mode == "linkedin":
            dork_queries.insert(0, f'site:linkedin.com/in/ "{tech_constraint or query}"{otw_clause} {clearance_dork} ("USA" OR "United States") -inurl:dir')
            dork_queries.append(f'site:linkedin.com/in/ "{tech_constraint or query}"{otw_clause} ("Lockheed" OR "Northrop" OR "Raytheon" OR "General Dynamics" OR "Booz Allen" OR "DoD") ("USA" OR "United States") -inurl:dir')
        else:
            dork_queries.insert(0, f'site:github.com "{tech_constraint or query}"{otw_clause} ("security clearance" OR "cleared" OR "TS/SCI" OR "secret clearance") ("USA" OR "United States") -inurl:orgs')

    # Dynamic technology-variant queries to expand query recall
    tech_variants = []
    category_upper = str(category).upper()
    if "AI" in category_upper or "MACHINE LEARNING" in category_upper or "ARTIFICIAL INTELLIGENCE" in category_upper:
        tech_variants = ["PyTorch", "TensorFlow", "Transformers", "LLM", "Generative AI"]
    elif "CLOUD" in category_upper or "DEVOPS" in category_upper or "INFRASTRUCTURE" in category_upper:
        tech_variants = ["Terraform", "Kubernetes", "AWS", "Ansible", "Docker"]
    elif "SECURITY" in category_upper or "CYBER" in category_upper:
        tech_variants = ["Splunk", "SIEM", "Incident Response", "Penetration", "SOC"]
    elif "NETWORK" in category_upper:
        tech_variants = ["Cisco", "Routing", "Switching", "BGP", "OSPF"]
    elif "SAP" in category_upper or "ENTERPRISE" in category_upper:
        tech_variants = ["ABAP", "Basis", "HANA", "FICO", "S4HANA"]
        
    if tech_variants:
        tech_or = " OR ".join([f'"{v}"' for v in tech_variants[:3]])
        if mode == "linkedin":
            dork_queries.append(f'site:linkedin.com/in/ "{tech_constraint}"{otw_clause} ({tech_or}) ("USA" OR "United States") -inurl:dir')
        else:
            dork_queries.append(f'site:github.com "{tech_constraint}"{otw_clause} ({tech_or}) ("USA" OR "United States") -inurl:orgs')

    # Distribute the target requests among:
    # 1. SerpAPI (with precise GitHub/LinkedIn dork queries)
    # 2. GitHub REST API user search (if mode is github)
    source_counts = {}
    source_counts["SerpAPI"] = 0
    source_counts["GitHub"] = 0
    
    available_sources = []
    if os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY") or os.getenv("SERPER_API_KEY") or os.getenv("GOOGLE_CSE_API_KEY"):
        available_sources.append("SerpAPI")
    if mode == "github":
        available_sources.append("GitHub")
    
    base_count = max(1, num // len(available_sources))
    remainder = num % len(available_sources)
    
    for i, source in enumerate(available_sources):
        source_counts[source] = base_count + (1 if i < remainder else 0)

    serp_start_offset = (page - 1) * source_counts.get("SerpAPI", 10)

    # 1. Run SerpAPI Search with rotated GitHub dork queries
    if "SerpAPI" in available_sources and source_counts["SerpAPI"] > 0:
        serp_limit = source_counts["SerpAPI"]
        for dq in dork_queries:
            if len(results) >= serp_limit:
                break
            needed = serp_limit - len(results)
            if os.getenv("SERPER_API_KEY"):
                provider = "Serper.dev"
            elif (os.getenv("GOOGLE_CSE_ID") or os.getenv("CSE_ID")) and (os.getenv("GOOGLE_CSE_API_KEY") or os.getenv("CSE_KEY")):
                provider = "Google CSE"
            else:
                provider = "SerpAPI"
            print(f"  [Luffy] Querying {provider} with dork: {dq} (page: {page})")
            serp_results = unified_google_search(dq, needed, start_offset=serp_start_offset)
            normalized_results = []
            for r in serp_results:
                link = r.get("link", "")
                parsed = urlparse(link)
                if "linkedin.com" in parsed.netloc:
                    # Filter international subdomains early (e.g. in.linkedin.com, uk.linkedin.com)
                    netloc_parts = (parsed.netloc or "").split(".")
                    if len(netloc_parts) >= 3 and netloc_parts[0] not in ("www", "linkedin"):
                        continue
                    # Clean/normalize LinkedIn URL
                    if "/in/" in parsed.path:
                        clean_link = f"https://www.linkedin.com{parsed.path}".split("?")[0].rstrip("/")
                        r["link"] = clean_link
                        r["source_platform"] = "LinkedIn"
                        if r["link"] not in [item.get("link") for item in normalized_results] and r["link"] not in [item.get("link") for item in results]:
                            normalized_results.append(r)
                elif mode == "github" and "github.com" in parsed.netloc:
                    path_parts = [p for p in parsed.path.split("/") if p]
                    if path_parts:
                        username = path_parts[0]
                        if username.lower() not in ("topics", "trending", "collections", "features", "pricing", "explore", "search", "about", "site", "contact", "marketplace", "security", "orgs"):
                            r["link"] = f"https://github.com/{username}"
                            r["source_platform"] = "GitHub"
                            # Deduplicate normalized links
                            if r["link"] not in [item.get("link") for item in normalized_results] and r["link"] not in [item.get("link") for item in results]:
                                normalized_results.append(r)
            results.extend(normalized_results)
        sources.append(provider if 'provider' in locals() else "Serper.dev")

    # 2. Run GitHub API search
    if "GitHub" in available_sources and source_counts["GitHub"] > 0:
        # Use clean unquoted role for GitHub REST API to ensure high matching recall
        clean_role = roles_chunk[0] if roles_chunk else query
        if tech_constraint and tech_constraint.lower() not in clean_role.lower():
            github_search_term = f"{tech_constraint} {clean_role}"
        else:
            github_search_term = clean_role
        github_search_term = github_search_term.replace('"', '').strip()
        print(f"  [Luffy] Querying GitHub API: {github_search_term} (page: {page})")
        github_results = github_search_users(github_search_term, source_counts["GitHub"], page=page)
        results.extend(github_results)
        sources.append("GitHub")

    print(f"[Luffy] Search completed using: {', '.join(sources)}")
    return results[:num]


def unified_google_search(query: str, num: int, start_offset: int = 0) -> list:
    """Unified search that executes Google queries prioritizing Serper.dev (fastest & dork-friendly), falling back to Google CSE or SerpAPI."""
    results = []
    
    # 1. Try Serper.dev (primary search provider)
    serper_key = os.getenv("SERPER_API_KEY")
    if serper_key:
        try:
            needed = num - len(results)
            current_page = (start_offset // 10) + 1
            while len(results) < num:
                PROVIDER_REQUEST_COUNTS["Serper.dev"] += 1
                limit = min(num - len(results), 10)
                
                def make_serper_request():
                    return httpx.post(
                        "https://google.serper.dev/search",
                        headers={
                            "X-API-KEY": serper_key,
                            "Content-Type": "application/json"
                        },
                        json={
                            "q": query,
                            "num": limit,
                            "page": current_page,
                            "gl": "us",
                            "hl": "en"
                        },
                        timeout=15.0
                    )
                    
                resp = query_with_backoff(make_serper_request)
                if resp.status_code == 200:
                    data = resp.json()
                    organic = data.get("organic", [])
                    if not organic:
                        break
                    for item in organic:
                        results.append({
                            "title": item.get("title", ""),
                            "link": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "source_platform": "web"
                        })
                    current_page += 1
                    time.sleep(random.uniform(0.5, 1.5))
                else:
                    print(f"  [Luffy] WARNING: Serper.dev error code {resp.status_code}: {resp.text}")
                    break
        except Exception as e:
            print(f"  [Luffy] WARNING: Serper.dev search error: {e}")
            
    if len(results) >= num:
        return results[:num]
        
    # 2. Try Google CSE (secondary fallback)
    cse_id = os.getenv("CSE_ID") or os.getenv("GOOGLE_CSE_ID")
    cse_key = os.getenv("CSE_KEY") or os.getenv("GOOGLE_CSE_API_KEY")
    if cse_id and cse_key:
        try:
            needed = num - len(results)
            print(f"  [Luffy] INFO: Falling back to Google CSE for query: {query}")
            PROVIDER_REQUEST_COUNTS["Google CSE"] += 1
            
            def make_cse_request():
                return httpx.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": cse_key,
                        "cx": cse_id,
                        "q": query,
                        "num": min(needed, 10),
                        "start": start_offset + 1
                    },
                    timeout=15.0
                )
                
            resp = query_with_backoff(make_cse_request)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "source_platform": "web"
                    })
            else:
                print(f"  [Luffy] WARNING: Google CSE error code {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            print(f"  [Luffy] WARNING: Google CSE search error: {e}")
            
    if len(results) >= num:
        return results[:num]
        
    # 3. Try SerpAPI (tertiary fallback)
    global SERPAPI_EXHAUSTED
    serpapi_key = os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")
    if serpapi_key and not SERPAPI_EXHAUSTED:
        try:
            needed = num - len(results)
            start = start_offset
            while len(results) < num:
                PROVIDER_REQUEST_COUNTS["SerpAPI"] += 1
                limit = min(num - len(results), 100)
                
                resp = httpx.get(
                    "https://serpapi.com/search",
                    params={
                        "engine": "google",
                        "q": query,
                        "api_key": serpapi_key,
                        "num": limit,
                        "start": start
                    },
                    timeout=15.0
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" in data:
                        err_msg = str(data["error"])
                        if "out of searches" in err_msg.lower():
                            SERPAPI_EXHAUSTED = True
                            print(f"  [Luffy] SerpAPI quota exhausted: {err_msg}")
                            break
                        print(f"  [Luffy] WARNING: SerpAPI JSON error: {err_msg}")
                        break
                    organic = data.get("organic_results", [])
                    if not organic:
                        break
                    for r in organic:
                        results.append({
                            "title": r.get("title", ""),
                            "link": r.get("link", ""),
                            "snippet": r.get("snippet", ""),
                            "source_platform": "web"
                        })
                    start += len(organic)
                    time.sleep(random.uniform(0.5, 1.5))
                elif resp.status_code == 429:
                    SERPAPI_EXHAUSTED = True
                    print("  [Luffy] SerpAPI quota exhausted (429). Disabling SerpAPI fallback for session.")
                    break
                else:
                    print(f"  [Luffy] WARNING: SerpAPI error page start={start}: {resp.status_code}")
                    break
        except Exception as e:
            print(f"  [Luffy] WARNING: SerpAPI fallback search error: {e}")
            
    return results[:num]


def fallback_google_search_link(query: str, patterns: list) -> str:
    """Run search and return the first link matching one of the pattern sub-strings."""
    results = unified_google_search(query, 5)
    for r in results:
        link = r.get("link", "")
        if any(pat in link.lower() for pat in patterns):
            return link.split("?")[0]
    return ""


def _serpapi_search(query: str, num: int) -> list:
    return unified_google_search(query, num)


def _google_cse_search(query: str, num: int) -> list:
    # Kept for compatibility
    results = []
    cse_id = os.getenv("CSE_ID") or os.getenv("GOOGLE_CSE_ID")
    cse_key = os.getenv("CSE_KEY") or os.getenv("GOOGLE_CSE_API_KEY")
    if cse_id and cse_key:
        try:
            resp = httpx.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": cse_key,
                    "cx": cse_id,
                    "q": query,
                    "num": min(num, 10)
                },
                timeout=15.0
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "source_platform": "web"
                    })
        except Exception:
            pass
    return results[:num]

def github_search_users(query: str, num: int, page: int = 1) -> list:
    """Search for users on GitHub with pagination."""
    try:
        github_token = os.getenv("GITHUB_TOKEN")
        headers = {}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
            headers["Accept"] = "application/vnd.github+json"
        
        clean_q = query.replace('"', '').strip()
        # Search for users in US
        resp = httpx.get(
            "https://api.github.com/search/users",
            params={
                "q": f'{clean_q} location:USA type:user',
                "per_page": min(num, 100),  # GitHub API max per page is 100
                "page": page,
            },
            headers=headers,
            timeout=10,
        )
        
        if resp.status_code != 200 or not resp.json().get("items"):
            # Fallback to location:US
            resp = httpx.get(
                "https://api.github.com/search/users",
                params={
                    "q": f'{clean_q} location:US type:user',
                    "per_page": min(num, 100),
                    "page": page,
                },
                headers=headers,
                timeout=10,
            )
        
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get("items", [])[:num]:
                # Get more details for each user
                user_resp = httpx.get(
                    item["url"],
                    headers=headers,
                    timeout=10,
                )
                
                if user_resp.status_code == 200:
                    user_data = user_resp.json()
                    # Extract relevant information
                    email = user_data.get("email") or ""
                    location = user_data.get("location") or ""
                    
                    # Try to get followers/following count as a proxy for activity/experience
                    followers = user_data.get("followers", 0)
                    following = user_data.get("following", 0)
                    public_repos = user_data.get("public_repos", 0)
                    
                    years_exp = "Not available"
                    
                    # Extract skills from repo languages if possible
                    skills = []
                    try:
                        repos_resp = httpx.get(
                            user_data["repos_url"],
                            params={"per_page": 5},
                            headers=headers,
                            timeout=10,
                        )
                        if repos_resp.status_code == 200:
                            repos_data = repos_resp.json()
                            lang_set = set()
                            for repo in repos_data:
                                if repo.get("language"):
                                    lang_set.add(repo["language"])
                            skills = list(lang_set)[:5]  # Limit to 5 skills
                    except:
                        pass  # If we can't get repos, continue without skills
                    
                    results.append({
                        "title": user_data.get("name") or user_data.get("login", ""),
                        "link": user_data.get("html_url", ""),
                        "snippet": f"GitHub user | {followers} followers | {public_repos} repos",
                        "source_platform": "github",
                        "full_name": user_data.get("name") or user_data.get("login", ""),
                        "email": email,
                        "location": location,
                        "skills": ", ".join(skills) if skills else "",
                        "years_of_exp": str(years_exp),
                        "github_username": user_data.get("login", ""),
                        "github_followers": followers,
                        "github_repos": public_repos,
                        "account_type": user_data.get("type") or "User"
                    })
                else:
                    # Fallback to basic info if we can't get user details
                    results.append({
                        "title": item.get("login", ""),
                        "link": item.get("html_url", ""),
                        "snippet": f"GitHub user | {item.get('followers', 0)} followers",
                        "account_type": "User",
                        "source_platform": "github",
                        "full_name": item.get("login", ""),
                        "github_username": item.get("login", ""),
                        "github_followers": item.get("followers", 0)
                    })
            
            return results
        else:
            print(f"  [Luffy] WARNING: GitHub search error: {resp.status_code}")
            return []
    except Exception as e:
        print(f"  [Luffy] WARNING: GitHub search exception: {e}")
        return []

def brightdata_linkedin_search(query: str, _, num: int) -> list:
    """Search for people on LinkedIn using Bright Data API.
    
    Args:
        query: Search query
        _: Unused parameter (for compatibility with caller)
        num: Number of results to return
    
    Returns:
        List of profile dictionaries
    """
    try:
        api_key = os.getenv("BRIGHTDATA_API_KEY")
        if not api_key:
            return []
        
        # Bright Data LinkedIn search via Bright Data would typically work like this:
        # Note: Actual implementation depends on Bright Data's specific API
        # This is a placeholder that explains what would happen
        
        print(f"  [Luffy] INFO: Bright Data LinkedIn search would be performed for: {query}")
        print(f"  [Luffy] INFO: Would return up to {num} results if API key were configured")
        
        # In a real implementation, this would make an HTTP request to Bright Data's API
        # For now, we return an empty list since we don't have the actual API credentials/endpoint
        return []
        
        # Example of what a real implementation might look like (commented out):
        '''
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # This is a simplified example - actual Bright Data API usage may differ
        payload = {
            "zone": "linkedin_people_scraper",
            "url": f"https://www.linkedin.com/search/results/people/?keywords={requests.utils.quote(query)}",
            "format": "json"
        }
        
        resp = httpx.post(
            "https://api.brightdata.com/datasets/v3/trigger",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if resp.status_code == 200:
            # Process the response according to Bright Data's format
            # This would need to be adapted to the actual API response structure
            data = resp.json()
            results = []
            # Extract and format profile data from data
            # ...
            return results[:num]
        else:
            print(f"  [Luffy] WARNING: Bright Data API error: {resp.status_code}")
            return []
        '''
    except Exception as e:
        print(f"  [Luffy] WARNING: Bright Data LinkedIn search exception: {e}")
        return []

def _search_linkedin_url(name: str, location: str, github_username: str = "") -> str:
    """Search for LinkedIn URL using search engines as a fallback, with alternate query retries."""
    try:
        if not name or len(name.strip()) < 2:
            if github_username:
                name = github_username
            else:
                return ""
                
        # Query 1: "{full_name}" LinkedIn location
        search_query = f'"{name}" site:linkedin.com/in/'
        if location and location.strip():
            clean_loc = location.replace('"', '').strip()
            search_query += f' {clean_loc}'
            
        print(f"  [Luffy] Resolving LinkedIn URL (Query 1): {search_query}")
        link = fallback_google_search_link(search_query, ["linkedin.com/in/"])
        if link and "/pub/dir" not in link:
            return link
            
        # Query 2: Try "{full_name}" {github_username} site:linkedin.com/in/
        if github_username:
            search_query2 = f'"{name}" {github_username} site:linkedin.com/in/'
            print(f"  [Luffy] Resolving LinkedIn URL (Query 2): {search_query2}")
            link = fallback_google_search_link(search_query2, ["linkedin.com/in/"])
            if link and "/pub/dir" not in link:
                return link
                
        # Query 3: Try "{full_name}" {location} site:linkedin.com/in/
        if location and location.strip():
            clean_loc = location.replace('"', '').strip()
            search_query3 = f'"{name}" {clean_loc} site:linkedin.com/in/'
            print(f"  [Luffy] Resolving LinkedIn URL (Query 3): {search_query3}")
            link = fallback_google_search_link(search_query3, ["linkedin.com/in/"])
            if link and "/pub/dir" not in link:
                return link
                
        # Query 4: Try {github_username} site:linkedin.com/in/
        if github_username:
            search_query4 = f'{github_username} site:linkedin.com/in/'
            print(f"  [Luffy] Resolving LinkedIn URL (Query 4): {search_query4}")
            link = fallback_google_search_link(search_query4, ["linkedin.com/in/"])
            if link and "/pub/dir" not in link:
                return link
                
        return ""

    except Exception as e:
        print(f"  [Luffy] WARNING: _search_linkedin_url exception: {e}")
        return ""


# ---------------------------------------------------------------------------
# Compatibility helpers expected by run.py
# ---------------------------------------------------------------------------
# retired _extract_technology helper
def _extract_security_clearance(text):
    text = (text or "").lower()
    patterns = [
        r"active\s+top\s+secret",
        r"active\s+ts/sci",
        r"active\s+secret\s+clearance",
        r"holds?\s+(?:a\s+)?secret\s+clearance",
        r"holds?\s+(?:a\s+)?top\s+secret\s+clearance",
        r"security\s+clearance\s*:\s*(secret|top\s+secret|ts/sci|public\s+trust)"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).upper()
    return "Not available"

def _is_usa_location(location: str) -> bool:
    """Check if a location string represents a USA location."""
    if not location or not isinstance(location, str):
        return False
    
    location = location.strip()
    if not location:
        return False
    
    # Check for state abbreviations
    state_abbrevs = {
        'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID',
        'IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS',
        'MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK',
        'OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV',
        'WI','WY','DC'
    }
    
    # Check for full state names
    state_names = {
        'alabama','alaska','arizona','arkansas','california','colorado','connecticut',
        'delaware','florida','georgia','hawaii','idaho','illinois','indiana','iowa',
        'kansas','kentucky','louisiana','maine','maryland','massachusetts','michigan',
        'minnesota','mississippi','missouri','montana','nebraska','nevada','new hampshire',
        'new jersey','new mexico','new york','north carolina','north dakota','ohio',
        'oklahoma','oregon','pennsylvania','rhode island','south carolina','south dakota',
        'tennessee','texas','utah','vermont','virginia','washington','west virginia','wisconsin','district of columbia'
    }
    location_lower = location.lower()
    
    # Check if the location contains state abbreviations or names
    words = re.findall(r'\b[a-zA-Z]+\b', location_lower)
    for word in words:
        if word.upper() in state_abbrevs:
            return True
        if word in state_names:
            return True
    
    # Check for USA location patterns
    patterns = [
        r'(?:location|based in|lives?\s+in|from)[:\s]+([A-Z][a-zA-Z\s]{3,40})',
        r'([A-Z][a-zA-Z\s]+,\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC))'
    ]
    
    for pat in patterns:
        m = re.search(pat, location, re.IGNORECASE)
        if m:
            return True
    
    # Check if we have a city, state format
    if ', ' in location:
        parts = location.split(', ')
        if len(parts) == 2:
            possible_state = parts[1].strip()
            if len(possible_state) == 2 and possible_state.upper() in state_abbrevs:
                return True
            if possible_state.lower() in state_names:
                return True
    
    # Check for USA-specific indicators
    usa_indicators = ['usa', 'united states', 'america', 'u.s.', 'u.s.a.']
    for indicator in usa_indicators:
        if indicator in location_lower:
            return True
    
    return False


def scrape_page(url: str, fallback_snippet: str = "") -> str:
    """Scrape a webpage for text content using Playwright (fallback to requests if Playwright fails)."""
    try:
        # Try Playwright first for JavaScript-heavy sites
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=15000)
            # Wait for content to load
            page.wait_for_timeout(2000)
            # Get text content
            text = page.evaluate("() => document.body.innerText")
            browser.close()
            
            if text and len(text.strip()) > 50:
                return text.strip()
    except Exception as e:
        # Fallback to requests if Playwright fails
        print(f"  [Luffy] WARNING: Playwright scrape failed for {url}: {e}")
        pass
    
    # Fallback to requests+BeautifulSoup
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        # Clean up text
        lines = ((line or "").strip() for line in (text or "").splitlines())
        chunks = ((phrase or "").strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        if (text or "") and len((text or "").strip()) > 50:
            return (text or "").strip()
    except Exception as e:
        print(f"  [Luffy] WARNING: Requests scrape failed for {url}: {e}")
        pass
    
    # If all scraping fails, return the fallback snippet
    if fallback_snippet:
        return fallback_snippet
    return ""


def fetch_github_user_profile(url: str) -> dict:
    """Fetch detailed GitHub user profile information."""
    try:
        if not url or 'github.com' not in url:
            return {'error': 'Invalid GitHub URL'}
        
        path = urlparse(url).path.strip('/')
        if not path:
            return {'error': 'Could not extract username from URL'}
        
        username = path.split('/')[0]
        if not username or username.lower() in ('settings', 'explore', 'trending', 'notifications', 'repositories', 'stars', 'pulls', 'issues', 'marketplace', 'explore'):
            return {'error': 'Invalid GitHub username'}
        
        github_token = os.getenv("GITHUB_TOKEN")
        headers = {}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        
        # Increment provider request count
        PROVIDER_REQUEST_COUNTS["GitHub REST API"] += 1
        
        # Fetch user data with backoff
        def make_user_req():
            return httpx.get(
                f"https://api.github.com/users/{username}",
                headers=headers,
                timeout=10
            )
        user_resp = query_with_backoff(make_user_req)
        
        if user_resp.status_code != 200:
            return {'error': f'GitHub API error: {user_resp.status_code}'}
        
        user_data = user_resp.json()
        
        if user_data.get('type') == 'Organization':
            return {
                'error': 'GitHub account type is Organization',
                'account_type': 'Organization',
                'full_name': user_data.get('name') or user_data.get('login') or username
            }
        
        # Increment count for repos fetch
        PROVIDER_REQUEST_COUNTS["GitHub REST API"] += 1
        
        # Fetch user repositories to get languages with backoff
        def make_repos_req():
            return httpx.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 100, "sort": "updated"},
                headers=headers,
                timeout=10
            )
        repos_resp = query_with_backoff(make_repos_req)
        
        languages = set()
        repos_info = []
        if repos_resp.status_code == 200:
            repos_data = repos_resp.json()
            for repo in repos_data:
                if isinstance(repo, dict):
                    if repo.get('language'):
                        languages.add(repo['language'])
                    repos_info.append({
                        'name': repo.get('name') or '',
                        'description': repo.get('description') or ''
                    })
        
        profile = {
            'full_name': user_data.get('name') or user_data.get('login'),
            'email': user_data.get('email') or '',
            'location': user_data.get('location') or '',
            'bio_text': user_data.get('bio') or '',
            'profile_url': user_data.get('html_url') or url,
            'source_platform': 'github',
            'followers': user_data.get('followers', 0),
            'following': user_data.get('following', 0),
            'public_repos': user_data.get('public_repos', 0),
            'created_at': user_data.get('created_at'),
            'updated_at': user_data.get('updated_at'),
            'github_username': user_data.get('login'),
            'company': user_data.get('company') or '',
            'blog': user_data.get('blog') or '',
            'account_type': user_data.get('type') or 'User',
            'repos': repos_info,
        }
        
        profile['mobile_phone'] = ""
        
        if languages:
            profile['skills'] = list(languages)[:10]
        else:
            profile['skills'] = []
        
        years_exp = None
        bio_val = user_data.get('bio') or ''
        m_bio = re.search(r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience', bio_val, re.IGNORECASE)
        if m_bio:
            years_exp = int(m_bio.group(1))
        elif user_data.get('created_at'):
            m_yr = re.search(r'\b(200[8-9]|201\d|202[0-6])\b', str(user_data['created_at']))
            if m_yr:
                years_exp = max(1, 2026 - int(m_yr.group(1)))
        
        profile['years_of_experience'] = years_exp if years_exp is not None else "Not available"
        
        return profile
        
    except Exception as e:
        return {'error': f'Failed to fetch GitHub profile: {str(e)}'}


from abc import ABC, abstractmethod

class LinkedInDataProvider(ABC):
    @abstractmethod
    def fetch_profile(self, url: str) -> dict:
        pass

class BrightDataProvider(LinkedInDataProvider):
    def fetch_profile(self, url: str) -> dict:
        raw_profile = self._scrape_brightdata(url)
        if not raw_profile or 'error' in raw_profile:
            return raw_profile
            
        skills_raw = raw_profile.get('skills')
        skills = [sk.get('name') for sk in skills_raw if isinstance(sk, dict) and sk.get('name')] if isinstance(skills_raw, list) else []
        contact_info = raw_profile.get('contact_info') or {}
        email_val = contact_info.get('email') or "" if isinstance(contact_info, dict) else ""
        phone_val = contact_info.get('phone') or "" if isinstance(contact_info, dict) else ""
        
        about_text = raw_profile.get('about') or ""
        position_text = raw_profile.get('position') or ""
        exp_text = " ".join([f"{j.get('title', '')} {j.get('description', '')}" for j in (raw_profile.get('experience') or []) if isinstance(j, dict)])
        certs_text = " ".join([f"{c.get('title', '')} {c.get('subtitle', '')} {c.get('meta', '')}" for c in (raw_profile.get('certifications') or []) if isinstance(c, dict)])
        recs_text = " ".join([str(r) for r in (raw_profile.get('recommendations') or [])])
        edu_text = " ".join([f"{e.get('degree', '')} {e.get('field_of_study', '')}" for e in (raw_profile.get('education') or []) if isinstance(e, dict)])
        lang_text = " ".join([str(l) for l in (raw_profile.get('languages') or [])])
        proj_text = " ".join([f"{p.get('title', '')} {p.get('description', '')}" for p in (raw_profile.get('projects') or []) if isinstance(p, dict)])
        
        full_scan_text = f"{about_text} {position_text} {exp_text} {certs_text} {recs_text} {edu_text} {lang_text} {proj_text}"
        
        security_clearance = "Not available"
        clearance_patterns = [
            (r'\b(ts/sci|ts-sci|top secret/sci|top secret-sci)\b', 'TS/SCI'),
            (r'\b(top secret|active top secret)\b', 'TOP SECRET'),
            (r'\b(secret|active secret)\b', 'SECRET'),
            (r'\b(ci poly|ci-poly|counterintelligence polygraph)\b', 'CI Poly'),
            (r'\b(fs poly|fs-poly|full scope polygraph)\b', 'FS Poly'),
            (r'\b(dod clearance)\b', 'DoD Clearance'),
            (r'\b(security clearance|active clearance|clearance|cleared|public trust)\b', 'Yes')
        ]
        for pattern, label in clearance_patterns:
            if re.search(pattern, full_scan_text, re.IGNORECASE):
                security_clearance = label
                break
                
        visa_status = "Unknown"
        visa_patterns = [
            (r'\b(us citizen|u\.s\.\s+citizen|united states citizen)\b', 'US Citizen'),
            (r'\b(citizen|citizenship)\b', 'Citizen'),
            (r'\b(green card|green-card|permanent resident)\b', 'Green Card'),
            (r'\b(gc|pr)\b', 'GC/PR'),
            (r'\b(h1b|h-1b)\b', 'H1B'),
            (r'\b(h4 ead|h4-ead)\b', 'H4 EAD'),
            (r'\b(ead|employment authorization document)\b', 'EAD'),
            (r'\b(stem opt|stem-opt)\b', 'STEM OPT'),
            (r'\b(opt|optional practical training)\b', 'OPT'),
            (r'\b(cpt|curricular practical training)\b', 'CPT'),
            (r'\b(tn visa|tn status)\b', 'TN'),
            (r'\b(l1 visa|l-1 visa|l1|l-1)\b', 'L1'),
            (r'\b(l2 visa|l-2 visa|l2|l-2)\b', 'L2'),
            (r'\b(authorized to work in the us|work authorization)\b', 'Authorized to work in the US')
        ]
        for pattern, label in visa_patterns:
            if re.search(pattern, full_scan_text, re.IGNORECASE):
                visa_status = label
                break

        experience_raw = raw_profile.get('experience') or []
        parsed_exp = []
        for job in experience_raw:
            if isinstance(job, dict):
                parsed_exp.append({
                    "title": job.get("title"),
                    "company": job.get("company_name"),
                    "start_date": job.get("start_date"),
                    "end_date": job.get("end_date"),
                    "description": job.get("description"),
                    "location": job.get("location")
                })
                
        edu_raw = raw_profile.get('education') or []
        parsed_edu = []
        for edu in edu_raw:
            if isinstance(edu, dict):
                parsed_edu.append({
                    "school_name": edu.get("school_name") or edu.get("institution") or edu.get("title"),
                    "degree": edu.get("degree"),
                    "field_of_study": edu.get("field_of_study"),
                    "start_year": edu.get("start_year"),
                    "end_year": edu.get("end_year"),
                    "description": edu.get("description")
                })

        github_url = None
        websites_raw = raw_profile.get('websites') or []
        for ws in websites_raw:
            url_str = ""
            if isinstance(ws, dict):
                url_str = ws.get('url') or ws.get('name') or ""
            elif isinstance(ws, str):
                url_str = ws
            if url_str and "github.com" in url_str.lower():
                github_url = url_str
                break
                
        if not github_url:
            gh_match = re.search(r'(https?://(?:www\.)?github\.com/[a-zA-Z0-9_-]+)', full_scan_text)
            if gh_match:
                github_url = gh_match.group(1)
                
        # Calculate years of experience from parsed_exp or bio if available
        bd_years_exp = None
        if parsed_exp:
            years_found = []
            for j in parsed_exp:
                for d_field in [j.get('start_date'), j.get('end_date')]:
                    if d_field:
                        m_y = re.search(r'\b(19\d{2}|20[0-2]\d)\b', str(d_field))
                        if m_y:
                            years_found.append(int(m_y.group(1)))
            if years_found:
                earliest = min(years_found)
                if 1980 <= earliest <= 2026:
                    bd_years_exp = max(1, 2026 - earliest)
        if bd_years_exp is None:
            m_bio_exp = re.search(r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience', full_scan_text, re.IGNORECASE)
            if m_bio_exp:
                bd_years_exp = int(m_bio_exp.group(1))

        normalized = {
            'full_name':           raw_profile.get('name') or None,
            'email':               email_val,
            'location':            raw_profile.get('city') or raw_profile.get('country_code') or "",
            'skills':              skills,
            'profile_url':         url,
            'source_platform':     'LinkedIn (Bright Data)',
            'years_of_experience': bd_years_exp if bd_years_exp is not None else "Not available",
            'bio_text':            raw_profile.get('about') or "",
            'github_url':          github_url,
            'mobile_phone':        phone_val,
            'experience_history':  parsed_exp,
            'headline':            raw_profile.get('position') or "",
            'current_company_name': raw_profile.get('current_company_name') or "",
            'certifications':      raw_profile.get('certifications') or [],
            'recommendations':     raw_profile.get('recommendations') or [],
            'education':           parsed_edu,
            'languages':           raw_profile.get('languages') or [],
            'projects':            raw_profile.get('projects') or [],
            'security_clearance':  security_clearance,
            'visa_status':         visa_status,
            'data_source':         'Bright Data',
            'linkedin_raw_response': raw_profile,
        }
        normalized['linkedin_normalized_profile'] = dict(normalized)
        return normalized

    def _scrape_brightdata(self, url: str) -> dict:
        try:
            api_key = os.getenv("BRIGHTDATA_API_KEY") or os.getenv("SERPAPI_KEY")
            if not api_key:
                return {'error': 'Bright Data API key not configured'}
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            scrape_url = "https://api.brightdata.com/datasets/v3/scrape"
            params = {
                "dataset_id": "gd_l1viktl72bvl7bjuj0"
            }
            payload = [{"url": url}]
            
            PROVIDER_REQUEST_COUNTS["Bright Data LinkedIn API"] += 1
            print(f"  [Luffy] Initial Request: Querying Bright Data synchronous scrape for URL: {url}")
            
            def make_initial_request():
                return httpx.post(
                    scrape_url,
                    headers=headers,
                    params=params,
                    json=payload,
                    timeout=120
                )
            resp = query_with_backoff(make_initial_request)
            
            if resp.status_code == 200:
                print(f"  [Luffy] Download: Data received synchronously (HTTP 200) for URL: {url}")
                data = resp.json()
            elif resp.status_code == 202:
                trigger_data = resp.json()
                snapshot_id = trigger_data.get("snapshot_id")
                if not snapshot_id:
                    return {'error': 'Bright Data response 202 Accepted but missing snapshot_id'}
                    
                print(f"  [Luffy] Status 202: Scrape request accepted asynchronously. Snapshot ID: {snapshot_id}")
                
                import time
                poll_start = time.time()
                max_duration = 180
                poll_interval = 5
                attempt = 0
                
                while True:
                    attempt += 1
                    elapsed = time.time() - poll_start
                    if elapsed > max_duration:
                        print(f"  [Luffy] Timeout: Polling exceeded max duration of {max_duration} seconds for snapshot {snapshot_id}")
                        return {'error': f'Bright Data scrape timed out after {max_duration} seconds'}
                        
                    print(f"  [Luffy] Polling: Check attempt {attempt} for snapshot {snapshot_id} (elapsed: {int(elapsed)}s)...")
                    
                    PROVIDER_REQUEST_COUNTS["Bright Data LinkedIn API"] += 1
                    
                    def make_status_request():
                        return httpx.get(
                            f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}",
                            headers=headers,
                            timeout=30
                        )
                    status_resp = query_with_backoff(make_status_request)
                    
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        status = status_data.get("status")
                        print(f"  [Luffy] Polling response status: {status}")
                        
                        if status == "ready":
                            print(f"  [Luffy] Completion: Scrape finished successfully. Downloading snapshot {snapshot_id}...")
                            
                            PROVIDER_REQUEST_COUNTS["Bright Data LinkedIn API"] += 1
                            
                            def make_download_request():
                                return httpx.get(
                                    f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}?format=json",
                                    headers=headers,
                                    timeout=60
                                )
                            data_resp = query_with_backoff(make_download_request)
                            if data_resp.status_code == 200:
                                data = data_resp.json()
                                break
                            else:
                                return {'error': f'Failed to download completed snapshot {snapshot_id}: HTTP {data_resp.status_code}'}
                        elif status == "failed":
                            return {'error': f'Bright Data snapshot {snapshot_id} execution failed'}
                    else:
                        print(f"  [Luffy] Polling status check failed: HTTP {status_resp.status_code}")
                        
                    time.sleep(poll_interval)
            else:
                return {'error': f'Bright Data API error: HTTP {resp.status_code}'}
                
            if isinstance(data, dict):
                return data
            elif isinstance(data, list) and len(data) > 0:
                return data[0]
            else:
                return {'error': 'Empty profile list returned from Bright Data'}
        except Exception as e:
            return {'error': f'Bright Data scrape exception: {str(e)}'}

def _clean_linkedin_company_name(val):
    for sep in ["·", "•", "Full-time", "Part-time", "Contract", "Freelance", "Self-employed"]:
        if sep in val:
            val = val.split(sep)[0]
    return val.strip().rstrip("·").rstrip("•").strip()

def _parse_linkedin_experience_html(html_content):
    """Parses LinkedIn experience HTML using the structured experience extraction module."""
    try:
        from skills.profile_scraper.experience_extractor import extract_structured_experience
        return extract_structured_experience(html_content)
    except Exception as e:
        logger.warning(f"Structured experience extraction exception: {e}")
        return []

def _extract_signalhire_contacts(page) -> dict:
    """
    Extracts contact info (email, phone) using the SignalHire Chrome Extension.
    Expands the floating sidebar, clicks 'Reveal Contacts', and reads revealed data.
    """
    contacts = {"email": "", "phone": "", "all_emails": [], "all_phones": []}
    try:
        # Allow the extension content script to initialize on the page
        page.wait_for_timeout(2000)
        
        # 1. Look for SignalHire floating trigger button if collapsed
        floating_btn = page.locator("button.floating-button, .floating-button, [class*='floating-button']").first
        if floating_btn.count() > 0 and floating_btn.is_visible():
            print("  [Luffy] SignalHire floating button found. Opening sidebar...")
            try:
                floating_btn.click(timeout=3000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  [Luffy] Note opening SignalHire sidebar: {e}")
                
        # 2. Check for "Reveal Contacts" or "Reveal All" button
        reveal_btn = page.locator("button:has-text('Reveal Contacts'), button:has-text('Reveal All'), text='Reveal Contacts'").first
        if reveal_btn.count() > 0 and reveal_btn.is_visible():
            print("  [Luffy] Clicking SignalHire 'Reveal Contacts' button...")
            try:
                reveal_btn.click(timeout=3000)
                # Wait for SignalHire to search and return results
                for _ in range(8):
                    page.wait_for_timeout(1000)
                    searching = page.locator("text='Contacts are being searched', text='Loading contacts...'").first
                    if searching.count() == 0 or not searching.is_visible():
                        break
            except Exception as e:
                print(f"  [Luffy] Note clicking Reveal Contacts: {e}")
        else:
            print("  [Luffy] SignalHire 'Reveal Contacts' button not visible or already revealed.")
            
        # 3. Read revealed contacts from container or shadow root
        content_box = page.locator(".contacts-list, .floating-button-content, [class*='floating-button-wrapper']").first
        box_text = ""
        if content_box.count() > 0:
            box_text = content_box.inner_text()
        else:
            cand = page.locator("div:has-text('Contact Info')").last
            if cand.count() > 0:
                box_text = cand.inner_text()
                
        if box_text:
            # Parse emails
            emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', box_text)
            clean_emails = [
                e.strip() for e in emails 
                if not any(ign in e.lower() for ign in ["signalhire", "example.com", "sentry", "wxt.dev", "domain.com"])
            ]
            if clean_emails:
                contacts["all_emails"] = list(dict.fromkeys(clean_emails))
                contacts["email"] = clean_emails[0]
                print(f"  [Luffy] SignalHire found email(s): {', '.join(contacts['all_emails'])}")
                
            # Parse phone numbers
            phones = re.findall(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', box_text)
            clean_phones = [p.strip() for p in phones if len(re.sub(r'\D', '', p)) >= 10]
            if clean_phones:
                contacts["all_phones"] = list(dict.fromkeys(clean_phones))
                contacts["phone"] = clean_phones[0]
                print(f"  [Luffy] SignalHire found phone(s): {', '.join(contacts['all_phones'])}")
                
    except Exception as e:
        print(f"  [Luffy] SignalHire extraction notice: {e}")
        
    return contacts

class AuthorizedLinkedInProvider(LinkedInDataProvider):
    """
    Authorized LinkedIn Provider using modular browser session management,
    event-based DOM readiness checks, and structured profile extraction.
    """
    def __init__(self, session_monitor=None):
        from skills.profile_scraper.config import load_config
        from skills.profile_scraper.session_monitor import SessionMonitor
        self.config = load_config()
        self.session_monitor = session_monitor or SessionMonitor(self.config)

    def _attempt_self_healing_login(self, page) -> bool:
        """Attempts to fill credentials if redirected to a login page."""
        username = self.config.linkedin_username
        password = self.config.linkedin_password
        if not username or not password or username == "your_email@example.com":
            return False

        try:
            user_input = page.locator("input#csm-v2_session_key:visible, input#username:visible, input#session_key:visible").first
            pass_input = page.locator("input#csm-v2_session_password:visible, input#password:visible, input#session_password:visible").first
            if user_input.is_visible() and pass_input.is_visible():
                user_input.fill(username)
                pass_input.fill(password)
                submit_btn = page.locator("button[data-id='sign-in-form__submit-btn']:visible, button[type=submit]:visible").first
                if submit_btn.is_visible():
                    submit_btn.click()
                    page.wait_for_load_state("domcontentloaded")
                    return True
        except Exception as ex:
            print(f"  [Luffy] Note on self-healing login: {ex}")
        return False

    def fetch_profile(self, url: str, require_open_to_work: bool = False) -> dict:
        from skills.profile_scraper.browser_session import BrowserSessionManager
        from skills.profile_scraper.page_readiness import navigate_to_profile, wait_for_profile_ready
        from skills.profile_scraper.profile_extractor import extract_full_profile
        from skills.profile_scraper.session_monitor import (
            SessionTerminatedException,
            CheckpointDetectedException,
            AuthenticationRequiredException,
            SessionLimitExceededException,
            ConsecutiveFailureLimitException
        )

        # 1. Enforce session limits
        try:
            self.session_monitor.check_limits()
        except SessionLimitExceededException as sle:
            return {"error": str(sle), "session_terminated": True, "reason": "SESSION_LIMIT_EXCEEDED"}

        manager = BrowserSessionManager(self.config)
        try:
            page = manager.start_session()

            # 2. Event-based navigation
            nav_ok = navigate_to_profile(page, url, timeout_ms=self.config.page_load_timeout)
            if not nav_ok:
                self.session_monitor.record_failure(url, "Navigation timeout or failure")
                manager.close()
                return {"error": f"Failed to navigate to candidate profile: {url}"}

            # 3. Check session health immediately after navigation
            try:
                self.session_monitor.check_page_health(page)
            except AuthenticationRequiredException as auth_err:
                if self._attempt_self_healing_login(page):
                    navigate_to_profile(page, url, timeout_ms=self.config.page_load_timeout)
                    self.session_monitor.check_page_health(page)
                else:
                    manager.close()
                    return {"error": str(auth_err), "session_terminated": True, "reason": "AUTH_EXPIRED"}
            except CheckpointDetectedException as chk_err:
                manager.close()
                return {"error": str(chk_err), "session_terminated": True, "reason": "CHECKPOINT_DETECTED"}

            # 4. Event-based DOM readiness check
            is_ready, reason = wait_for_profile_ready(page, timeout_ms=self.config.element_timeout)
            if not is_ready:
                # Re-verify page health in case redirect occurred
                try:
                    self.session_monitor.check_page_health(page)
                except SessionTerminatedException as term_err:
                    manager.close()
                    return {"error": str(term_err), "session_terminated": True, "reason": type(term_err).__name__}

                self.session_monitor.record_failure(url, f"Profile not ready: {reason}")
                manager.close()
                return {"error": f"Profile layout not ready: {reason}"}

            # 5. Extract structured profile data
            profile_data = extract_full_profile(
                page,
                url,
                enable_extension=self.config.enable_signalhire_extension,
                require_open_to_work=require_open_to_work
            )

            # 6. Record success
            self.session_monitor.record_success(url)
            manager.close()
            return profile_data

        except (SessionLimitExceededException, CheckpointDetectedException, ConsecutiveFailureLimitException) as term_exc:
            manager.close()
            return {"error": str(term_exc), "session_terminated": True, "reason": type(term_exc).__name__}
        except Exception as exc:
            self.session_monitor.record_failure(url, str(exc))
            manager.close()
            return {"error": f"Authorized LinkedIn extraction error: {str(exc)}"}

class FutureProvider(LinkedInDataProvider):
    def fetch_profile(self, url: str) -> dict:
        return {
            "linkedin_url": url,
            "full_name": None,
            "headline": "",
            "location": "",
            "about": "",
            "experience_history": [],
            "skills": [],
            "education": [],
            "certifications": [],
            "current_company_name": "",
            "data_source": "Future Provider (Placeholder)",
            "linkedin_raw_response": {},
            "linkedin_normalized_profile": {}
        }

def brightdata_linkedin_profile(url: str, require_open_to_work: bool = False) -> dict:
    """Fetch LinkedIn profile using default or configured LinkedInDataProvider."""
    try:
        provider_name = os.getenv("LINKEDIN_PROVIDER", "brightdata").lower()
        if provider_name == "authorized":
            provider = AuthorizedLinkedInProvider()
            return provider.fetch_profile(url, require_open_to_work=require_open_to_work)
        else:
            provider = BrightDataProvider()
            return provider.fetch_profile(url)
    except Exception as e:
        return {'error': f'Failed to fetch LinkedIn profile: {str(e)}'}


def _search_github_url(name: str, location: str) -> str:
    """Search for GitHub URL using search engines as a fallback."""
    try:
        # If we don't have good name info, return empty
        if not name or len(name.strip()) < 2:
            return ""
        
        # Try to search for the GitHub profile using SerpAPI or Google CSE
        search_query = f'"{name}" GitHub'
        if location and location.strip():
            search_query += f' "{location}"'
        
        # Try unified search fallback
        link = fallback_google_search_link(search_query, ["github.com/"])
        if link:
            return link
        return ""
    except Exception as e:
        print(f"  [Luffy] WARNING: _search_github_url exception: {e}")
        return ""


def _local_validate_phone(phone_str: str) -> str:
    """Validate and format phone number locally using phonenumbers package."""
    try:
        import phonenumbers
        # Parse US format by default (or check if starts with country prefix)
        parsed = phonenumbers.parse(phone_str, "US")
        is_valid = phonenumbers.is_valid_number(parsed)
        number_type = phonenumbers.number_type(parsed)
        
        # Map number type integer to human readable name
        from phonenumbers import PhoneNumberType
        type_str = "Unknown"
        if number_type == PhoneNumberType.MOBILE:
            type_str = "Mobile"
        elif number_type == PhoneNumberType.FIXED_LINE:
            type_str = "Fixed Line"
        elif number_type == PhoneNumberType.VOIP:
            type_str = "VoIP"
            
        formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
        status = "Valid" if is_valid else "Invalid Format"
        return f"{formatted} ({status} - {type_str} - Local)"
    except Exception:
        return f"{phone_str} (Format Error - Local)"


def _local_validate_email(email_str: str) -> dict:
    """Validate email format and check domain MX records locally using email-validator package."""
    try:
        from email_validator import validate_email, EmailNotValidError
        # Validates syntax and checks domain has valid MX/A records
        validation = validate_email(email_str, check_deliverability=True, timeout=10)
        return {
            'is_valid': True,
            'email': validation.normalized,
            'reason': 'Valid syntax & domain records (Local)'
        }
    except EmailNotValidError as e:
        return {
            'is_valid': False,
            'email': email_str,
            'reason': f'Local error: {str(e)}'
        }
    except Exception as e:
        # If network/DNS timeout occurs, at least check basic syntax
        try:
            from email_validator import validate_email
            validation = validate_email(email_str, check_deliverability=False)
            return {
                'is_valid': True,
                'email': validation.normalized,
                'reason': 'Valid syntax (Local - DNS skipped)'
            }
        except Exception as e2:
            return {
                'is_valid': False,
                'email': email_str,
                'reason': f'Local syntax error: {str(e2)}'
            }


def _validate_phone_with_abstract(phone_str: str) -> str:
    """Validate extracted phone number via Abstract Phone Intelligence API with local fallback."""
    if not phone_str or phone_str == "Not available":
        return "Not available"
        
    phone_key = os.getenv("ABSTRACT_PHONE_KEY")
    if not phone_key:
        return _local_validate_phone(phone_str)
        
    # Standardize/clean raw digits
    clean_digits = "".join(c for c in phone_str if c.isdigit())
    if not clean_digits:
        return f"{phone_str} (Format Error)"
        
    # Abstract requires country prefix. If US number and doesn't start with 1, add it.
    if len(clean_digits) == 10:
        clean_digits = "1" + clean_digits
        
    try:
        url = "https://phoneintelligence.abstractapi.com/v1/"
        params = {
            'api_key': phone_key,
            'phone': clean_digits,
        }
        # Avoid instant 429 requests per second limits
        time.sleep(0.5)
        response = httpx.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            is_valid = data.get('phone_validation', {}).get('is_valid', False)
            line_status = data.get('phone_validation', {}).get('line_status', 'unknown')
            line_type = data.get('phone_carrier', {}).get('line_type', 'unknown')
            
            # Format the output nicely for the spreadsheet
            status_suffix = []
            if is_valid:
                status_suffix.append("Valid")
            else:
                status_suffix.append("Invalid/Inactive")
                
            if line_type and line_type != 'unknown':
                status_suffix.append(line_type.title())
                
            if line_status and line_status != 'unknown':
                status_suffix.append(line_status.title())
                
            # Preferred formatting (national format if available, else clean digits)
            formatted_num = data.get('phone_format', {}).get('national') or phone_str
            return f"{formatted_num} ({' - '.join(status_suffix)})"
        else:
            print(f"  [Luffy] Phone validation API failed (status={response.status_code}). Falling back to local validation.")
            return _local_validate_phone(phone_str)
    except Exception as e:
        print(f"  [Luffy] Phone validation API exception ({e}). Falling back to local validation.")
        return _local_validate_phone(phone_str)


def _get_absolute_excel_path() -> str:
    """Resolve EXCEL_OUTPUT_PATH relative to the workspace root directory."""
    excel_path = os.getenv("EXCEL_OUTPUT_PATH", "skills/output/profiles.xlsx")
    if not os.path.isabs(excel_path):
        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        excel_path = os.path.abspath(os.path.join(workspace_root, excel_path))
    return excel_path


def log_rejected_candidate(identifier: str, source: str, stage: str, reason: str) -> None:
    """Log a rejected candidate to the _Rejected sheet in the Excel output file."""
    try:
        from openpyxl import load_workbook
        import os
        
        excel_path = _get_absolute_excel_path()
        os.makedirs(os.path.dirname(excel_path), exist_ok=True)
        
        if os.path.exists(excel_path):
            try:
                wb = load_workbook(excel_path)
            except PermissionError:
                # Excel file is locked even for loading, let's create a fresh memory workbook
                from openpyxl import Workbook
                wb = Workbook()
                if 'Sheet' in wb.sheetnames:
                    wb.remove(wb['Sheet'])
        else:
            from openpyxl import Workbook
            wb = Workbook()
            if 'Sheet' in wb.sheetnames:
                wb.remove(wb['Sheet'])
                
        sheet_name = "_Rejected"
        COLUMNS = ["Candidate identifier", "Source", "Stage rejected at", "Reason"]
        
        if sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(title=sheet_name)
            ws.append(COLUMNS)
        else:
            ws = wb[sheet_name]
            
        ws.append([identifier or "Unknown", source or "Unknown", stage or "Unknown", reason or "Unknown"])
        _save_workbook_with_fallback(wb, excel_path)
    except Exception as e:
        print(f"  [Luffy] ERROR writing to _Rejected sheet: {e}")


def _save_workbook_with_fallback(wb, excel_path: str) -> str:
    """Save the openpyxl workbook. Fall back to a timestamped backup file if locked."""
    try:
        wb.save(excel_path)
        return "saved"
    except PermissionError:
        import datetime
        dir_name = os.path.dirname(excel_path)
        base_name = os.path.basename(excel_path)
        name_part, ext_part = os.path.splitext(base_name)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(dir_name, f"{name_part}_LOCKED_{timestamp}{ext_part}")
        try:
            wb.save(backup_path)
            print(f"  [Luffy] WARNING: '{excel_path}' is open in Excel and locked. Saved data to fallback: {backup_path}")
            return f"backup_saved:{backup_path}"
        except Exception as e:
            print(f"  [Luffy] ERROR: Failed to save to fallback path '{backup_path}': {e}")
            raise e


from pydantic import BaseModel, Field

class CandidateRowModel(BaseModel):
    name: str = Field(..., min_length=1)
    technology: str
    years_of_exp: str = "Not available"
    linkedin: str = ""
    github: str = ""
    email: str = ""
    mobile_no: str = ""
    location: str = ""
    security_clearances: str = "Not available"
    skills: str = ""


def save_profile(profile: dict) -> str:
    """Save a profile to the Excel workbook, returning a status message."""
    try:
        from openpyxl import load_workbook
        import os
        
        excel_path = _get_absolute_excel_path()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(excel_path), exist_ok=True)
        
        # Load or create workbook
        wb_loaded_from_disk = False
        if os.path.exists(excel_path):
            try:
                wb = load_workbook(excel_path)
                wb_loaded_from_disk = True
            except PermissionError:
                # Target excel is locked on load, start a fresh workbook
                from openpyxl import Workbook
                wb = Workbook()
                if 'Sheet' in wb.sheetnames:
                    wb.remove(wb['Sheet'])
        else:
            from openpyxl import Workbook
            wb = Workbook()
            # Remove default sheet if it exists
            if 'Sheet' in wb.sheetnames:
                wb.remove(wb['Sheet'])
        
        # Define expected columns
        COLUMNS = [
            "Name", "Technology", "Years of exp", "LinkedIn", "GitHub",
            "Email", "Mobile No", "Location", "Security Clearances", "Skill set"
        ]
        
        # Check if we have the required minimum data (excluding email check)
        if not profile.get("full_name") or not profile.get("full_name").strip():
            log_rejected_candidate(profile.get("profile_url") or "Unknown", "save_profile", "Excel validation", "Missing name")
            return "Rejected: Missing name"
        
        # Validate USA location
        location = profile.get("location", "")
        if location and not _is_usa_location(location):
            log_rejected_candidate(profile.get("full_name") or "Unknown", "save_profile", "Excel validation", f"Non-USA location: {location}")
            return "Rejected: Non-USA location"
        
        # Determine which sheet to use based on technology
        technology = profile.get("technology", "")
        if not technology:
            technology = "Other"
        
        # Ensure technology is properly formatted for sheet name
        # Remove any invalid characters for Excel sheet names
        import re
        safe_technology = re.sub(r'[:\\/\?\*\[\]]', '_', technology)
        if len(safe_technology) > 31:
            safe_technology = safe_technology[:31]
            
        is_incomplete = not profile.get("email") or not profile.get("email").strip()
        is_uncertain = profile.get("confidence_score") in ("Uncertain", "Needs Manual Review - API Failure")
        
        # Target sheet names
        if is_uncertain:
            main_sheet_name = f"{safe_technology}_Review"
            incomplete_sheet_name = f"{safe_technology}_Review_Incomplete"
        else:
            main_sheet_name = safe_technology
            incomplete_sheet_name = f"{safe_technology}_Incomplete"
            
        target_sheet_name = incomplete_sheet_name if is_incomplete else main_sheet_name
        
        # Ensure the sheet exists
        if target_sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(title=target_sheet_name)
            ws.append(COLUMNS)  # Header
        else:
            ws = wb[target_sheet_name]
        
        # Check for duplicates based on email, LinkedIn, or GitHub in BOTH main and incomplete sheets
        email = (profile.get("email") or "").strip().lower()
        linkedin = (profile.get("linkedin_url") or "").strip().lower()
        github = (profile.get("github_url") or "").strip().lower()
        
        sheets_to_check = []
        if wb_loaded_from_disk:
            if main_sheet_name in wb.sheetnames:
                sheets_to_check.append(wb[main_sheet_name])
            if incomplete_sheet_name in wb.sheetnames:
                sheets_to_check.append(wb[incomplete_sheet_name])
            
        for check_ws in sheets_to_check:
            for row in check_ws.iter_rows(min_row=2, values_only=True):
                if len(row) >= 10:
                    existing_email = (str(row[5]) or "").strip().lower() if row[5] else ""
                    existing_linkedin = (str(row[3]) or "").strip().lower() if row[3] else ""
                    existing_github = (str(row[4]) or "").strip().lower() if row[4] else ""
                    
                    if email and email == existing_email:
                        msg = f"Duplicate skipped: Email {email} already exists in {check_ws.title}"
                        log_rejected_candidate(profile.get("full_name") or "Unknown", "save_profile", "Excel Deduplication", msg)
                        return msg
                    if linkedin and linkedin == existing_linkedin:
                        msg = f"Duplicate skipped: LinkedIn {linkedin} already exists in {check_ws.title}"
                        log_rejected_candidate(profile.get("full_name") or "Unknown", "save_profile", "Excel Deduplication", msg)
                        return msg
                    if github and github == existing_github:
                        msg = f"Duplicate skipped: GitHub {github} already exists in {check_ws.title}"
                        log_rejected_candidate(profile.get("full_name") or "Unknown", "save_profile", "Excel Deduplication", msg)
                        return msg
        
        # Prepare and validate row data using Pydantic schema
        years_exp = profile.get("years_of_experience")
        years_exp_str = str(years_exp).strip() if years_exp is not None and str(years_exp).strip() != "" else "Not available"
        
        clearance = profile.get("security_clearance")
        clearance_str = str(clearance).strip() if clearance is not None and str(clearance).strip() != "" else "Not available"

        mobile = profile.get("mobile_phone", "") or "Not available"
        skills_val = ", ".join(profile.get("skills", [])) if isinstance(profile.get("skills", []), list) else str(profile.get("skills", ""))

        try:
            row_model = CandidateRowModel(
                name=profile.get("full_name") or "",
                technology=technology,
                years_of_exp=years_exp_str,
                linkedin=profile.get("linkedin_url") or "",
                github=profile.get("github_url") or "",
                email=profile.get("email") or "",
                mobile_no=mobile,
                location=profile.get("location") or "",
                security_clearances=clearance_str,
                skills=skills_val
            )
        except Exception as pydantic_err:
            err_msg = f"Schema validation failed: {str(pydantic_err)}"
            log_rejected_candidate(profile.get("full_name") or profile.get("profile_url") or "Unknown", "save_profile", "Pydantic Schema Validation", err_msg)
            return "Rejected: Schema validation failed"

        row_data = [
            row_model.name,
            row_model.technology,
            row_model.years_of_exp,
            row_model.linkedin,
            row_model.github,
            row_model.email,
            row_model.mobile_no,
            row_model.location,
            row_model.security_clearances,
            row_model.skills,
        ]
        
        # Add the row
        ws.append(row_data)
        
        # Save the workbook with fallback
        save_status = _save_workbook_with_fallback(wb, excel_path)
        
        if is_incomplete:
            if "backup_saved" in save_status:
                backup_file = save_status.split(":", 1)[1]
                return f"Incomplete: Saved to {target_sheet_name} sheet (locked fallback: {os.path.basename(backup_file)})"
            return f"Incomplete: Saved to {target_sheet_name} sheet"
            
        if "backup_saved" in save_status:
            backup_file = save_status.split(":", 1)[1]
            return f"Profile saved to {target_sheet_name} sheet (locked fallback: {os.path.basename(backup_file)})"
        return f"Profile saved to {target_sheet_name} sheet"
        
    except Exception as e:
        return f"Error saving profile: {str(e)}"


def enrich_incomplete_profiles(limit: int = 25) -> dict:
    """Enrich incomplete profiles using Abstract API to validate email permutations."""
    try:
        from openpyxl import load_workbook
        import os
        import httpx
        from urllib.parse import urlparse

        excel_path = _get_absolute_excel_path()
        abstract_api_key = os.getenv("ABSTRACT_API_KEY")

        if not abstract_api_key:
            return {'promoted': 0, 'error': 'Abstract API key not configured', 'provider_issue': 'Missing ABSTRACT_API_KEY'}

        if not os.path.exists(excel_path):
            return {'promoted': 0, 'error': 'Excel file not found'}

        # Load workbook
        wb = load_workbook(excel_path)

        promoted_count = 0
        provider_issue = None

        # Define expected columns
        COLUMNS = [
            "Name", "Technology", "Years of exp", "LinkedIn", "GitHub",
            "Email", "Mobile No", "Location", "Security Clearances", "Skill set"
        ]

        # Process each sheet ending with _Incomplete
        for sheet_name in wb.sheetnames:
            if not sheet_name.endswith('_Incomplete'):
                continue

            ws = wb[sheet_name]
            rows_to_delete = []

            # Process rows in this sheet
            for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
                # Check if we've reached our limit
                if promoted_count >= limit:
                    break

                # Extract data from row
                if len(row) < 9:
                    continue

                name = str(row[0].value).strip() if row[0].value else ""
                technology = str(row[1].value).strip() if row[1].value else ""
                years_exp = str(row[2].value).strip() if row[2].value else ""
                linkedin_url = str(row[3].value).strip() if row[3].value else ""
                github_url = str(row[4].value).strip() if row[4].value else ""
                email = str(row[5].value).strip() if row[5].value else ""
                mobile_phone = str(row[6].value).strip() if len(row) > 6 and row[6].value else "Not available"
                location = str(row[7].value).strip() if len(row) > 7 and row[7].value else ""
                security_clearance = str(row[8].value).strip() if len(row) > 8 and row[8].value else ""
                skill_set = str(row[9].value).strip() if len(row) > 9 and row[9].value else ""

                # Check if this profile needs enrichment (missing email)
                if not email:
                    enriched_email = None

                    # Extract first/last name
                    if name and len(name) >= 2:
                        clean_name = "".join(c for c in name if c.isalpha() or c.isspace()).strip()
                        name_parts = clean_name.split()
                        if len(name_parts) >= 2:
                            first_name = name_parts[0]
                            last_name = name_parts[-1]
                            
                            # Derive domain from GitHub API blog or email domain
                            domain = None
                            if github_url:
                                try:
                                    gh_profile = fetch_github_user_profile(github_url)
                                    if gh_profile and 'error' not in gh_profile:
                                        blog = gh_profile.get('blog', '')
                                        if blog:
                                            parsed_blog = urlparse(blog)
                                            blog_domain = parsed_blog.netloc or parsed_blog.path
                                            if blog_domain.startswith('www.'):
                                                blog_domain = blog_domain[4:]
                                            if '/' in blog_domain:
                                                blog_domain = blog_domain.split('/')[0]
                                            if '.' in blog_domain and len(blog_domain) > 3:
                                                domain = blog_domain.strip()
                                        
                                        if not domain and gh_profile.get('email'):
                                            gh_email = gh_profile.get('email')
                                            if '@' in gh_email:
                                                domain = gh_email.split('@')[-1].strip()
                                except Exception as e:
                                    print(f"  [Luffy] WARNING: Failed to fetch GitHub profile for {name}: {e}")
                            
                            # If a domain was successfully resolved, run guesses
                            if domain:
                                first_lower = first_name.lower()
                                last_lower = last_name.lower()
                                domain_lower = domain.lower()
                                guesses = [
                                    f"{first_lower}.{last_lower}@{domain_lower}",
                                    f"{first_lower[0]}{last_lower}@{domain_lower}"
                                ]
                                
                                for guess in guesses:
                                    # Determine if name matches first
                                    email_user = guess.split('@')[0]
                                    f_match = (first_lower in email_user)
                                    l_match = (last_lower in email_user)
                                    name_matched = f_match or l_match
                                    
                                    if not name_matched:
                                        print(f"  [Luffy] Guess {guess} rejected: name mismatch")
                                        continue
                                        
                                    # Try Abstract API first if key exists
                                    api_success = False
                                    if abstract_api_key:
                                        try:
                                            abstract_url = "https://emailreputation.abstractapi.com/v1/"
                                            params = {
                                                'api_key': abstract_api_key,
                                                'email': guess,
                                            }
                                            response = httpx.get(abstract_url, params=params, timeout=10)
                                            if response.status_code == 200:
                                                data = response.json()
                                                deliverability_dict = data.get('email_deliverability', {})
                                                deliverability = str(deliverability_dict.get('status', '')).upper()
                                                
                                                quality_dict = data.get('email_quality', {})
                                                quality_score = float(quality_dict.get('score', 0))
                                                is_smtp_valid = deliverability_dict.get('is_smtp_valid')
                                                
                                                confidence_ok = (quality_score >= 0.80) or (is_smtp_valid is True)
                                                
                                                if confidence_ok and deliverability in ('DELIVERABLE', 'RISKY'):
                                                    enriched_email = guess
                                                    print(f"  [Luffy] Abstract API email validation success: {name} -> {enriched_email} (score={quality_score})")
                                                    api_success = True
                                                    break
                                                else:
                                                    print(f"  [Luffy] Abstract API guess {guess} rejected: low quality (score={quality_score}) or undeliverable ({deliverability})")
                                                    # Avoid trying local if the API explicitly said it's bad
                                                    continue
                                            elif response.status_code in (401, 429):
                                                err_msg = response.json().get('error', {}).get('message', 'Account restricted/invalid key')
                                                print(f"  [Luffy] WARNING: Abstract API error ({response.status_code}): {err_msg}. Falling back to local validation.")
                                        except Exception as e:
                                            print(f"  [Luffy] WARNING: Abstract API error ({e}). Falling back to local validation.")
                                            
                                    # Local fallback if API is not set up, failed, or rate-limited
                                    if not api_success:
                                        local_res = _local_validate_email(guess)
                                        if local_res['is_valid']:
                                            enriched_email = local_res['email']
                                            print(f"  [Luffy] Local email validation fallback success: {name} -> {enriched_email} ({local_res['reason']})")
                                            break
                                        else:
                                            print(f"  [Luffy] Local email guess {guess} rejected: {local_res['reason']}")
                            else:
                                print(f"  [Luffy] Skipping email enrichment for {name}: No github blog/email domain found")

                    # If we found an email, promote the profile to the main sheet
                    if enriched_email:
                        main_sheet_name = sheet_name[:-len('_Incomplete')]
                        if main_sheet_name not in wb.sheetnames:
                            main_ws = wb.create_sheet(title=main_sheet_name)
                            main_ws.append(COLUMNS)
                        else:
                            main_ws = wb[main_sheet_name]
                        
                        row_data = [
                            name,
                            technology,
                            years_exp,
                            linkedin_url,
                            github_url,
                            enriched_email,
                            mobile_phone,
                            location,
                            security_clearance,
                            skill_set,
                        ]
                        main_ws.append(row_data)
                        
                        # Record row index to delete from incomplete sheet
                        rows_to_delete.append(row_idx)
                        promoted_count += 1
                        print(f"  [Luffy] Enriched {name} with email {enriched_email} and promoted to {main_sheet_name}")

                # Check if we've reached our limit (after processing the row)
                if promoted_count >= limit:
                    break

            # Delete promoted rows from the incomplete sheet in reverse order
            for r_idx in reversed(rows_to_delete):
                ws.delete_rows(r_idx)

            # Check if we've reached our limit (across all sheets)
            if promoted_count >= limit:
                break

        # Save the workbook if we made any changes
        if promoted_count > 0 or len(rows_to_delete) > 0:
            wb.save(excel_path)

        res = {
            'promoted': promoted_count,
            'message': f'Successfully enriched {promoted_count} profiles'
        }
        if provider_issue:
            res['provider_issue'] = provider_issue
        return res
    except Exception as e:
        return {'promoted': 0, 'error': f'Failed to enrich profiles: {str(e)}'}


def preflight_check():
    """Check that all required API keys are present before starting a scrape run."""
    import os

    required_keys = ["SERPAPI_API_KEY", "CSE_ID", "CSE_KEY"]
    optional_keys = ["GITHUB_TOKEN", "HUNTER_API_KEY", "BRIGHTDATA_API_KEY"]

    missing_required = [key for key in required_keys if not os.getenv(key)]

    if missing_required:
        error_msg = f"Missing {', '.join(missing_required)} — cannot run search"
        print(f"  [Luffy] {error_msg}")
        return False

    # Check optional keys and warn if missing
    missing_optional = [key for key in optional_keys if not os.getenv(key)]
    if missing_optional:
        print(f"  [Luffy] Warning: Optional keys not set: {', '.join(missing_optional)}")

    print("  [Luffy] READY — all required API keys present")
    return True


# =============================================================================
# OPENCLAW TOOL WRAPPERS
# These functions wrap the existing functionality for use as OpenClaw tools
# =============================================================================

def tool_preflight_check():
    """OpenClaw tool: Check that all required API keys are present before starting a scrape run."""
    return preflight_check()

def tool_search_all_sources(query: str, num: int = 10) -> list:
    """OpenClaw tool: Search all available sources and return combined results.
    
    Args:
        query: Search query string (e.g. "python engineers")
        num: Maximum total results to return (default: 10)
        
    Returns:
        List of dictionaries containing search results from all sources
    """
    # Run preflight check first
    if not preflight_check():
        return []  # Return empty list on failure - preflight_check already printed error
    
    # If we get here, credentials are OK, call original function
    return search_all_sources(query, num)

def tool_parse_github(result: dict, query: str) -> dict:
    """OpenClaw tool: Parse a GitHub search result into a normalized profile.
    
    Args:
        result: Dictionary from search_all_sources containing GitHub result
        query: Original search query for context
        
    Returns:
        Normalized profile dictionary
    """
    return _parse_github(result, query)

def tool_parse_linkedin(result: dict, query: str) -> dict:
    """OpenClaw tool: Parse a LinkedIn search result into a normalized profile.
    
    Args:
        result: Dictionary from search_all_sources containing LinkedIn result
        query: Original search query for context
        
    Returns:
        Normalized profile dictionary
    """
    return _parse_linkedin(result, query)

def tool_parse_web(result: dict, query: str) -> dict:
    """OpenClaw tool: Parse a web search result into a normalized profile.
    
    Args:
        result: Dictionary from search_all_sources containing web result
        query: Original search query for context
        
    Returns:
        Normalized profile dictionary
    """
    return _parse_web(result, query)

def tool_score_profile(profile: dict, query: str) -> float:
    """OpenClaw tool: Score a profile based on completeness, relevance, and source trust.
    
    Args:
        profile: Normalized profile dictionary
        query: Original search query for relevance scoring
        
    Returns:
        Float score between 0.0 and 1.0
    """
    # Import the scoring function from run.py
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from run import _score_profile
    return _score_profile(profile, query)

def tool_save_profile(profile: dict) -> str:
    """OpenClaw tool: Save a profile to the Excel workbook.
    
    Args:
        profile: Normalized profile dictionary (must have full_name and pass USA location check)
        
    Returns:
        Status string indicating result of save operation
    """
    return save_profile(profile)

def tool_enrich_incomplete_profiles(limit: int = 25) -> dict:
    """OpenClaw tool: Enrich incomplete profiles using Hunter.io API.
    
    Args:
        limit: Maximum number of incomplete profiles to attempt enrichment on (default: 25)
        
    Returns:
        Dictionary with 'promoted' count and optional 'message' or 'error'
    """
    return enrich_incomplete_profiles(limit)

def tool_segregate(workbook_path: str = "skills/output/profiles.xlsx") -> bool:
    """OpenClaw tool: Segregate the Excel workbook into technology-specific sheets.
    
    Args:
        workbook_path: Path to the Excel workbook to segregate (default: skills/output/profiles.xlsx)
        
    Returns:
        True if successful, False otherwise
    """
    import subprocess
    import sys
    
    # Change to the workbook's directory to ensure relative paths work
    workbook_dir = os.path.dirname(os.path.abspath(workbook_path))
    workbook_name = os.path.basename(workbook_path)
    
    # Run the segregate script
    cmd = [sys.executable, "segregate.py"]
    # If workbook_path is not the default, we need to modify segregate.py to accept argument
    # For now, we'll use the default path and copy if needed
    if workbook_path != "skills/output/profiles.xlsx":
        # Copy the workbook to the expected location
        import shutil
        shutil.copy2(workbook_path, "skills/output/profiles.xlsx")
    
    try:
        result = subprocess.run(cmd, cwd="/c/Users/USER/.openclaw/workspace/profile_scraping_agent", 
                              capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            # If we copied the workbook, copy it back
            if workbook_path != "skills/output/profiles.xlsx":
                shutil.copy2("skills/output/profiles.xlsx", workbook_path)
            return True
        else:
            print(f"  [Luffy] Segregation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"  [Luffy] Segregation error: {str(e)}")
        return False
