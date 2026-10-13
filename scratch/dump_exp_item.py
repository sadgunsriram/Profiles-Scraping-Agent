import sys
sys.path.insert(0, '.')
from bs4 import BeautifulSoup
from skills.profile_scraper.browser_session import BrowserSessionManager

def dump():
    m = BrowserSessionManager()
    p = m.start_session()
    p.goto('https://www.linkedin.com/in/bryce-m-0b5bbaa4', wait_until='domcontentloaded')
    p.wait_for_timeout(2000)
    
    for _ in range(4):
        p.evaluate('''() => {
            const scroller = document.querySelector('main#workspace') || document.querySelector('main') || window;
            scroller.scrollBy(0, 800);
        }''')
        p.wait_for_timeout(1000)
        
    soup = BeautifulSoup(p.content(), 'html.parser')
    t = soup.find(string=lambda s: s and 'Cyber Security Engineer' in s)
    if t:
        cur = t.parent
        for _ in range(5):
            if cur:
                print(f"Parent {cur.name} class={cur.get('class')}:")
                nodes = [s.strip() for s in cur.find_all(string=True) if s.strip()]
                print("  Text nodes:", nodes)
                cur = cur.parent
    m.close()

if __name__ == '__main__':
    dump()
