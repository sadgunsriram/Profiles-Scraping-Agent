import re
import os
import json
import httpx
from loguru import logger

# Static Seed Maps
SEED_MAPS = {
    "network engineering": {
        "category": "NETWORK ENGINEERING",
        "classification": "DOMAIN",
        "tier1": [
            "Network Engineer", "Junior Network Engineer", "Associate Network Engineer",
            "Mid-Level Network Engineer", "Senior Network Engineer", "Lead Network Engineer",
            "Principal Network Engineer", "Staff Network Engineer", "Network Analyst",
            "Network Administrator", "Senior Network Administrator", "Systems and Network Engineer",
            "Network Systems Engineer"
        ],
        "tier2": [
            "Network Security Engineer", "Firewall Engineer", "Perimeter Security Engineer",
            "VPN Engineer", "Secure Access Engineer", "Zero Trust Network Engineer",
            "SASE Engineer", "Infrastructure Security Engineer",
            "Network Automation Engineer", "Python Network Automation Engineer",
            "Infrastructure Automation Engineer", "NetDevOps Engineer", "Network DevOps Engineer",
            "Cloud Network Engineer", "Cloud Infrastructure Engineer", "AWS Network Engineer",
            "Azure Network Engineer", "Google Cloud Network Engineer", "Hybrid Cloud Network Engineer",
            "Data Center Network Engineer", "Data Center Infrastructure Engineer",
            "Network Architect", "Enterprise Network Architect", "Network Design Engineer",
            "Network Implementation Engineer", "Network Deployment Engineer", "Network Integration Engineer",
            "IP Network Engineer", "Routing and Switching Engineer", "Cisco Network Engineer",
            "Cisco Infrastructure Engineer", "Cisco Collaboration Engineer",
            "Unified Communications Engineer", "VoIP Engineer", "Voice Network Engineer",
            "Telecom Network Engineer", "Telecommunications Engineer", "Carrier Network Engineer",
            "ISP Network Engineer", "Optical Network Engineer", "Fiber Network Engineer",
            "MPLS Engineer", "BGP Engineer", "DNS Engineer", "DHCP Engineer",
            "Load Balancing Engineer", "F5 Network Engineer", "Palo Alto Network Engineer",
            "Fortinet Network Engineer", "Juniper Network Engineer", "Arista Network Engineer",
            "Extreme Networks Engineer", "Wireless Network Engineer", "Wi-Fi Engineer",
            "WLAN Engineer", "SD-WAN Engineer", "Software-Defined Networking (SDN) Engineer"
        ],
        "tier3": [
            "Network Operations Engineer", "Network Operations Center (NOC) Engineer",
            "NOC Technician", "Network Technician", "Network Infrastructure Engineer",
            "Infrastructure Engineer", "Enterprise Network Engineer", "Core Network Engineer",
            "LAN Engineer", "WAN Engineer", "IT Infrastructure Engineer", "Infrastructure Operations Engineer",
            "Network Performance Engineer", "Network Monitoring Engineer", "Network Capacity Engineer",
            "Network Optimization Engineer", "Network Planning Engineer", "Network Validation Engineer",
            "Network Test Engineer", "Network Consulting Engineer", "Professional Services Network Engineer",
            "Customer Network Engineer", "Field Network Engineer", "Resident Network Engineer",
            "Network Project Engineer", "Network Migration Engineer", "Network Services Engineer",
            "Broadcast Network Engineer", "Media Network Engineer", "Industrial Network Engineer",
            "Operational Technology (OT) Network Engineer", "Manufacturing Network Engineer",
            "SCADA Network Engineer", "IIoT Network Engineer", "Defense Network Engineer",
            "Government Network Engineer", "Security Clearance Network Engineer", "Mission Network Engineer",
            "High-Performance Computing (HPC) Network Engineer", "Edge Network Engineer",
            "Edge Infrastructure Engineer", "Internet Backbone Engineer", "Backbone Network Engineer",
            "Network Engineering Manager", "Infrastructure Manager (Networking)", "Network Operations Manager"
        ]
    },
    "snowflake": {
        "category": "DATA PLATFORM / DATA WAREHOUSING",
        "classification": "TECHNOLOGY",
        "tier1": [
            "Snowflake Engineer", "Snowflake Developer", "Snowflake Data Engineer", "Snowflake Consultant"
        ],
        "tier2": [
            "Data Engineer", "Senior Data Engineer", "Cloud Data Engineer", "Data Platform Engineer",
            "Data Warehouse Engineer", "Data Warehouse Developer", "Analytics Engineer", "Data Architect",
            "Cloud Data Architect", "ETL Engineer", "ETL Developer", "Data Integration Engineer", "Data Migration Engineer"
        ],
        "tier3": [
            "BI Engineer", "Business Intelligence Engineer", "Data Analyst", "Senior Data Analyst",
            "Data Platform Consultant"
        ]
    },
    "cybersecurity": {
        "category": "SECURITY DOMAIN",
        "classification": "DOMAIN",
        "tier1": [
            "Cybersecurity Engineer", "Cybersecurity Analyst", "Information Security Analyst",
            "Information Security Engineer", "Security Engineer", "Security Analyst"
        ],
        "tier2": [
            "SOC Analyst", "Security Operations Analyst", "Security Operations Engineer", "Cloud Security Engineer",
            "Network Security Engineer", "Application Security Engineer", "Product Security Engineer",
            "DevSecOps Engineer", "Security Automation Engineer", "Penetration Tester", "Penetration Testing Engineer",
            "Vulnerability Analyst", "Vulnerability Management Engineer", "Incident Response Analyst",
            "Incident Response Engineer", "Threat Intelligence Analyst", "Threat Hunter", "Digital Forensics Analyst",
            "IAM Engineer", "Identity and Access Management Engineer", "Security Architect"
        ],
        "tier3": [
            "GRC Analyst", "Security Compliance Analyst", "Security Consultant", "Security Operations Engineer",
            "Security Monitoring Engineer", "Security Detection Engineer", "Security Engineering Analyst"
        ]
    },
    "sap": {
        "category": "ENTERPRISE SOFTWARE / ERP",
        "classification": "TECHNOLOGY",
        "tier1": [
            "SAP Consultant", "SAP Technical Consultant", "SAP Functional Consultant", "SAP Developer",
            "SAP Engineer", "SAP Architect", "SAP Solution Architect"
        ],
        "tier2": [
            "SAP Application Consultant", "SAP Integration Consultant", "SAP Basis Consultant",
            "SAP Security Consultant", "SAP Cloud Consultant", "SAP HANA Consultant", "SAP HANA Developer",
            "SAP S/4HANA Consultant", "SAP ABAP Developer", "SAP Fiori Developer", "SAP UI5 Developer",
            "SAP BW Consultant", "SAP Analytics Consultant", "SAP SuccessFactors Consultant",
            "SAP Ariba Consultant", "SAP Supply Chain Consultant", "SAP Finance Consultant",
            "SAP MM Consultant", "SAP SD Consultant", "SAP PP Consultant", "SAP EWM Consultant",
            "SAP CRM Consultant", "SAP Technical Architect"
        ],
        "tier3": [
            "SAP Data Engineer", "SAP Data Analyst", "SAP Administrator", "SAP Basis Administrator",
            "SAP Integration Engineer"
        ]
    },
    "cloud": {
        "category": "CLOUD DOMAIN",
        "classification": "DOMAIN",
        "tier1": [
            "Cloud Engineer", "Cloud Infrastructure Engineer", "Cloud Platform Engineer", "Cloud Architect",
            "Cloud Solutions Architect", "Cloud Infrastructure Architect"
        ],
        "tier2": [
            "Cloud DevOps Engineer", "Cloud DevSecOps Engineer", "Cloud Security Engineer", "Cloud Network Engineer",
            "Cloud Operations Engineer", "Cloud Systems Engineer", "Cloud Automation Engineer",
            "Cloud Reliability Engineer", "Site Reliability Engineer", "Cloud Data Engineer", "Cloud Migration Engineer",
            "Cloud Solutions Engineer"
        ],
        "tier3": [
            "Cloud Consultant", "Cloud Infrastructure Consultant", "Platform Engineer", "AWS Cloud Engineer",
            "Azure Cloud Engineer", "Google Cloud Engineer", "AWS Solutions Architect", "Azure Solutions Architect",
            "Google Cloud Architect"
        ]
    },
    "databricks": {
        "category": "DATA PLATFORM / ANALYTICS",
        "classification": "TECHNOLOGY",
        "tier1": [
            "Databricks Engineer", "Databricks Developer", "Databricks Data Engineer", "Databricks Consultant"
        ],
        "tier2": [
            "Data Engineer", "Senior Data Engineer", "Big Data Engineer", "Big Data Developer",
            "Data Platform Engineer", "Cloud Data Engineer", "Data Architect", "Data Platform Architect",
            "Analytics Engineer", "ETL Engineer", "Data Integration Engineer", "Apache Spark Engineer",
            "Spark Developer"
        ],
        "tier3": [
            "Machine Learning Engineer", "ML Engineer", "Data Scientist", "MLOps Engineer", "Data Platform Consultant"
        ]
    },
    "artificial intelligence": {
        "category": "AI DOMAIN",
        "classification": "DOMAIN",
        "tier1": [
            "AI Engineer", "Artificial Intelligence Engineer", "AI Software Engineer", "AI Developer",
            "AI Research Engineer", "AI Research Scientist"
        ],
        "tier2": [
            "Machine Learning Engineer", "Machine Learning Scientist", "Applied Scientist", "Applied AI Engineer",
            "Generative AI Engineer", "GenAI Engineer", "AI/ML Engineer", "ML Engineer", "Deep Learning Engineer",
            "NLP Engineer", "Computer Vision Engineer", "AI Solutions Architect", "AI Platform Engineer",
            "AI Infrastructure Engineer", "MLOps Engineer", "LLM Engineer", "LLM Application Engineer"
        ],
        "tier3": [
            "AI Consultant", "AI Product Engineer", "AI Application Engineer", "AI Automation Engineer"
        ]
    },
    "machine learning": {
        "category": "AI / ML DOMAIN",
        "classification": "DOMAIN",
        "tier1": [
            "Machine Learning Engineer", "ML Engineer", "Senior Machine Learning Engineer",
            "Machine Learning Scientist", "ML Scientist"
        ],
        "tier2": [
            "Applied Scientist", "Research Scientist", "Research Engineer", "AI/ML Engineer",
            "Data Scientist", "Applied Machine Learning Engineer", "Deep Learning Engineer",
            "NLP Engineer", "Computer Vision Engineer", "MLOps Engineer", "ML Platform Engineer",
            "ML Infrastructure Engineer", "Machine Learning Architect", "AI Engineer", "AI Research Engineer"
        ],
        "tier3": [
            "Machine Learning Consultant"
        ]
    },
    "data science": {
        "category": "DATA SCIENCE DOMAIN",
        "classification": "DOMAIN",
        "tier1": [
            "Data Scientist", "Senior Data Scientist", "Applied Data Scientist", "Research Data Scientist",
            "Machine Learning Scientist"
        ],
        "tier2": [
            "Machine Learning Engineer", "Applied Scientist", "Decision Scientist", "Product Data Scientist",
            "Marketing Data Scientist", "Business Data Scientist", "Quantitative Analyst", "Data Science Engineer",
            "AI/ML Scientist", "Research Scientist", "NLP Data Scientist", "Computer Vision Scientist",
            "Predictive Analytics Scientist"
        ],
        "tier3": [
            "Data Science Consultant", "Data Science Manager"
        ]
    },
    "data engineering": {
        "category": "DATA ENGINEERING DOMAIN",
        "classification": "DOMAIN",
        "tier1": [
            "Data Engineer", "Senior Data Engineer", "Cloud Data Engineer", "Big Data Engineer",
            "Data Platform Engineer"
        ],
        "tier2": [
            "Data Infrastructure Engineer", "Data Pipeline Engineer", "Data Warehouse Engineer",
            "Data Warehouse Developer", "ETL Engineer", "ETL Developer", "Data Integration Engineer",
            "Data Migration Engineer", "Analytics Engineer", "Streaming Data Engineer",
            "Real-Time Data Engineer", "Data Architect", "Cloud Data Architect", "Data Platform Architect"
        ],
        "tier3": [
            "Database Engineer", "Database Developer", "BI Engineer", "Data Operations Engineer",
            "Data Engineering Consultant"
        ]
    },
    "iam": {
        "category": "IDENTITY & SECURITY DOMAIN",
        "classification": "DOMAIN",
        "tier1": [
            "IAM Engineer", "Identity and Access Management Engineer", "Identity Engineer",
            "Identity Management Engineer", "Access Management Engineer", "Identity Security Engineer",
            "Identity Architect", "IAM Architect", "Identity and Access Management Architect"
        ],
        "tier2": [
            "IAM Analyst", "Identity Analyst", "IAM Administrator", "Identity Administrator",
            "Privileged Access Management Engineer", "PAM Engineer", "IGA Engineer", "Identity Governance Engineer",
            "Identity Governance and Administration Engineer", "Access Governance Engineer", "Authentication Engineer",
            "Authorization Engineer", "SSO Engineer", "Single Sign-On Engineer", "Directory Services Engineer",
            "Active Directory Engineer", "Azure AD Engineer", "Entra ID Engineer", "Okta Engineer"
        ],
        "tier3": [
            "Cybersecurity Engineer", "Cloud Security Engineer", "Security Engineer",
            "Identity Security Consultant", "IAM Consultant"
        ]
    }
}

# Suffix rules mapping a query to JOB_ROLE or DOMAIN
ROLE_SUFFIXES = [
    "engineer", "engineers", "developer", "developers", "analyst", "analysts",
    "administrator", "administrators", "architect", "architects", "consultant",
    "consultants", "specialist", "specialists", "technician", "technicians",
    "manager", "managers", "operations", "support", "tester", "testers"
]

DOMAIN_KEYWORDS = [
    "networking", "cybersecurity", "cyber security", "information security",
    "infosec", "cloud engineering", "cloud computing", "data science",
    "data engineering", "artificial intelligence", "ai", "machine learning", "ml",
    "identity management", "access management"
]

def expand_query_via_ollama(query: str) -> dict:
    """Queries local Ollama instance to dynamically expand query into job tiers."""
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    
    prompt = f"""You are an expert recruiter assistant.
Given the search query: "{query}"
Classify the query category, classification (DOMAIN, JOB_ROLE, or TECHNOLOGY), and expand it into related job titles.
Respond ONLY with a valid JSON object matching the schema below. Do not include markdown code block formatting, explanations, or leading/trailing text.

Schema:
{{
  "classification": "DOMAIN",
  "category": "Technology domain category",
  "tier1": ["list of 5 core roles"],
  "tier2": ["list of 10 specialized roles"],
  "tier3": ["list of 10 adjacent/junior/manager roles"]
}}"""

    try:
        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0
                }
            },
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "60.0"))
        )
        if resp.status_code == 200:
            res_json = resp.json()
            response_text = res_json.get("response", "").strip()
            
            # Clean up potential markdown formatting
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()
                
            data = json.loads(response_text)
            
            # Extract lists
            t1 = data.get("tier1", [])
            t2 = data.get("tier2", [])
            t3 = data.get("tier3", [])
            
            # Ensure they are lists of strings
            t1 = [str(x) for x in t1]
            t2 = [str(x) for x in t2]
            t3 = [str(x) for x in t3]
            
            # Tech constraint determination
            tech_constraint = query
            
            logger.info(f"Ollama successfully expanded '{query}' into {len(t1)+len(t2)+len(t3)} roles.")
            return {
                "query": query,
                "classification": data.get("classification", "DOMAIN"),
                "category": data.get("category", "GENERAL TECHNOLOGY"),
                "tech_constraint": tech_constraint,
                "tiers": {"tier1": t1, "tier2": t2, "tier3": t3},
                "expanded_list": t1 + t2 + t3
            }
    except Exception as e:
        logger.warning(f"Ollama expansion failed: {e}. Falling back to default static heuristics.")
        
    return None

def classify_and_expand_query(query: str) -> dict:
    """
    Classifies the user input query and expands it into ranked professional roles.
    
    Returns a dictionary containing:
      - 'query': original query
      - 'classification': 'TECHNOLOGY', 'JOB_ROLE', or 'DOMAIN'
      - 'category': general ecosystem name
      - 'tech_constraint': technology name string that must be in the search query (or None)
      - 'tiers': {'tier1': [...], 'tier2': [...], 'tier3': [...]}
      - 'expanded_list': combined ranked titles
    """
    q_clean = query.strip()
    q_lower = q_clean.lower()
    
    # Strip clearance prefixes/suffixes to find core job role domain
    clearance_words = [
        r'\bcleared\b', r'\bsecurity\s+cleared\b', r'\bts/sci\s+cleared\b',
        r'\bsecret\s+cleared\b', r'\bactive\s+clearance\b', r'\bsecurity\s+clearance\b',
        r'\bts/sci\b', r'\btop\s+secret\b', r'\bsecret\b', r'\bpublic\s+trust\b'
    ]
    core_q_lower = q_lower
    for pat in clearance_words:
        core_q_lower = re.sub(pat, '', core_q_lower, flags=re.IGNORECASE).strip()
    core_q_lower = re.sub(r'\s+', ' ', core_q_lower).strip()

    # 0. Check local Ollama dynamic expansion
    if os.getenv("USE_OLLAMA", "false").lower() == "true":
        ollama_result = expand_query_via_ollama(core_q_lower or q_clean)
        if ollama_result:
            return ollama_result
    
    # 1. Check direct matches in seed list
    matched_key = None
    target_terms = [core_q_lower, q_lower] if core_q_lower != q_lower else [q_lower]
    
    for term in target_terms:
        if matched_key:
            break
        for key in SEED_MAPS:
            if term == key or term == key.replace(" engineering", "") or term == key.replace(" engineer", "") or term + "s" == key or term == key + "s":
                matched_key = key
                break
            
    # Normalize synonyms for seeds
    if not matched_key:
        for term in target_terms:
            if term in ("network", "networking", "network engineer", "network engineers"):
                matched_key = "network engineering"
                break
            elif term in ("cyber security", "cybersecurity", "information security", "infosec"):
                matched_key = "cybersecurity"
                break
            elif term in ("cloud engineer", "cloud computing", "cloud"):
                matched_key = "cloud"
                break
            elif term in ("ai", "artificial intelligence", "ai engineer", "ai engineers"):
                matched_key = "artificial intelligence"
                break
            elif term in ("ml", "machine learning", "ml engineer", "ml engineers"):
                matched_key = "machine learning"
                break
            elif term in ("data science", "data scientist", "data scientists"):
                matched_key = "data science"
                break
            elif term in ("data engineering", "data engineer", "data engineers"):
                matched_key = "data engineering"
                break
            elif term in ("iam", "identity and access management", "identity management", "access management"):
                matched_key = "iam"
                break


    if matched_key:
        seed = SEED_MAPS[matched_key]
        tech_map = {
            "network engineering": "network",
            "cybersecurity": "cybersecurity",
            "cloud": "cloud",
            "iam": "iam",
            "artificial intelligence": "ai",
            "machine learning": "machine learning",
            "data science": "data science",
            "data engineering": "data",
            "snowflake": "snowflake",
            "sap": "sap",
            "databricks": "databricks"
        }
        tech_constraint = tech_map.get(matched_key, q_clean)
        
        # Deduplicate and sort
        t1 = list(dict.fromkeys(seed["tier1"]))
        t2 = list(dict.fromkeys(seed["tier2"]))
        t3 = list(dict.fromkeys(seed["tier3"]))
        
        return {
            "query": q_clean,
            "classification": seed["classification"],
            "category": seed["category"],
            "tech_constraint": tech_constraint,
            "tiers": {"tier1": t1, "tier2": t2, "tier3": t3},
            "expanded_list": t1 + t2 + t3
        }

    # 2. Heuristic Classification if not in seed list
    is_role = False
    for suffix in ROLE_SUFFIXES:
        if q_lower.endswith(suffix) or q_lower.endswith(suffix + "s"):
            is_role = True
            break
            
    is_domain = False
    for kw in DOMAIN_KEYWORDS:
        if kw in q_lower:
            is_domain = True
            break
            
    classification = "TECHNOLOGY"
    if is_role:
        classification = "JOB_ROLE"
    elif is_domain:
        classification = "DOMAIN"

    # Strip suffix for base name expansion
    base_term = q_clean
    for suffix in ["engineers", "engineer", "developers", "developer", "analysts", "analyst", "scientists", "scientist", "consultants", "consultant", "specialists", "specialist", "administrators", "administrator", "managers", "manager", "operations", "support", "tester", "testers"]:
        if q_lower.endswith(suffix):
            base_term = q_clean[:-len(suffix)].strip()
            break

    # The technology constraint is never None - fallback to base_term for DOMAIN or JOB_ROLE
    tech_constraint = base_term

    # Analyze technology indicators to group into categories
    if any(k in q_lower for k in ["data", "db", "sql", "spark", "lakehouse", "kafka", "airflow", "postgres", "mysql", "warehouse", "etl", "streaming", "cassandra", "oracle", "mongodb", "redis", "dbt", "hadoop", "redshift", "bigquery", "clickhouse"]):
        category = "DATA / DATABASE / BIG DATA"
        tier1 = [f"{base_term} Data Engineer", f"{base_term} Engineer", f"{base_term} Developer", f"{base_term} Specialist"]
        tier2 = ["Data Engineer", "Senior Data Engineer", "Cloud Data Engineer", "Data Warehouse Engineer", "ETL Developer", "Analytics Engineer", "Data Architect"]
        tier3 = ["Data Scientist", "Database Administrator", "Data Analyst", "BI Developer"]
        
    elif any(k in q_lower for k in ["cloud", "devops", "sre", "terraform", "kubernetes", "k8s", "ansible", "jenkins", "docker", "helm", "ops", "infrastructure", "automation", "aws", "azure", "gcp", "gitops", "ci/cd"]):
        category = "CLOUD / DEVOPS / INFRASTRUCTURE"
        tier1 = [f"{base_term} Engineer", f"{base_term} Cloud Engineer", f"{base_term} DevOps Engineer", f"{base_term} Specialist"]
        tier2 = ["Cloud Engineer", "DevOps Engineer", "Site Reliability Engineer", "SRE", "Platform Engineer", "Cloud Architect", "Infrastructure Engineer"]
        tier3 = ["Systems Administrator", "Software Engineer", "Systems Engineer"]
        
    elif any(k in q_lower for k in ["ai", "ml", "artificial intelligence", "machine learning", "pytorch", "tensorflow", "nlp", "vision", "deep learning", "neural", "openai", "langchain", "llamaindex", "genai", "generative"]):
        category = "ARTIFICIAL INTELLIGENCE / ML"
        tier1 = [f"{base_term} Engineer", f"{base_term} Developer", f"{base_term} Research Scientist"]
        tier2 = ["Machine Learning Engineer", "ML Engineer", "AI Engineer", "Data Scientist", "Research Scientist", "NLP Engineer", "Computer Vision Engineer", "MLOps Engineer"]
        tier3 = ["Applied Scientist", "Data Engineer", "Software Engineer"]
        
    elif any(k in q_lower for k in ["security", "cyber", "sec", "firewall", "auth", "identity", "iam", "okta", "penetration", "pentest", "vulnerability", "soc"]):
        category = "SECURITY / CYBERSECURITY"
        tier1 = [f"{base_term} Security Engineer", f"{base_term} Engineer", f"{base_term} Analyst", f"{base_term} Specialist"]
        tier2 = ["Cybersecurity Engineer", "Cybersecurity Analyst", "Security Engineer", "Security Analyst", "SOC Analyst", "Penetration Tester", "Cloud Security Engineer", "IAM Engineer"]
        tier3 = ["Network Security Engineer", "Security Consultant", "Systems Administrator"]
        
    elif any(k in q_lower for k in ["sap", "salesforce", "servicenow", "crm", "erp", "dynamics", "workday"]):
        category = "ENTERPRISE SOFTWARE / ERP"
        tier1 = [f"{base_term} Consultant", f"{base_term} Developer", f"{base_term} Analyst"]
        tier2 = [f"{base_term} Specialist", f"{base_term} Architect", f"{base_term} Technical Consultant", f"{base_term} Functional Consultant"]
        tier3 = ["Application Engineer", "Business Analyst", "Systems Administrator"]
        
    elif any(k in q_lower for k in ["react", "angular", "vue", "frontend", "front-end", "js", "ts", "html", "css", "next.js", "svelte"]):
        category = "FRONTEND / WEB DEVELOPMENT"
        tier1 = [f"{base_term} Developer", f"{base_term} Frontend Developer", f"{base_term} Engineer"]
        tier2 = ["Frontend Engineer", "Frontend Developer", "Full Stack Developer", "UI Developer", "Web Developer"]
        tier3 = ["Software Engineer", "Web Designer"]
        
    elif any(k in q_lower for k in ["python", "java", "golang", "go", "c++", "c#", ".net", "rust", "ruby", "backend", "back-end", "php"]):
        category = "BACKEND / SOFTWARE DEVELOPMENT"
        tier1 = [f"{base_term} Developer", f"{base_term} Engineer", f"{base_term} Backend Developer"]
        tier2 = ["Backend Engineer", "Backend Developer", "Software Engineer", "Software Developer", "Full Stack Engineer"]
        tier3 = ["Systems Engineer", "Developer"]
        
    else:
        # Default Fallback for completely unknown tech
        category = "GENERAL TECHNOLOGY"
        tier1 = [f"{base_term} Engineer", f"{base_term} Developer", f"{base_term} Specialist"]
        tier2 = ["Software Engineer", "Software Developer", "Systems Engineer", "Application Developer"]
        tier3 = ["Consultant", "Analyst", "Technical Specialist"]

    # Exclude C-level positions from final lists to be safe
    c_level_patterns = ["cto", "cio", "ceo", "cfo", "coo", "cpo", "cro", "chief", "president", "vp", "director", "founder", "partner", "owner", "head of"]
    
    def clean_tier(lst):
        cleaned = []
        for r in lst:
            r_str = str(r).strip()
            r_lower = r_str.lower()
            if not any(re.search(rf"\b{p}\b", r_lower) for p in c_level_patterns):
                if r_str not in cleaned:
                    cleaned.append(r_str)
        return cleaned

    t1 = clean_tier(tier1)
    t2 = clean_tier(tier2)
    t3 = clean_tier(tier3)

    return {
        "query": q_clean,
        "classification": classification,
        "category": category,
        "tech_constraint": tech_constraint,
        "tiers": {"tier1": t1, "tier2": t2, "tier3": t3},
        "expanded_list": t1 + t2 + t3
    }
