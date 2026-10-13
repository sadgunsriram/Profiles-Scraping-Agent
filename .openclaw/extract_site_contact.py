import requests, re, sys, json
from bs4 import BeautifulSoup

headers={"user-agent":"Mozilla/5.0"}
for url in sys.argv[1:]:
    try:
        html=requests.get(url,headers=headers,timeout=25).text
        # Try JSON-LD first
        name=telephone=email=''
        street=locality=region=postal=''
        for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S|re.I):
            txt=m.group(1).strip()
            try:
                data=json.loads(txt)
            except Exception:
                continue
            objs=data if isinstance(data,list) else [data]
            for obj in objs:
                if not isinstance(obj,dict):
                    continue
                if not name and obj.get('name'):
                    name=obj.get('name')
                if not telephone and obj.get('telephone'):
                    telephone=obj.get('telephone')
                if not email and obj.get('email'):
                    email=obj.get('email')
                addr=obj.get('address')
                if isinstance(addr,dict):
                    street=street or addr.get('streetAddress','')
                    locality=locality or addr.get('addressLocality','')
                    region=region or addr.get('addressRegion','')
                    postal=postal or addr.get('postalCode','')
        if not telephone:
            m=re.search(r'telephone"\s*:\s*"([^"]+)"', html)
            if m: telephone=m.group(1)
        if not email:
            m=re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html)
            if m: email=m.group(0)
        print(url)
        print('NAME=',name)
        print('PHONE=',telephone)
        print('EMAIL=',email)
        print('ADDR=',', '.join([p for p in [street, locality, region, postal] if p]))
        print('---')
    except Exception as e:
        print(url)
        print('ERR=',e)
        print('---')
