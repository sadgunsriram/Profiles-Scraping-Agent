from skills.profile_scraper.browser_session import BrowserSessionManager
from bs4 import BeautifulSoup

def inspect():
    m = BrowserSessionManager()
    p = m.start_session()
    p.goto('https://www.linkedin.com/in/bryce-m-0b5bbaa4', wait_until='domcontentloaded')
    p.wait_for_timeout(2500)
    
    soup = BeautifulSoup(p.content(), 'html.parser')
    
    # 1. Contact info link
    ci = soup.find('a', href=lambda x: x and 'contact-info' in x)
    print("Contact info link:", ci)
    if ci:
        print("Contact info parent container:", ci.parent.get_text(separator=' | '))
        print("Grandparent container:", ci.parent.parent.get_text(separator=' | '))
        
    # 2. Main sections
    sections = soup.find_all('section')
    print(f"Sections found ({len(sections)}):")
    for s in sections:
        h = s.find(['h1', 'h2', 'h3', 'p', 'div'])
        h_text = h.get_text().strip() if h else "no-heading"
        print(f"  section id={s.get('id')} class={s.get('class')}: heading='{h_text[:40]}'")
        
    m.close()

if __name__ == '__main__':
    inspect()
