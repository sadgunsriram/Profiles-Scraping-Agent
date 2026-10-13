import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from skills.profile_scraper.scraper import save_profile, get_profiles

profiles = [
    {
        "full_name": "Venkatesh Tigalamaram",
        "email": "venkatesh60360@gmail.com",
        "contact_number": "+91-9346196626",
        "location": "Near Masid (Sarai), Patancheru, Hyderabad, Telangana, 502319",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent"],
        "profile_url": "https://www.realestateindia.com/profile/v26-acres-in-patancheru-hyderabad-3101207/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Jai Sri Krishna",
        "email": "maksinfrahyd@gmail.com",
        "contact_number": "+91-9705034622",
        "location": "201, KS Residency, Attapur, Hyderabad, Telangana, 500048",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent", "Property Consultant"],
        "profile_url": "https://www.realestateindia.com/profile/maks-infra-in-attapur-hyderabad-3688717/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Bandla Krishna",
        "email": "kribandla@gmail.com",
        "contact_number": "+91-9052000074",
        "location": "1-106, Main Road, Ahmedguda Keesara, ECIL, Hyderabad, Telangana",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent", "Real Estate Consultant"],
        "profile_url": "https://www.realestateindia.com/profile/bandla-properties-in-ecil-hyderabad-3105148/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Venu Gopall",
        "email": "svenn@ssbrealestates.in",
        "contact_number": "+91-8309374151",
        "location": "Plot No. 261, Prashanthnagar, Street No. 1 Lane No. 6 Extension, Bandlaguda Jagir, Gandipet, Hyderabad, Telangana, 500086",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent"],
        "profile_url": "https://www.realestateindia.com/profile/ssb-sri-sai-balaji-real-estate-constructions-in-gandipet-hyderabad-123385/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Srinivas Reddy G",
        "email": "forlandsandwalls@gmail.com",
        "contact_number": "+91-9059112619",
        "location": "Flat No 405, Vijay Laxmi Arcade, Spring Field Colony, Jeeimetla, Qutubullapur Mndl, Medchal-Malkajgiri, Kompally, Hyderabad, Telangana, 500067",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent"],
        "profile_url": "https://www.realestateindia.com/profile/lands-and-walls-in-kompally-hyderabad-2538893/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Sumit Das",
        "email": "vistacoreproperties@gmail.com",
        "contact_number": "+91-8919581066",
        "location": "C507, Sai Raghav Enclave, Chanda Nagar, Hyderabad, Telangana, 500049",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent"],
        "profile_url": "https://www.realestateindia.com/profile/vistacore-properties-in-chanda-nagar-hyderabad-3401516/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Swamy Reddy Javidi",
        "email": "sadgunaproperties@gmail.com",
        "contact_number": "+91-9030057488",
        "location": "Sadguna Properties, 2nd Branch, Gachibowli, Hyderabad, Telangana, 500032",
        "domain": "Real Estate",
        "skills": ["Real Estate Consultancy", "Building Construction"],
        "profile_url": "https://www.realestateindia.com/profile/sadguna-properties-in-gachibowli-hyderabad-2708023/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Pratap Sinha",
        "email": "prathaap.k@gmail.com",
        "contact_number": "+91-7729822999",
        "location": "10th Floor, Tharamandal Complex, Saifabad, Hyderabad, Telangana, 500004",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent"],
        "profile_url": "https://www.realestateindia.com/profile/jp-realty-in-saifabad-hyderabad-2215018/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
    {
        "full_name": "Rafee Shaik",
        "email": "ramf.shaik@gmail.com",
        "contact_number": "+91-9949385538",
        "location": "144/3RT, Vijaya Nagar Colony, Hyderabad, Telangana, 500057",
        "domain": "Real Estate",
        "skills": ["Real Estate Agent"],
        "profile_url": "https://www.realestateindia.com/profile/property-shoppy-in-vijaya-nagar-colony-mehdipatnam-hyderabad-2241077/",
        "source_platform": "realestateindia+website",
        "search_query": "real estate agents hyderabad contact",
    },
]

for profile in profiles:
    print(save_profile(profile))

print("--- STORED PROFILES ---")
print(json.dumps(get_profiles(search_query="real estate agents hyderabad contact", limit=20), indent=2))
