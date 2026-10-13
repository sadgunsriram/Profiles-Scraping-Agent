import sys
import os

# Ensure the workspace and skills folders are in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from skills.profile_scraper.set1_identity import (
    qualify_candidate_set1,
    is_full_name_valid,
    parse_date_to_month_offset,
    calculate_employment_months_union,
    is_role_relevant,
    calculate_relevant_experience_years,
    infer_experience_bracket,
    validate_us_location,
    is_c2c_candidate,
    extract_and_validate_contacts,
    is_c_level_role
)

# ===========================================================================
# 1. TEST NAME VALIDATION (Issue 7)
# ===========================================================================
print("--- 1. Testing Full Name Validation ---")
assert is_full_name_valid("Michael Scott") is True
assert is_full_name_valid("Michael D") is False
assert is_full_name_valid("M. Scott") is False
assert is_full_name_valid("M S") is False
assert is_full_name_valid("Michael") is False
print("Name validation tests passed!")

# ===========================================================================
# 2. TEST MONTH OFFSET PARSING & UNION DURATION (Issue 3)
# ===========================================================================
print("\n--- 2. Testing Month Offset & Union calculations ---")
offset_jan_2020 = parse_date_to_month_offset("Jan 2020")
offset_dec_2020 = parse_date_to_month_offset("Dec 2020", is_end_date=True)
print(f"Jan 2020 offset: {offset_jan_2020}, Dec 2020 offset: {offset_dec_2020}")
assert offset_dec_2020 - offset_jan_2020 == 11 # 12 months total

# Overlapping jobs union
history_overlapping = [
    {"title": "Dev", "start_date": "Jan 2020", "end_date": "Dec 2022"}, # 36 months (2020, 2021, 2022)
    {"title": "Sr Dev", "start_date": "Jan 2021", "end_date": "Dec 2023"} # 36 months (2021, 2022, 2023)
]
months_union = calculate_employment_months_union(history_overlapping)
# The union should cover Jan 2020 to Dec 2023 inclusive (48 months = 4.0 years)
total_years = round(len(months_union) / 12.0, 1)
print(f"Union months: {len(months_union)} months, Total Years: {total_years}")
assert total_years == 4.0
print("Month offset & union duration calculations passed!")

# ===========================================================================
# 3. TEST US LOCATION VALIDATION (Issue 2)
# ===========================================================================
print("\n--- 3. Testing US Location Validation ---")
p_us_ok = {"location": "San Francisco, CA", "bio_text": "Based in California, US"}
is_us, confidence, details = validate_us_location(p_us_ok)
print(f"US profile valid: {is_us}, Confidence: {confidence}, Details: {details}")
assert is_us is True

p_non_us = {"location": "Mumbai, India", "bio_text": "Software engineer in India"}
is_us_no, conf_no, details_no = validate_us_location(p_non_us)
print(f"Non-US profile valid: {is_us_no}, Confidence: {conf_no}, Details: {details_no}")
assert is_us_no is False
print("US location validation tests passed!")

# ===========================================================================
# 4. TEST C2C CANDIDATE DETECTOR (Issue 4)
# ===========================================================================
print("\n--- 4. Testing C2C Candidate Detector ---")
p_c2c = {"bio_text": "I am a bench sales consultant open for C2C positions."}
is_c2c, kw = is_c2c_candidate(p_c2c)
print(f"Is C2C: {is_c2c}, Matched Keyword: {kw}")
assert is_c2c is True

p_normal = {"bio_text": "Senior Python Developer looking for full-time roles."}
is_c2c_no, kw_no = is_c2c_candidate(p_normal)
print(f"Is C2C: {is_c2c_no}")
assert is_c2c_no is False
print("C2C candidate detector tests passed!")

# ===========================================================================
# 5. TEST EXPERIENCE BRACKET DETECTION (Issue 1)
# ===========================================================================
print("\n--- 5. Testing Experience Bracket Inference ---")
# Director
assert infer_experience_bracket(10, "Director of Engineering", ["Software Engineer"]) == "Director"
# Architect
assert infer_experience_bracket(9, "Solutions Architect", ["Lead Developer"]) == "Architect"
# Senior based on years
assert infer_experience_bracket(9, "Software Engineer", ["Developer"]) == "Senior"
# Mid-Level
assert infer_experience_bracket(5, "Software Engineer", []) == "Mid-Level"
# Entry level
assert infer_experience_bracket(0.5, "Junior Developer", []) == "Entry Level"
print("Experience bracket tests passed!")

# ===========================================================================
# 6. TEST CONTACT INFO VALIDATION (Issue 5)
# ===========================================================================
print("\n--- 6. Testing Contact Info Extraction & Validation ---")
p_contacts = {
    "email": "test@gmail.com",
    "mobile_phone": "206-555-0199",
    "bio_text": "Feel free to reach me at anotheremail@company.com or +1 415 555 2671"
}
email, phone = extract_and_validate_contacts(p_contacts)
print(f"Extracted email: {email}, Extracted phone: {phone}")
assert email == "test@gmail.com"
assert phone == "+12065550199"
print("Contact validation tests passed!")

# ===========================================================================
# 7. TEST C-LEVEL ROLE FILTERING
# ===========================================================================
print("\n--- 7. Testing C-Level Role Filtering ---")
assert is_c_level_role("Chief Technology Officer") is True
assert is_c_level_role("Vice President of Network Operations") is True
assert is_c_level_role("CTO") is True
assert is_c_level_role("CEO") is True
assert is_c_level_role("Director of Infrastructure") is True
assert is_c_level_role("Founder & Partner") is True
assert is_c_level_role("Senior Network Engineer") is False
assert is_c_level_role("NOC Operations Manager") is False
assert is_c_level_role("Technical Support Specialist") is False
print("C-level role filtering tests passed!")

print("\nAll unit tests passed successfully!")
