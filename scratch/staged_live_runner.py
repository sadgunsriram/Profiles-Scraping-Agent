import os
import sys
import time
from loguru import logger

sys.path.insert(0, '.')

from skills.profile_scraper.config import load_config
from skills.profile_scraper.browser_session import BrowserSessionManager
from skills.profile_scraper.session_monitor import SessionMonitor
from skills.profile_scraper.page_readiness import navigate_to_profile, wait_for_profile_ready
from skills.profile_scraper.profile_extractor import extract_full_profile
from skills.profile_scraper.set1_identity import qualify_candidate_set1
from skills.profile_scraper.set2_clearance import qualify_candidate_set2
from skills.profile_scraper.set3_contact import qualify_candidate_set3
import skills.profile_scraper.excel_manager as excel_manager


def run_staged_batch(urls, query="Network Engineer", stage_name="Stage"):
    print(f"\n========================================================")
    print(f"   STARTING STAGED LIVE VALIDATION: {stage_name} ({len(urls)} profiles)")
    print(f"========================================================\n")
    
    config = load_config()
    monitor = SessionMonitor(config)
    manager = BrowserSessionManager(config)
    
    set1_passed = []
    set2_passed = []
    set3_passed = []
    rejected = {}
    
    page = manager.start_session()
    
    results_summary = []
    
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] Processing live profile: {url}")
        
        # Monitor session health
        try:
            monitor.check_page_health(page)
        except Exception as e:
            print(f"  Session monitor halted: {e}")
            break
            
        nav_ok = navigate_to_profile(page, url, timeout_ms=config.page_load_timeout)
        if not nav_ok:
            print(f"  Navigation failed for {url}")
            monitor.record_failure()
            continue
            
        is_ready, reason = wait_for_profile_ready(page, timeout_ms=config.element_timeout)
        if not is_ready:
            print(f"  Page not ready ({reason}) for {url}")
            monitor.record_failure()
            continue
            
        profile_data = extract_full_profile(page, url, enable_extension=config.enable_signalhire_extension)
        monitor.record_success()
        
        name = profile_data.get('full_name') or 'Unknown'
        loc = profile_data.get('location') or 'Unknown'
        headline = profile_data.get('headline') or 'Unknown'
        history = profile_data.get('experience_history') or []
        skills = profile_data.get('skills') or []
        email = profile_data.get('email') or 'Not Available'
        phone = profile_data.get('phone') or 'Not Available'
        
        print(f"  Name: {name}")
        print(f"  Location: {loc}")
        print(f"  Headline: {headline}")
        print(f"  Experience: {len(history)} records found")
        for j_idx, job in enumerate(history[:3], 1):
            print(f"    - {job.get('title')} at {job.get('company')} ({job.get('start_date')} - {job.get('end_date')})")
        if len(history) > 3:
            print(f"    ... and {len(history) - 3} more")
        print(f"  Skills: {len(skills)} found ({', '.join(skills[:3])})")
        print(f"  Contacts: Email={email}, Phone={phone}")
        
        # Qualification stages
        s1 = qualify_candidate_set1(profile_data, query=query)
        s1_status = "FAIL"
        s2_status = "FAIL"
        s3_status = "FAIL"
        
        if s1:
            s1_status = f"PASS ({s1.years_of_experience} yrs)"
            set1_passed.append(s1)
            
            is_s2, _, s2_reason, _, _ = qualify_candidate_set2(s1, profile_data, query=query)
            if is_s2:
                s2_status = "PASS"
                set2_passed.append(s1)
                
                is_s3, _, s3_reason, _, _, _, _ = qualify_candidate_set3(s1, profile_data)
                if is_s3:
                    s3_status = "PASS"
                    set3_passed.append(s1)
                else:
                    s3_status = f"FAIL ({s3_reason})"
            else:
                s2_status = f"FAIL ({s2_reason})"
        else:
            s1_status = f"FAIL ({profile_data.get('rejection_reason', 'Did not qualify')})"
            
        print(f"  Outcomes -> Set 1: {s1_status} | Set 2: {s2_status} | Set 3: {s3_status}")
        
        results_summary.append({
            "url": url,
            "name": name,
            "location": loc,
            "history_count": len(history),
            "set1": s1_status,
            "set2": s2_status,
            "set3": s3_status
        })
        
        time.sleep(2)  # Polite pacing between profile views
        
    manager.close()
    
    # Save to Excel
    excel_path = "skills/output/profiles.xlsx"
    if set1_passed:
        excel_manager.batch_save_profiles(set1_passed, set2_passed, set3_passed, rejected, excel_path)
        print(f"\nSaved {len(set1_passed)} Set 1, {len(set2_passed)} Set 2, {len(set3_passed)} Set 3 candidates to {excel_path}")
        
    print(f"\n========================================================")
    print(f"   SUMMARY FOR {stage_name}")
    print(f"========================================================")
    for r in results_summary:
        print(f"  * {r['name']} | {r['location']} | {r['history_count']} jobs | Set 1: {r['set1']}")
    print(f"========================================================\n")
    return results_summary

if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else "3"
    urls_all = [
        "https://www.linkedin.com/in/michael-owens27",
        "https://www.linkedin.com/in/farooqahmadmsc",
        "https://www.linkedin.com/in/curt-lunceford",
        "https://www.linkedin.com/in/paul-weinstein-177837a",
        "https://www.linkedin.com/in/jamesjaekim",
        "https://www.linkedin.com/in/stephen-j-janetzke",
        "https://www.linkedin.com/in/shahid-ali-472b4928",
        "https://www.linkedin.com/in/yanfilyurin",
        "https://www.linkedin.com/in/stan-mccombs-7484b9b3",
        "https://www.linkedin.com/in/georgeagibson"
    ]
    
    count = int(stage)
    run_staged_batch(urls_all[:count], query="Network Engineer", stage_name=f"Stage {count}")
