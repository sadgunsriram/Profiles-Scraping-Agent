"""
Structured experience extraction module for authorized LinkedIn profile scraping.
Extracts work history with exact company, title, start date, end date, duration, and description.
Handles both single positions and grouped multi-role positions.
"""

import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from loguru import logger


DATE_RANGE_REGEX = re.compile(
    r'([A-Za-z]{3,}\s+\d{4}|\d{4})\s*[-–—]\s*([A-Za-z]{3,}\s+\d{4}|Present|\d{4})',
    re.IGNORECASE
)
DURATION_REGEX = re.compile(
    r'(?:·|•|\b)\s*(\d+\s*(?:yrs?|years?)(?:\s*\d+\s*(?:mos?|months?))?|\d+\s*(?:mos?|months?))',
    re.IGNORECASE
)


EMPLOYMENT_TYPES = {
    "full-time", "part-time", "contract", "freelance", "internship",
    "seasonal", "self-employed", "apprenticeship", "permanent"
}


def _clean_company_name(raw: str) -> str:
    """Clean company name by removing employment types, location tokens, or symbols."""
    if not raw:
        return ""
    cleaned = raw.strip()
    if cleaned.lower() in EMPLOYMENT_TYPES:
        return ""
    # Remove employment type suffixes like "· Full-time", "• Contract", "- Self-employed"
    cleaned = re.sub(
        r'[·•\-\|]\s*(?:Full-time|Part-time|Contract|Freelance|Internship|Seasonal|Self-employed|Apprenticeship).*$',
        '',
        cleaned,
        flags=re.IGNORECASE
    )
    # Remove trailing dots, dashes, or separators
    cleaned = cleaned.strip(" -·•|,")
    if cleaned.lower() in EMPLOYMENT_TYPES:
        return ""
    return cleaned.strip()


def parse_experience_date_range(text: str) -> Optional[Dict[str, str]]:
    """
    Parses a string containing a LinkedIn employment date range.
    Example: 'Jan 2021 - Present · 3 yrs 8 mos' ->
             {'start_date': 'Jan 2021', 'end_date': 'Present', 'duration_text': '3 yrs 8 mos'}
    """
    if not text:
        return None

    m = DATE_RANGE_REGEX.search(text)
    if not m:
        return None

    start_date = m.group(1).strip()
    end_date = m.group(2).strip()

    duration_text = ""
    dur_m = DURATION_REGEX.search(text)
    if dur_m:
        duration_text = dur_m.group(1).strip()

    return {
        "start_date": start_date,
        "end_date": end_date,
        "duration_text": duration_text
    }


def extract_structured_experience(html_content: str) -> List[Dict[str, str]]:
    """
    Parses LinkedIn experience section HTML into a structured list of employment history items.
    Handles both modern SDUI entity-collection-items and classic list items.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    jobs: List[Dict[str, str]] = []
    seen_keys = set()

    # 1. Identify experience entities (modern SDUI containers or top-level <li> elements)
    entities = soup.find_all(attrs={'componentkey': lambda k: k and 'entity-collection-item' in str(k)})
    if not entities:
        all_lis = soup.find_all("li")
        entities = [li for li in all_lis if not li.find_parent("li")]

    # If no top-level li was filtered, fallback to soup.find_all("li")
    if not entities:
        entities = soup.find_all("li")

    for item in entities:
        # Check if item represents a grouped company (has nested ul/li)
        nested_ul = item.find("ul")
        if nested_ul:
            # Grouped positions under a single company
            # Extract parent company name from text nodes outside the nested_ul
            header_nodes = []
            for s in item.find_all(string=True):
                # If this text node is inside the nested_ul, it belongs to the roles, not the company header
                if nested_ul in s.parents:
                    continue
                st = s.strip()
                if st:
                    header_nodes.append(st)

            parent_company = ""
            for h in header_nodes:
                cleaned_h = _clean_company_name(h)
                if cleaned_h and not DURATION_REGEX.search(cleaned_h) and not DATE_RANGE_REGEX.search(cleaned_h):
                    parent_company = cleaned_h
                    break

            # Extract each sub-role in the nested list
            sub_items = nested_ul.find_all("li", recursive=False)
            if not sub_items:
                sub_items = nested_ul.find_all("li")

            for sub in sub_items:
                sub_nodes = [s.strip() for s in sub.find_all(string=True) if s.strip()]
                if not sub_nodes:
                    continue

                sub_title = sub_nodes[0]
                sub_date_info = None
                sub_desc_parts = []

                for idx, node in enumerate(sub_nodes[1:], 1):
                    parsed_dates = parse_experience_date_range(node)
                    if parsed_dates and not sub_date_info:
                        sub_date_info = parsed_dates
                    elif sub_date_info:
                        if not any(ign in node.lower() for ign in ["see more", "show all", "endorse"]):
                            sub_desc_parts.append(node)

                if sub_title and sub_date_info:
                    key = (sub_title, parent_company, sub_date_info["start_date"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        jobs.append({
                            "company": parent_company,
                            "company_name": parent_company,
                            "title": sub_title,
                            "start_date": sub_date_info["start_date"],
                            "end_date": sub_date_info["end_date"],
                            "duration_text": sub_date_info["duration_text"],
                            "description": " ".join(sub_desc_parts).strip()
                        })
            continue

        # Single position item
        nodes = [s.strip() for s in item.find_all(string=True) if s.strip()]
        if len(nodes) < 2:
            continue

        # Find the date node index
        date_idx = -1
        date_info = None
        for idx, node in enumerate(nodes):
            parsed = parse_experience_date_range(node)
            if parsed:
                date_idx = idx
                date_info = parsed
                break

        if date_idx > 0 and date_info:
            title = nodes[0]
            company = ""
            cand_tokens = [nodes[i] for i in range(date_idx)]
            cleaned_cands = []
            for ct in cand_tokens[1:]:
                cleaned = _clean_company_name(ct)
                if cleaned and cleaned.lower() not in EMPLOYMENT_TYPES:
                    cleaned_cands.append(cleaned)

            if cleaned_cands:
                company = cleaned_cands[0]
            elif date_idx > 2:
                title = nodes[date_idx - 1]
                company = _clean_company_name(nodes[0])

            # Description nodes are those after date_idx (excluding location or see more)
            desc_parts = []
            for k in range(date_idx + 1, len(nodes)):
                n = nodes[k]
                if parse_experience_date_range(n):
                    break
                if any(ign in n.lower() for ign in ["see more", "show all", "skills:"]):
                    continue
                desc_parts.append(n)

            if title and company:
                key = (title, company, date_info["start_date"])
                if key not in seen_keys:
                    seen_keys.add(key)
                    jobs.append({
                        "company": company,
                        "company_name": company,
                        "title": title,
                        "start_date": date_info["start_date"],
                        "end_date": date_info["end_date"],
                        "duration_text": date_info["duration_text"],
                        "description": " ".join(desc_parts).strip()
                    })

    # If list_items parsing didn't find jobs, use string scanning fallback
    if not jobs:
        date_tags = soup.find_all(string=DATE_RANGE_REGEX)
        for tag in date_tags:
            date_str = tag.strip()
            date_info = parse_experience_date_range(date_str)
            if not date_info:
                continue

            p = tag.parent
            title = ""
            company = ""
            desc_parts = []

            while p and p.name not in ["[document]", "html", "body"]:
                all_nodes = [s.strip() for s in p.find_all(string=True) if s.strip()]
                if date_str in all_nodes:
                    idx = all_nodes.index(date_str)
                    if idx >= 2:
                        title = all_nodes[0]
                        company = _clean_company_name(all_nodes[1])
                    elif idx == 1:
                        title = all_nodes[0]

                    for k in range(idx + 1, len(all_nodes)):
                        n = all_nodes[k]
                        if DATE_RANGE_REGEX.search(n):
                            break
                        if n.lower() not in ["see more", "show all"]:
                            desc_parts.append(n)
                if title and company:
                    break
                p = p.parent

            if title and company:
                key = (title, company, date_info["start_date"])
                if key not in seen_keys and title.lower() != "experience":
                    seen_keys.add(key)
                    jobs.append({
                        "company": company,
                        "company_name": company,
                        "title": title,
                        "start_date": date_info["start_date"],
                        "end_date": date_info["end_date"],
                        "duration_text": date_info["duration_text"],
                        "description": " ".join(desc_parts).strip()
                    })

    logger.debug(f"[ExperienceExtractor] Extracted {len(jobs)} structured experience entries.")
    return jobs
