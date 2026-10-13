import sys
sys.path.insert(0, '.')
from bs4 import BeautifulSoup
from skills.profile_scraper.browser_session import BrowserSessionManager

def test_exp():
    m = BrowserSessionManager()
    p = m.start_session()
    p.goto('https://www.linkedin.com/in/bryce-m-0b5bbaa4', wait_until='domcontentloaded')
    p.wait_for_timeout(2500)
    
    # Scroll main container progressively
    p.evaluate('''() => {
        const scroller = document.querySelector('main#workspace') || document.querySelector('main') || window;
        scroller.scrollBy(0, 1000);
    }''')
    p.wait_for_timeout(2500)
    
    p.evaluate('''() => {
        const scroller = document.querySelector('main#workspace') || document.querySelector('main') || window;
        scroller.scrollBy(0, 1000);
    }''')
    p.wait_for_timeout(2500)
    
    p.screenshot(path='scratch/diagnostic_exp_loaded.png')
    
    soup = BeautifulSoup(p.content(), 'html.parser')
    exp_matches = []
    for el in soup.find_all(['h2', 'h3', 'p', 'span', 'section', 'div']):
        txt = el.get_text().strip()
        if 'experience' in txt.lower() and len(txt) < 40 and txt not in exp_matches:
            exp_matches.append(txt)
    print("Experience-related matches:", exp_matches)
    
    # Look for dates
    import re
    date_regex = re.compile(r'([A-Za-z]{3,}\s+\d{4}|\d{4})\s*[-–—]\s*([A-Za-z]{3,}\s+\d{4}|Present|\d{4})')
    date_tags = soup.find_all(string=date_regex)
    print(f"Date strings found ({len(date_tags)}):", [d.strip() for d in date_tags][:5])
    
    m.close()

if __name__ == '__main__':
    test_exp()
