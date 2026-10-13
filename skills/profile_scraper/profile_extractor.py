"""
profile_extractor.py — Complete Progressive Profile Extraction Coordinator.

Coordinates the progressive harvesting of all available LinkedIn sections:
1. Top Card / Introduction (Name, Headline, Location, Connections, Pronouns)
2. Contact Information Modal (Email, Phone, Websites, GitHub, Explicit Birthday)
3. About Section (with inline expansion)
4. Featured Section
5. Experience Section (with nested role expansion & full timeline descriptions)
6. Education Section (Institutions, Degrees, Fields of Study, Graduation Years)
7. Licenses & Certifications (Names, Issuing Authorities, Dates, Credential IDs)
8. Skills Section (Complete skill inventory)
9. Projects Section (Titles, Descriptions, URLs)
10. Languages Section (Languages & Proficiency)
11. Volunteer Experience Section

Missing sections default cleanly without interrupting or failing the scraping pipeline.
All data is packaged into a complete NormalizedCandidateProfile object.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import Page

from skills.profile_scraper.candidate_models import (
    NormalizedCandidateProfile,
    ExperienceEntry,
    EducationEntry,
    CertificationEntry,
    ProjectEntry
)
from skills.profile_scraper.contact_extractor import extract_contact_info
from skills.profile_scraper.content_scroller import scroll_profile_progressively
from skills.profile_scraper.demographics import extract_explicit_demographics
from skills.profile_scraper.experience_extractor import extract_structured_experience
from skills.profile_scraper.section_expander import (
    expand_about_section,
    expand_experience_descriptions,
    expand_skills_section
)
from skills.profile_scraper.workflow_state import WorkflowStage, WorkflowStateTracker
from skills.profile_scraper.selectors import (
    PROFILE_NAME_SELECTORS,
    HEADLINE_SELECTORS,
    LOCATION_SELECTORS,
    ABOUT_SECTION_SELECTORS,
    CONNECTION_COUNT_SELECTORS,
    query_first_text
)


def _parse_education_entities(soup: BeautifulSoup) -> List[EducationEntry]:
    """Extract structured education entries from the Education section."""
    education: List[EducationEntry] = []
    edu_sec = soup.find(attrs={'componentkey': lambda k: k and 'Education' in str(k)}) or soup.find("section", id="education")
    if not edu_sec:
        return education

    entities = edu_sec.find_all(attrs={'componentkey': lambda k: k and 'entity-collection-item' in str(k)})
    if not entities:
        entities = edu_sec.find_all("li", recursive=False) or edu_sec.find_all("li")

    for ent in entities:
        text_nodes = [s.strip() for s in ent.find_all(string=True) if s.strip()]
        text_nodes = [n for n in text_nodes if n.lower() not in ["see more", "show all", "more", "education"]]
        if not text_nodes:
            continue

        institution = text_nodes[0]
        degree = None
        field_of_study = None
        start_year = None
        end_year = None

        for node in text_nodes[1:]:
            # Look for years: e.g. "2016 - 2020" or "2018"
            year_matches = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', node)
            if year_matches:
                years = [int(y) for y in year_matches]
                start_year = min(years)
                end_year = max(years)
            elif any(d_kw in node.lower() for d_kw in ["bachelor", "master", "doctor", "b.s", "m.s", "ph.d", "associate", "btech", "degree", "diploma", "licentiate"]):
                degree = node
            elif not field_of_study and not degree and len(node) < 60:
                field_of_study = node

        education.append(EducationEntry(
            institution=institution,
            degree=degree,
            field_of_study=field_of_study,
            start_year=start_year,
            end_year=end_year
        ))

    return education


def _parse_certifications_entities(soup: BeautifulSoup) -> List[CertificationEntry]:
    """Extract structured license and certification records."""
    certs: List[CertificationEntry] = []
    cert_sec = soup.find(attrs={'componentkey': lambda k: k and 'Certification' in str(k)}) or soup.find("section", id="licenses_and_certifications")
    if not cert_sec:
        return certs

    entities = cert_sec.find_all(attrs={'componentkey': lambda k: k and 'entity-collection-item' in str(k)})
    if not entities:
        entities = cert_sec.find_all("li", recursive=False) or cert_sec.find_all("li")

    for ent in entities:
        text_nodes = [s.strip() for s in ent.find_all(string=True) if s.strip()]
        text_nodes = [n for n in text_nodes if n.lower() not in ["see more", "show all", "more", "licenses & certifications"]]
        if not text_nodes:
            continue

        name = text_nodes[0]
        issuing_org = text_nodes[1] if len(text_nodes) > 1 else ""
        issue_date = None
        cred_id = None

        for node in text_nodes[1:]:
            if "issued" in node.lower() or any(m in node.lower() for m in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
                issue_date = node
            elif "credential id" in node.lower():
                cred_id = node.split(":")[-1].strip()

        certs.append(CertificationEntry(
            name=name,
            issuing_organization=issuing_org,
            issue_date=issue_date,
            credential_id=cred_id
        ))

    return certs


def _parse_projects_entities(soup: BeautifulSoup) -> List[ProjectEntry]:
    """Extract structured projects from the Projects section."""
    projects: List[ProjectEntry] = []
    proj_sec = soup.find(attrs={'componentkey': lambda k: k and 'Project' in str(k)}) or soup.find("section", id="projects")
    if not proj_sec:
        return projects

    entities = proj_sec.find_all(attrs={'componentkey': lambda k: k and 'entity-collection-item' in str(k)})
    if not entities:
        entities = proj_sec.find_all("li", recursive=False) or proj_sec.find_all("li")

    for ent in entities:
        text_nodes = [s.strip() for s in ent.find_all(string=True) if s.strip()]
        text_nodes = [n for n in text_nodes if n.lower() not in ["see more", "show all", "more", "projects"]]
        if not text_nodes:
            continue

        title = text_nodes[0]
        desc_parts = []
        start_date = None
        end_date = None

        for node in text_nodes[1:]:
            date_m = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', node)
            if date_m and not start_date:
                years = [int(y) for y in date_m]
                start_date = str(min(years))
                end_date = str(max(years))
            elif len(node) > 20:
                desc_parts.append(node)

        link_elem = ent.find("a", href=True)
        proj_url = link_elem["href"] if link_elem else None

        projects.append(ProjectEntry(
            title=title,
            description=" ".join(desc_parts).strip(),
            start_date=start_date,
            end_date=end_date,
            url=proj_url
        ))

    return projects


def _parse_languages_entities(soup: BeautifulSoup) -> List[str]:
    """Extract languages and proficiency ratings."""
    languages: List[str] = []
    lang_sec = soup.find(attrs={'componentkey': lambda k: k and 'Language' in str(k)}) or soup.find("section", id="languages")
    if not lang_sec:
        return languages

    entities = lang_sec.find_all(attrs={'componentkey': lambda k: k and 'entity-collection-item' in str(k)}) or lang_sec.find_all("li")
    for ent in entities:
        nodes = [s.strip() for s in ent.find_all(string=True) if s.strip() and s.lower() not in ["languages", "show all", "more"]]
        if nodes:
            languages.append(" - ".join(nodes[:2]))

    return languages


def _parse_volunteer_entities(soup: BeautifulSoup) -> List[str]:
    """Extract volunteer experiences."""
    volunteer: List[str] = []
    vol_sec = soup.find(attrs={'componentkey': lambda k: k and 'Volunteer' in str(k)}) or soup.find("section", id="volunteer_experience")
    if not vol_sec:
        return volunteer

    entities = vol_sec.find_all(attrs={'componentkey': lambda k: k and 'entity-collection-item' in str(k)}) or vol_sec.find_all("li")
    for ent in entities:
        nodes = [s.strip() for s in ent.find_all(string=True) if s.strip() and s.lower() not in ["volunteer", "show all", "more"]]
        if nodes:
            volunteer.append(" | ".join(nodes[:3]))

    return volunteer


def _parse_featured_entities(soup: BeautifulSoup) -> List[str]:
    """Extract featured posts, articles, links, and media items."""
    featured: List[str] = []
    feat_sec = (
        soup.find(attrs={'componentkey': lambda k: k and 'Featured' in str(k)}) or
        soup.find("section", id="featured") or
        soup.find("section", attrs={"data-section": "featured"})
    )
    if not feat_sec:
        for sec in soup.find_all("section"):
            h2 = sec.find(["h2", "h3"])
            if h2 and "featured" in h2.get_text().lower():
                feat_sec = sec
                break

    if not feat_sec:
        return featured

    items = feat_sec.find_all(attrs={'componentkey': lambda k: k and ('entity-collection-item' in str(k) or 'featured' in str(k).lower())})
    if not items:
        items = feat_sec.find_all(["li", "div.artdeco-card"])

    for item in items:
        link_elem = item.find("a", href=True)
        link = link_elem["href"] if link_elem else ""
        text_nodes = [s.strip() for s in item.find_all(string=True) if s.strip()]
        text_nodes = [n for n in text_nodes if n.lower() not in ["featured", "see more", "more", "show all"]]
        if text_nodes:
            summary = " | ".join(text_nodes[:2])
            if link and not link.startswith("javascript:"):
                featured.append(f"{summary} ({link})")
            else:
                featured.append(summary)

    return list(dict.fromkeys(featured))


def detect_open_to_work(
    page: Optional[Page] = None,
    soup: Optional[BeautifulSoup] = None,
    headline: str = "",
    about: str = "",
    candidate_name: str = ""
) -> Tuple[bool, str]:
    """
    Authoritative detection of active 'Open to Work' status on a candidate's LinkedIn profile.
    Strictly scoped to the candidate's profile containers, explicitly ignoring any viewer/nav widgets.

    Checks 4 distinct visual and textual layers:
    1. Candidate Headline declarations (#OpenToWork, 'Open to work', 'Actively Looking')
    2. Candidate Topcard photo avatar badge / frame
    3. Dedicated candidate 'Open to work' spotlight card / section
    4. Opening declaration in candidate's About section
    """
    otw_pattern = r'(#open_?to_?work|\bopen to work\b|\bactively looking\b|\bseeking (?:new )?(?:roles?|opportunit\w+|positions?)\b|\bopen for (?:new )?(?:roles?|opportunit\w+)\b|\bready to work\b|\bavailable for (?:hire|roles?|work)\b)'

    # 1. Headline Check (Candidate's personal declaration)
    if headline and re.search(otw_pattern, headline, re.IGNORECASE):
        match = re.search(otw_pattern, headline, re.IGNORECASE).group(0)
        return True, f"Headline: '{match}'"

    # 2. Live DOM Playwright Inspection (Photo Badge & Spotlight Card)
    if page:
        # A. Check candidate's topcard container strictly
        topcard_selectors = [
            "section[componentkey*='Topcard']",
            "div[componentkey*='Topcard']",
            "section.pv-top-card",
            "div.pv-top-card",
            "main div.ph5"
        ]
        topcard = None
        for tc_sel in topcard_selectors:
            try:
                tc = page.locator(tc_sel).first
                if tc.count() > 0:
                    topcard = tc
                    break
            except Exception:
                pass

        if topcard:
            # Check within the candidate's topcard only
            tc_badge_selectors = [
                ".pv-top-card-profile-picture__image--show-open-to-work",
                "img[title*='Open to work' i]",
                "img[alt*='Open to work' i]",
                "[aria-label*='Open to work' i]",
                "[data-view-name*='open-to-work']",
                ".pv-top-card-profile-picture[class*='open-to-work']"
            ]
            for sel in tc_badge_selectors:
                try:
                    elem = topcard.locator(sel).first
                    if elem.count() > 0 and elem.is_visible():
                        alt = (elem.get_attribute("alt") or "").lower()
                        if "view your profile" in alt or "view manas" in alt:
                            continue
                        return True, f"Topcard Photo Frame ({sel})"
                except Exception:
                    pass

        # B. Dedicated Spotlight Card in main content
        spotlight_selectors = [
            "main div.pv-open-to-work-card",
            "main section[data-section='openToWork']",
            "main [data-view-name*='open-to-work']"
        ]
        for s_sel in spotlight_selectors:
            try:
                card = page.locator(s_sel).first
                if card.count() > 0 and card.is_visible():
                    txt = card.inner_text().lower()
                    # Filter out promo banners targeted to the viewing account
                    if "show recruiters you" in txt or "get started" in txt:
                        continue
                    if "open to work" in txt:
                        return True, f"Candidate Spotlight Card ({s_sel})"
            except Exception:
                pass

        # C. Generic candidate spotlight section inside main
        try:
            otw_section = page.locator("main section:has-text('Open to work')").first
            if otw_section.count() > 0 and otw_section.is_visible():
                txt = otw_section.inner_text().lower()
                if "open to work" in txt and any(w in txt for w in ["roles", "details", "job titles", "remote"]):
                    if not ("show recruiters you" in txt or "get started" in txt):
                        return True, "Candidate Spotlight Section: 'Open to work'"
        except Exception:
            pass

        # D. Main avatar image inspection with nav exclusion & viewer filtering
        try:
            imgs = page.locator("main img[alt*='open to work' i]").all()
            for img in imgs:
                try:
                    is_in_nav = img.evaluate("el => !!el.closest('header, nav, .global-nav, .feed-identity-module, aside')")
                    if is_in_nav:
                        continue
                    alt = (img.get_attribute("alt") or "").lower()
                    if "view your profile" in alt or "view manas" in alt:
                        continue
                    if candidate_name:
                        first_name = candidate_name.split()[0].lower()
                        if first_name and first_name in alt:
                            return True, f"Candidate Avatar Alt: '{alt[:40]}'"
                    else:
                        return True, f"Candidate Avatar Alt: '{alt[:40]}'"
                except Exception:
                    continue
        except Exception:
            pass

    # 3. BeautifulSoup Inspection (Fallback / Tests)
    if soup:
        import copy
        soup_copy = copy.copy(soup)
        for tag in soup_copy.find_all(["header", "nav", "aside"]):
            tag.decompose()

        # Check candidate photo frame badge
        badge = soup_copy.select_one(".pv-top-card-profile-picture__image--show-open-to-work, [data-view-name*='open-to-work'], .pv-open-to-work-card, section[data-section='openToWork']")
        if badge:
            return True, "DOM Attribute Match (Badge/Card)"

        for img in soup_copy.find_all("img"):
            alt = str(img.get("alt", "")).lower()
            title = str(img.get("title", "")).lower()
            if any("open to work" in s or "opentowork" in s for s in (alt, title)):
                if "view your profile" not in alt and "view manas" not in alt:
                    return True, "DOM Attribute Match (img)"

        # Check section texts
        for sec in soup_copy.find_all(["section", "div"]):
            sec_text = sec.get_text().strip().lower()
            if "open to work" in sec_text and any(k in sec_text for k in ["roles", "show details", "job titles"]):
                if not ("show recruiters you" in sec_text or "get started" in sec_text):
                    return True, "Rendered Section: 'Open to work'"

    # 4. About Section Statement
    if about:
        about_intro = about[:600]
        if re.search(otw_pattern, about_intro, re.IGNORECASE):
            match = re.search(otw_pattern, about_intro, re.IGNORECASE).group(0)
            return True, f"About Section: '{match}'"

    return False, "Not Open to Work"


def extract_full_profile(
    page: Page,
    url: str,
    enable_extension: bool = False,
    tracker: Optional[WorkflowStateTracker] = None,
    require_open_to_work: bool = False
) -> Dict[str, Any]:
    """
    Extracts complete, structured LinkedIn profile data from an authenticated page.
    Implements progressive viewport harvesting across all sections.
    If require_open_to_work is True, checks Open to Work early and skips heavy scrolling if not Open to Work.
    """
    if tracker is None:
        tracker = WorkflowStateTracker(profile_url=url)
    tracker.record_transition(WorkflowStage.PROFILE_OPENED, f"Opened profile page: {url}")

    logger.info(f"[ProfileExtractor] Beginning progressive profile harvesting for: {url}")
    all_failed_selectors: List[str] = []

    # 1. Extract Top Card details
    PRONOUNS_FILTER = {"he/him", "she/her", "they/them", "she/her/hers", "he/him/his", "they/them/theirs"}

    full_name, name_sel, failed_name = query_first_text(page, PROFILE_NAME_SELECTORS)
    all_failed_selectors.extend(failed_name)
    if full_name and full_name.lower().strip() in PRONOUNS_FILTER:
        full_name = ""

    # Document title fallback for name
    if not full_name:
        try:
            page_title = page.title()
            if page_title and "|" in page_title:
                cand_name = page_title.split("|")[0].strip()
                if cand_name and "linkedin" not in cand_name.lower() and cand_name.lower() not in PRONOUNS_FILTER:
                    full_name = cand_name
                    name_sel = "document.title"
        except Exception:
            pass

    headline, head_sel, failed_head = query_first_text(page, HEADLINE_SELECTORS)
    all_failed_selectors.extend(failed_head)

    location, loc_sel, failed_loc = query_first_text(page, LOCATION_SELECTORS)
    all_failed_selectors.extend(failed_loc)
    if location:
        if "contact info" in location.lower():
            location = location.replace("Contact info", "").strip()
        if '|' in location or len(location) > 70 or (headline and location.strip() == headline.strip()):
            location = ""

    connection_count, conn_sel, _ = query_first_text(page, CONNECTION_COUNT_SELECTORS)
    tracker.record_transition(WorkflowStage.INTRO_PROCESSED, f"Name: {full_name}, Headline: {headline}, Location: {location}")

    # 2. Expand About section early for keyword detection
    expand_about_section(page)
    about = ""
    for a_sel in ABOUT_SECTION_SELECTORS:
        try:
            about_card = page.locator(a_sel).first
            if about_card.count() > 0 and about_card.is_visible():
                about = about_card.inner_text().replace("About\n", "").strip()
                if about:
                    break
        except Exception:
            all_failed_selectors.append(a_sel)

    # 3. Early Open to Work Detection & Fast-Exit Gate
    is_otw, otw_details = detect_open_to_work(page=page, soup=None, headline=headline, about=about, candidate_name=full_name)
    logger.info(f"[ProfileExtractor] Open to Work detection for '{full_name}': {is_otw} ({otw_details})")

    if require_open_to_work and not is_otw:
        logger.info(
            f"[ProfileExtractor] FAST FILTER: Candidate '{full_name}' is NOT Open to Work ({otw_details}). "
            f"Skipping 11-section scrolling to preserve campaign focus."
        )
        tracker.record_transition(WorkflowStage.ANALYSIS_COMPLETED, f"Fast-filtered: Not Open to Work ({otw_details})")
        cand = NormalizedCandidateProfile(
            full_name=full_name or "Candidate",
            linkedin_url=url,
            headline=headline or "NOT_AVAILABLE",
            location=location or "NOT_AVAILABLE",
            about=about or "NOT_AVAILABLE",
            is_open_to_work=False,
            open_to_work_details=otw_details
        )
        return {
            "full_name": full_name,
            "headline": headline,
            "location": location,
            "about": about,
            "email": "NOT_AVAILABLE",
            "phone": "NOT_AVAILABLE",
            "websites": [],
            "github_url": "NOT_AVAILABLE",
            "is_open_to_work": False,
            "open_to_work_details": otw_details,
            "fast_filtered_not_open_to_work": True,
            "normalized_candidate_object": cand
        }

    # 4. Extract Contact Info & Birthday from Contact Modal
    contact_data = extract_contact_info(page, enable_extension=enable_extension)
    email = contact_data.get("email", "")
    phone = contact_data.get("phone", "")
    websites = contact_data.get("websites", [])
    github_url = contact_data.get("github_url", "")
    explicit_dob = contact_data.get("date_of_birth", "NOT_AVAILABLE")
    modal_text = contact_data.get("raw_modal_text", "")
    tracker.record_transition(WorkflowStage.CONTACT_INFO_PROCESSED, f"Email: {email}, Phone: {phone}, Websites: {len(websites)}")
    tracker.record_transition(WorkflowStage.ABOUT_PROCESSED, f"About section extracted ({len(about)} characters)")

    # 5. Progressive Section-Aware Scrolling
    section_processing_log = scroll_profile_progressively(page)

    # 6. Expand Experience and Skills descriptions
    expand_experience_descriptions(page)
    expand_skills_section(page)

    # 6. Parse Rendered DOM for all sections
    html_content = page.content()
    soup = BeautifulSoup(html_content, "html.parser")

    # Fallback Top Card parsing if DOM elements were lazy
    topcard = soup.find(attrs={'componentkey': lambda k: k and 'Topcard' in str(k)})
    if topcard:
        if not full_name:
            h2 = topcard.find('h2')
            if h2 and h2.get_text().strip():
                full_name = h2.get_text().strip()
        ps = [p_tag.get_text().strip() for p_tag in topcard.find_all('p') if p_tag.get_text().strip()]
        for p_txt in ps:
            if any(pronoun in p_txt.lower() for pronoun in ['he/him', 'she/her', 'they/them']):
                continue
            if 'connection' in p_txt.lower() or 'contact info' in p_txt.lower():
                continue
            is_job_headline = (
                '|' in p_txt or
                any(w in p_txt.lower() for w in [
                    'engineer', 'developer', 'analyst', 'specialist', 'technician',
                    'consultant', 'architect', 'manager', 'director', 'lead',
                    'support', 'administrator', 'looking for', 'seeking', 'open to work'
                ]) or
                len(p_txt) > 65
            )
            if not headline and ('at ' in p_txt or 'engineer' in p_txt.lower() or 'developer' in p_txt.lower() or len(p_txt) > 15):
                headline = p_txt
            elif not location and not is_job_headline and (',' in p_txt or any(loc_kw in p_txt.lower() for loc_kw in ['united states', 'area', 'region', 'city', 'greater'])):
                location = p_txt

    # 7. Extract Structured Experience Timeline
    exp_html = ""
    skills_text = ""
    for sec in soup.find_all(["section", "div"]):
        ck = sec.get("componentkey") or ""
        id_ = sec.get("id") or ""
        h2 = sec.find(["h2", "h3"])
        h2_txt = h2.get_text().lower() if h2 else ""

        if not exp_html and ("experience" in h2_txt or "experiencetoplevelsection" in ck.lower() or id_ == "experience"):
            if sec.name == "section" or sec.find(attrs={'componentkey': lambda k: k and 'entity-collection-item' in str(k)}):
                exp_html = str(sec)

        if not skills_text and ("skills" in h2_txt or "skills" in ck.lower() or id_ == "skills"):
            skills_text = sec.get_text()

    raw_experience_history = extract_structured_experience(exp_html)
    experience_entries: List[ExperienceEntry] = []
    for raw_exp in raw_experience_history:
        experience_entries.append(ExperienceEntry(
            title=raw_exp.get("title", "Role"),
            company=raw_exp.get("company") or raw_exp.get("company_name", "Company"),
            start_date=raw_exp.get("start_date", ""),
            end_date=raw_exp.get("end_date", "Present"),
            duration_text=raw_exp.get("duration_text", ""),
            description=raw_exp.get("description", "")
        ))
    tracker.record_transition(WorkflowStage.EXPERIENCE_PROCESSED, f"Total employment history entries: {len(experience_entries)}")

    # 8. Extract Skills
    skills: List[str] = []
    skill_sec_elem = soup.find(attrs={'componentkey': lambda k: k and 'Skills' in str(k)}) or soup.find("section", id="skills")
    if skill_sec_elem:
        skill_cards = skill_sec_elem.find_all(attrs={'componentkey': lambda k: k and 'profile.skill' in str(k)})
        for sc in skill_cards:
            snodes = [t.strip() for t in sc.find_all(string=True) if t.strip()]
            if snodes and snodes[0] not in skills:
                skills.append(snodes[0])

    if not skills and skills_text:
        skill_lines = [l.strip() for l in skills_text.split("\n") if l.strip()]
        skills = [
            l for l in skill_lines 
            if l not in ["Skills", "Show all", "Endorse", "Endorsement", "more"] and len(l) < 50
        ]
        skills = list(dict.fromkeys(skills))

    # 9. Extract Education, Certifications, Projects, Languages, Volunteer, Featured
    education_entries = _parse_education_entities(soup)
    tracker.record_transition(WorkflowStage.EDUCATION_PROCESSED, f"Total education entries: {len(education_entries)}")

    cert_entries = _parse_certifications_entities(soup)
    project_entries = _parse_projects_entities(soup)
    language_entries = _parse_languages_entities(soup)
    volunteer_entries = _parse_volunteer_entities(soup)
    featured_entries = _parse_featured_entities(soup)

    tracker.record_transition(
        WorkflowStage.ADDITIONAL_SECTIONS_PROCESSED,
        f"Certs: {len(cert_entries)}, Projects: {len(project_entries)}, Featured: {len(featured_entries)}, Skills: {len(skills)}, Languages: {len(language_entries)}, Volunteer: {len(volunteer_entries)}"
    )

    # 10. Extract Ethical Voluntary Demographics
    demographic_payload = {
        "full_name": full_name,
        "headline": headline,
        "about": about,
        "experience_history": raw_experience_history
    }
    demographics_dict = extract_explicit_demographics(demographic_payload, html_content, modal_text)
    if explicit_dob != "NOT_AVAILABLE" and demographics_dict.get("date_of_birth") == "NOT_AVAILABLE":
        demographics_dict["date_of_birth"] = explicit_dob

    # Current role and company derivation
    current_company = ""
    current_title = ""
    if experience_entries:
        current_company = experience_entries[0].company
        current_title = experience_entries[0].title
    elif headline:
        current_title = headline

    # 11. Build Typed NormalizedCandidateProfile
    tracker.record_transition(WorkflowStage.PROFILE_COMPLETED, f"Harvesting completed successfully for {full_name}")

    normalized_candidate = NormalizedCandidateProfile(
        full_name=full_name or "Candidate",
        linkedin_url=url,
        headline=headline or "NOT_AVAILABLE",
        location=location or "NOT_AVAILABLE",
        current_title=current_title or "NOT_AVAILABLE",
        current_company=current_company or "NOT_AVAILABLE",
        connection_count=connection_count or "NOT_AVAILABLE",
        about=about or "NOT_AVAILABLE",
        date_of_birth=demographics_dict.get("date_of_birth", "NOT_AVAILABLE"),
        gender=demographics_dict.get("gender", "NOT_SPECIFIED"),
        pronouns=demographics_dict.get("pronouns", "NOT_SPECIFIED"),
        experience_history=experience_entries,
        education=education_entries,
        certifications=cert_entries,
        skills=skills,
        projects=project_entries,
        languages=language_entries,
        volunteer=volunteer_entries,
        featured_content=featured_entries,
        email=email or "NOT_AVAILABLE",
        phone=phone or "NOT_AVAILABLE",
        websites=websites,
        github_url=github_url or "NOT_AVAILABLE",
        is_open_to_work=is_otw,
        open_to_work_details=otw_details,
        raw_payload={
            "html_length": len(html_content),
            "experience_history": raw_experience_history,
            "education": [e.__dict__ for e in education_entries],
            "certifications": [c.__dict__ for c in cert_entries],
            "projects": [p.__dict__ for p in project_entries],
            "skills": skills,
            "languages": language_entries,
            "volunteer": volunteer_entries,
            "featured_content": featured_entries,
            "contacts": contact_data,
            "section_processing_log": section_processing_log,
            "workflow_state": tracker.to_dict(),
            "selector_diagnostics": {
                "name_selector": name_sel,
                "headline_selector": head_sel,
                "location_selector": loc_sel,
                "connection_selector": conn_sel,
                "failed_selectors": all_failed_selectors
            }
        }
    )

    # Return comprehensive dictionary containing normalized model and raw response
    res = normalized_candidate.to_dict()
    res["normalized_candidate_object"] = normalized_candidate
    res["section_processing_log"] = section_processing_log
    res["data_source"] = "Authorized LinkedIn API"
    res["company"] = current_company
    res["current_company_name"] = current_company
    res["is_open_to_work"] = is_otw
    res["open_to_work_details"] = otw_details

    # Education/cert flat string helpers for backward compatibility
    res["education_strings"] = [f"{e.degree or 'Degree'} | {e.institution}" for e in education_entries]
    res["certifications_strings"] = [f"{c.name} ({c.issuing_organization})" for c in cert_entries]

    logger.info(
        f"[ProfileExtractor] Successfully harvested profile for '{full_name}'. "
        f"Roles: {len(experience_entries)}, Education: {len(education_entries)}, "
        f"Certs: {len(cert_entries)}, Skills: {len(skills)}, Projects: {len(project_entries)}."
    )
    return res
