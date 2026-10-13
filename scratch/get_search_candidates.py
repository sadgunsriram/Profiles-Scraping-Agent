import sys
sys.path.insert(0, '.')
from skills.profile_scraper.scraper import search_all_sources

def get_candidates():
    results = search_all_sources('Network Engineer', num=12, mode='linkedin')
    print(f"Found {len(results)} candidate results:")
    for idx, r in enumerate(results):
        url = r.get('link') or r.get('profile_url') or ''
        title = r.get('title') or ''
        print(f"[{idx+1}] {title} -> {url}")

if __name__ == '__main__':
    get_candidates()
