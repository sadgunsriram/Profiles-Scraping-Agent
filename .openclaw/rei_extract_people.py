import re, requests, sys, time
from bs4 import BeautifulSoup
headers={"user-agent":"Mozilla/5.0"}
list_url=sys.argv[1]
limit=int(sys.argv[2]) if len(sys.argv)>2 else 12
html=requests.get(list_url,headers=headers,timeout=20).text
soup=BeautifulSoup(html,'html.parser')
links=[]
for a in soup.find_all('a',href=True):
    href=a['href']
    if '/profile/' in href and href.startswith('https://www.realestateindia.com/profile/') and '#review' not in href and href not in links:
        links.append(href)
for href in links[:limit]:
    page=requests.get(href,headers=headers,timeout=20).text
    m=re.search(r'<h4>(.*?)</h4>\s*<ul>\s*<li><i class="fa fa-user-circle-o"></i>\s*(.*?)</li>\s*<li>.*?</li>.*?<li><i class="fa fa-globe"></i>\s*<a href="([^"]+)"', page, re.S)
    if m:
        company=re.sub('<.*?>','',m.group(1)).strip()
        person=re.sub('<.*?>','',m.group(2)).strip()
        website=m.group(3).strip()
        if len(person.split())>=2:
            print(company+' | '+person+' | '+website+' | '+href)
    time.sleep(0.5)
