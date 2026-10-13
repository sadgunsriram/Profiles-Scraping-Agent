import sys
import os

# Ensure the workspace and skills folders are in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from skills.profile_scraper.set1_identity import qualify_candidate_set1
from skills.profile_scraper.role_expansion import classify_and_expand_query

# Pre-defined mock profiles to test the end-to-end pipeline under search API rate limits
MOCK_PROFILES = [
    {
        "full_name": "John Doe",
        "location": "New York, NY",
        "email": "johndoe@gmail.com",
        "mobile_phone": "+1 206 555 0100",
        "bio_text": "Experienced Python Engineer. Currently working at TechCorp in USA.",
        "skills": ["Python", "Django", "SQL"],
        "experience_history": [
            {"title": "Python Developer", "company": "TechCorp", "start_date": "Jan 2018", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/johndoe",
        "github_url": "https://github.com/johndoe"
    },
    {
        "full_name": "Nicolas Bonnet",
        "location": "Paris, France",
        "email": "nicolas@company.fr",
        "mobile_phone": "+33 1 42 27 78 90",
        "bio_text": "Java engineer based in France.",
        "skills": ["Java", "Spring"],
        "experience_history": [
            {"title": "Java Engineer", "company": "SpringCorp", "start_date": "Jan 2015", "end_date": "Dec 2022"}
        ],
        "profile_url": "https://linkedin.com/in/nicolasbonnet",
        "github_url": "https://github.com/nicolasbonnet"
    },
    {
        "full_name": "Bench Mark",
        "location": "Dallas, TX",
        "email": "benchmark@staffing.com",
        "mobile_phone": "+1 415 555 9876",
        "bio_text": "I am a bench sales recruiter offering C2C resource consulting.",
        "skills": ["Recruiting"],
        "experience_history": [
            {"title": "Bench Sales", "company": "Staffing Co", "start_date": "Jan 2020", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/benchmark",
        "github_url": "https://github.com/benchmark"
    },
    {
        "full_name": "Michael D",
        "location": "Austin, TX",
        "email": "michaeld@gmail.com",
        "mobile_phone": "+1 512 555 4321",
        "bio_text": "Cloud architect since 2015.",
        "skills": ["AWS", "Terraform"],
        "experience_history": [
            {"title": "Cloud Architect", "company": "Cloudy", "start_date": "Jan 2015", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/michaeld",
        "github_url": "https://github.com/michaeld"
    },
    {
        "full_name": "Sarah Connor",
        "location": "Los Angeles, CA",
        "email": "invalid_email_format",
        "mobile_phone": "+1 213 555 9988",
        "bio_text": "DevOps Engineer.",
        "skills": ["Docker", "Kubernetes"],
        "experience_history": [
            {"title": "DevOps Engineer", "company": "Cyberdyne", "start_date": "Jan 2018", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/sarahconnor",
        "github_url": "https://github.com/sarahconnor"
    },
    {
        "full_name": "John Connor",
        "location": "Los Angeles, CA",
        "email": "johnconnor@gmail.com",
        "mobile_phone": "",
        "bio_text": "System Administrator.",
        "skills": ["Linux", "Bash"],
        "experience_history": [
            {"title": "SysAdmin", "company": "Resistance", "start_date": "Jan 2021", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/johnconnor",
        "github_url": "https://github.com/johnconnor"
    },
    {
        "full_name": "John Doe",  # Duplicate of first candidate
        "location": "New York, NY",
        "email": "johndoe@gmail.com",
        "mobile_phone": "+1 206 555 0100",
        "bio_text": "Experienced Python Engineer.",
        "skills": ["Python"],
        "experience_history": [
            {"title": "Python Developer", "company": "TechCorp", "start_date": "Jan 2018", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/johndoe",
        "github_url": "https://github.com/johndoe"
    },
    {
        "full_name": "Zero Work",
        "location": "Seattle, WA",
        "email": "zerowork@gmail.com",
        "mobile_phone": "+1 206 555 3322",
        "bio_text": "Interested in tech.",
        "skills": ["HTML"],
        "experience_history": [],
        "profile_url": "https://linkedin.com/in/zerowork",
        "github_url": "https://github.com/zerowork"
    },
    {
        "full_name": "No GitHub Link",
        "location": "San Francisco, CA",
        "email": "nogithub@gmail.com",
        "mobile_phone": "+1 206 555 9999",
        "bio_text": "Python Dev.",
        "skills": ["Python"],
        "experience_history": [
            {"title": "Developer", "company": "NoGit", "start_date": "Jan 2020", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/nogithub",
        "github_url": ""  # Missing GitHub URL check
    },
    {
        "full_name": "Chief Technical Executive",
        "location": "Dallas, TX",
        "email": "chief@company.com",
        "mobile_phone": "+1 214 555 1234",
        "bio_text": "CTO and Vice President of Global Architecture.",
        "skills": ["Executive leadership"],
        "experience_history": [
            {"title": "Chief Technology Officer", "company": "Global Corp", "start_date": "Jan 2012", "end_date": "Present"}
        ],
        "profile_url": "https://linkedin.com/in/chiefcto",
        "github_url": "https://github.com/chiefcto"
    }
]

def main():
    print("Running batch validation runner...")
    print("=" * 60)
    
    total_profiles = len(MOCK_PROFILES)
    profiles_parsed = 0
    profiles_rejected = 0
    us_profiles = 0
    non_us_profiles = 0
    exp_calculated = 0
    names_extracted = 0
    emails_found = 0
    phones_found = 0
    c2c_removed = 0
    duplicates_removed = 0
    final_exported = 0
    total_confidence_score = 0
    existing_keys = set()
    set1_passed = []
    set2_passed = []
    set3_passed = []
    rejected_candidates = {
        "Set1": [],
        "Set2": [],
        "Set3": []
    }
    
    import skills.profile_scraper.set2_clearance as set2_clearance
    import skills.profile_scraper.set3_contact as set3_contact
    import skills.profile_scraper.excel_manager as excel_manager
    from skills.profile_scraper.set1_identity import qualify_candidate_set1

    for idx, profile in enumerate(MOCK_PROFILES, 1):
        name = profile.get("full_name") or "Unknown"
        profiles_parsed += 1
        
        # Check duplicate
        github_url = profile.get("github_url", "").strip().lower()
        linkedin_url = (profile.get("linkedin_url") or profile.get("profile_url") or "").strip().lower()
        email = profile.get("email", "").strip().lower()
        
        is_dup = False
        if github_url and github_url in existing_keys: is_dup = True
        if linkedin_url and linkedin_url in existing_keys: is_dup = True
        if email and email in existing_keys: is_dup = True
        
        if is_dup:
            print(f"Profile {idx}: {name} -> Rejected: Duplicate Candidate")
            duplicates_removed += 1
            profiles_rejected += 1
            continue
            
        # Step 10: Set 1 Identity & Experience Qualification
        candidate = qualify_candidate_set1(profile, "Python Developer")
        if not candidate:
            profiles_rejected += 1
            rejected_candidates["Set1"].append(profile)
            continue
            
        set1_passed.append(candidate)
        
        # Step 11: Set 2 Visa & US Clearance Qualification
        is_set2_ok, reject_stage, reject_reason, visa_sponsorship_needed, security_clearance = set2_clearance.qualify_candidate_set2(candidate, profile, "Python Developer")
        if not is_set2_ok:
            profiles_rejected += 1
            profile['rejection_stage'] = reject_stage
            profile['rejection_reason'] = reject_reason
            rejected_candidates["Set2"].append(profile)
            if reject_stage == "Location Validation":
                non_us_profiles += 1
            continue
            
        # Update candidate object with Set 2 findings
        candidate.visa_sponsorship_needed = visa_sponsorship_needed
        candidate.security_clearance = security_clearance
        candidate.current_pipeline_stage = "Set 2 Passed"
        
        set2_passed.append(candidate)
        
        # Step 12: Set 3 Contacts & Email Verification
        is_set3_ok, reject_stage, reject_reason, validated_email, formatted_phone = set3_contact.qualify_candidate_set3(candidate, profile)
        if not is_set3_ok:
            profiles_rejected += 1
            profile['rejection_stage'] = reject_stage
            profile['rejection_reason'] = reject_reason
            rejected_candidates["Set3"].append(profile)
            continue
            
        # Update candidate object with Set 3 findings
        candidate.email = validated_email
        candidate.phone = formatted_phone
        candidate.current_pipeline_stage = "Qualified"
        
        set3_passed.append(candidate)
            
        # Update metrics for passed candidate
        final_exported += 1
        if candidate.email:
            existing_keys.add(candidate.email.strip().lower())
        existing_keys.add(candidate.linkedin_url.strip().lower())
        
        # Track positive attributes
        us_profiles += 1
        if candidate.years_of_experience is not None:
            exp_calculated += 1
        if candidate.full_name:
            names_extracted += 1
        if candidate.email:
            emails_found += 1
        if candidate.phone:
            phones_found += 1
            
        conf_map = {"High": 3.0, "Medium": 2.0, "Low": 1.0}
        total_confidence_score += conf_map.get(candidate.confidence_score, 1.0)
        
    avg_conf = round(total_confidence_score / max(1, final_exported), 2)
    
    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    print(f"Total Profiles Found        : {total_profiles}")
    print(f"Profiles Parsed             : {profiles_parsed}")
    print(f"Profiles Rejected           : {profiles_rejected}")
    print(f"US Profiles                 : {us_profiles}")
    print(f"Non-US Profiles Rejected    : {non_us_profiles}")
    print(f"Experience Calculated       : {exp_calculated}")
    print(f"Full Names Extracted        : {names_extracted}")
    print(f"Emails Found                : {emails_found}")
    print(f"Phones Found                : {phones_found}")
    print(f"C2C Profiles Removed        : {c2c_removed}")
    print(f"Duplicate Profiles Removed  : {duplicates_removed}")
    print(f"Final Profiles Exported     : {final_exported}")
    print(f"Average Confidence Score    : {avg_conf}")
    print("=" * 60)

    # Save validation candidates to Excel using progressive V2 structure
    excel_path = os.getenv("EXCEL_OUTPUT_PATH", "skills/output/profiles.xlsx")
    excel_manager.batch_save_profiles(set1_passed, set2_passed, set3_passed, rejected_candidates, excel_path)

if __name__ == "__main__":
    # Test query expansions
    print("\n--- Testing Technology-to-Role Expansion Engine ---")
    
    # 1. Network Engineers (Domain/Role)
    net_exp = classify_and_expand_query("Network Engineers")
    print(f"Query: 'Network Engineers' -> Classification: {net_exp['classification']}, Category: {net_exp['category']}, Constraint: {net_exp['tech_constraint']}")
    assert net_exp["classification"] == "DOMAIN"
    assert net_exp["tech_constraint"] is None
    assert "Junior Network Engineer" in net_exp["expanded_list"]
    assert "Network Operations Manager" in net_exp["expanded_list"]
    
    # 2. Snowflake (Seed Tech)
    sf_exp = classify_and_expand_query("Snowflake")
    print(f"Query: 'Snowflake' -> Classification: {sf_exp['classification']}, Category: {sf_exp['category']}, Constraint: {sf_exp['tech_constraint']}")
    assert sf_exp["classification"] == "TECHNOLOGY"
    assert sf_exp["tech_constraint"] == "Snowflake"
    assert "Snowflake Data Engineer" in sf_exp["expanded_list"]
    
    # 3. Kafka (Unknown Data Tech)
    kafka_exp = classify_and_expand_query("Apache Kafka")
    print(f"Query: 'Apache Kafka' -> Classification: {kafka_exp['classification']}, Category: {kafka_exp['category']}, Constraint: {kafka_exp['tech_constraint']}")
    assert kafka_exp["classification"] == "TECHNOLOGY"
    assert kafka_exp["category"] == "DATA / DATABASE / BIG DATA"
    assert "Apache Kafka Data Engineer" in kafka_exp["expanded_list"]
    
    # 4. Terraform (Unknown Cloud Tech)
    tf_exp = classify_and_expand_query("Terraform")
    print(f"Query: 'Terraform' -> Classification: {tf_exp['classification']}, Category: {tf_exp['category']}, Constraint: {tf_exp['tech_constraint']}")
    assert tf_exp["classification"] == "TECHNOLOGY"
    assert tf_exp["category"] == "CLOUD / DEVOPS / INFRASTRUCTURE"
    assert "Terraform DevOps Engineer" in tf_exp["expanded_list"]
    
    # 5. Kubernetes (Unknown Cloud Tech)
    k8s_exp = classify_and_expand_query("Kubernetes")
    print(f"Query: 'Kubernetes' -> Classification: {k8s_exp['classification']}, Category: {k8s_exp['category']}, Constraint: {k8s_exp['tech_constraint']}")
    assert k8s_exp["classification"] == "TECHNOLOGY"
    assert k8s_exp["category"] == "CLOUD / DEVOPS / INFRASTRUCTURE"
    
    print("All role expansion tests passed successfully!\n")
    
    main()
