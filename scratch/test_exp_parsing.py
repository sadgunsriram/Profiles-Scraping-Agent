import sys
sys.path.insert(0, '.')
from bs4 import BeautifulSoup
from skills.profile_scraper.browser_session import BrowserSessionManager
from skills.profile_scraper.experience_extractor import extract_structured_experience

def test_exp_parsing():
    m = BrowserSessionManager()
    p = m.start_session()
    p.goto('https://www.linkedin.com/in/bryce-m-0b5bbaa4', wait_until='domcontentloaded')
    p.wait_for_timeout(2500)
    
    # Scroll main container
    for _ in range(4):
        p.evaluate('''() => {
            const scroller = document.querySelector('main#workspace') || document.querySelector('main') || window;
            scroller.scrollBy(0, 800);
        }''')
        p.wait_for_timeout(1000)
        
    html = p.content()
    jobs = extract_structured_experience(html)
    print(f"Jobs extracted from live HTML ({len(jobs)}):")
    for j in jobs:
        print(f"  - Title: {j.get('title')}, Company: {j.get('company')}, Dates: {j.get('start_date')} - {j.get('end_date')} ({j.get('duration_text')})")
        
    m.close()

if __name__ == '__main__':
    test_exp_parsing()
