import re
import sys
import time
import requests
from bs4 import BeautifulSoup

LIST_URL = sys.argv[1]
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 8
headers = {"user-agent": "Mozilla/5.0"}
html = requests.get(LIST_URL, headers=headers, timeout=20).text
soup = BeautifulSoup(html, "html.parser")
links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    if "/profile/" in href and href.startswith("https://www.realestateindia.com/profile/"):
        if href not in links:
            links.append(href)

for href in links[:LIMIT]:
    try:
        page = requests.get(href, headers=headers, timeout=20).text
        text = BeautifulSoup(page, "html.parser").get_text(" ", strip=True)
        m_name = re.search(r"More information\s+.+?\s+Mr\.\s*([A-Za-z][A-Za-z\s\.-]+?)\s+(?:\d|[A-Z]{2,}|Properties for Sale by)", text)
        if not m_name:
            m_name = re.search(r"More information\s+.+?\s+([A-Z][A-Za-z\s\.-]{4,}?)\s+(?:\d|[A-Z]{2,}|Properties for Sale by)", text)
        m_addr = re.search(r"More information\s+.+?\s+(?:Mr\.\s*[A-Za-z][A-Za-z\s\.-]+\s+)?(.{10,120}?)\s+Properties for Sale by", text)
        print("URL:", href)
        print("NAME:", m_name.group(1).strip() if m_name else "")
        print("ADDR:", m_addr.group(1).strip() if m_addr else "")
        print("---")
        time.sleep(1)
    except Exception as e:
        print("URL:", href)
        print("ERR:", e)
        print("---")
