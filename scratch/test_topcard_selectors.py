import sys
sys.path.insert(0, '.')
import re
from bs4 import BeautifulSoup
from skills.profile_scraper.browser_session import BrowserSessionManager

def test_selectors():
    m = BrowserSessionManager()
    p = m.start_session()
    p.goto('https://www.linkedin.com/in/bryce-m-0b5bbaa4', wait_until='domcontentloaded')
    p.wait_for_timeout(2500)
    
    soup = BeautifulSoup(p.content(), 'html.parser')
    
    # 1. Full name
    # Check title
    title = p.title()
    name_from_title = ""
    if title and '|' in title:
        name_from_title = title.split('|')[0].strip()
        # Clean any trailing status or bracket
        name_from_title = re.sub(r'\(.*?\)', '', name_from_title).strip()
    print("Name from title:", name_from_title)
    
    # Check topcard section
    topcard = soup.find(attrs={'componentkey': lambda k: k and 'Topcard' in k})
    print("Topcard found:", bool(topcard))
    if topcard:
        text_nodes = [s.strip() for s in topcard.find_all(string=True) if s.strip()]
        print("Topcard text nodes (first 10):", text_nodes[:10])
        
    m.close()

if __name__ == '__main__':
    test_selectors()
