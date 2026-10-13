import sys
import json
import httpx
from bs4 import BeautifulSoup

q = " ".join(sys.argv[1:]).strip()
if not q:
    raise SystemExit("query required")

r = httpx.get(
    "https://www.bing.com/search",
    params={"q": q},
    headers={"user-agent": "Mozilla/5.0"},
    timeout=20,
    follow_redirects=True,
)
r.raise_for_status()
soup = BeautifulSoup(r.text, "html.parser")
out = []
for li in soup.select("li.b_algo")[:15]:
    a = li.select_one("h2 a")
    if not a:
        continue
    snippet = li.select_one(".b_caption p")
    out.append({
        "title": a.get_text(" ", strip=True),
        "href": a.get("href"),
        "snippet": snippet.get_text(" ", strip=True) if snippet else "",
    })
print(json.dumps(out, indent=2, ensure_ascii=False))
