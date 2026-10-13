import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from skills.profile_scraper.scraper import save_profile, get_profiles

profiles = [
    {
        "full_name": "Prakruti",
        "email": "prakrutijoshi9@gmail.com",
        "contact_number": "84637896",
        "location": "BTM Layout Bengaluru, Karnataka - 560076",
        "domain": "Java",
        "skills": ["Java", "Spring Boot", "React.js", "Next.js", "MySQL", "Oracle DB"],
        "profile_url": "https://prakruti-20.github.io/PERSONAL_PORTFOLIO/",
        "source_platform": "github.io",
        "search_query": "Profile Scrape on java",
    },
    {
        "full_name": "Shubham Kulkarni",
        "email": "shubhamkulkarni17121999@gmail.com",
        "contact_number": "9579240446",
        "location": "Bhusawal, Maharashtra",
        "domain": "Java",
        "skills": ["Java", "Spring Boot", "REST APIs", "MySQL", "HTML", "CSS", "JavaScript", "AWS"],
        "profile_url": "https://shubham17121999.github.io/",
        "source_platform": "github.io",
        "search_query": "Profile Scrape on java",
    },
    {
        "full_name": "Madderla SaiKumar",
        "email": "saikumarmadderla@gmail.com",
        "contact_number": "8247891955",
        "location": "Hyderabad",
        "domain": "Java",
        "skills": ["Java", "SQL", "SpringBoot", "Django", "HTML", "CSS", "JavaScript", "React", "Cloud Computing"],
        "profile_url": "https://saikumar248.github.io/Portfolio/",
        "source_platform": "github.io",
        "search_query": "Profile Scrape on java",
    },
    {
        "full_name": "Banupriya B",
        "email": "pbanupriya427@gmail.com",
        "contact_number": None,
        "location": None,
        "domain": "Java",
        "skills": ["Java", "Python", "SQL", "REST APIs", "AI/ML"],
        "profile_url": "https://priya7676.github.io/",
        "source_platform": "github.io",
        "search_query": "Profile Scrape on java",
    },
    {
        "full_name": "Baramia Abdul-Salami",
        "email": "baramiaabdulsalami@gmail.com",
        "contact_number": "+255 713 637 542",
        "location": None,
        "domain": "Java",
        "skills": ["Java", "JavaScript", "PHP", "React", "Laravel"],
        "profile_url": "https://baramia056.github.io/My_Portfolio/",
        "source_platform": "github.io",
        "search_query": "Profile Scrape on java",
    },
]

for profile in profiles:
    print(save_profile(profile))

print("--- STORED PROFILES ---")
print(json.dumps(get_profiles(search_query="Profile Scrape on java", limit=10), indent=2))
