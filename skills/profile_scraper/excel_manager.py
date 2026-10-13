"""
excel_manager.py — Excel persistence manager supporting both 4-Sheet Lifecycle and legacy SET exports.
Maintains backward-compatibility for SET_1, SET_2, SET_3, and _Rejected_* sheets,
while providing ALL_RAW_PROFILES, ELIGIBLE_CANDIDATES, NEEDS_REVIEW, and REJECTED_CANDIDATES.
"""

import time
import os
import json
from loguru import logger
import openpyxl
from openpyxl.utils import get_column_letter

from skills.profile_scraper.excel_repository import (
    COLUMNS_RAW,
    COLUMNS_ELIGIBLE,
    COLUMNS_NEEDS_REVIEW,
    COLUMNS_REJECTED
)


def batch_save_profiles(
    set1_candidates: list,
    set2_candidates: list,
    set3_candidates: list,
    rejected_candidates: dict,
    path: str = "skills/output/profiles.xlsx",
    all_raw_profiles: list = None
):
    """
    Writes candidate batches safely to Excel workbook.
    Handles workbook lock detection and retries.
    Writes both legacy SET_1/SET_2/SET_3 sheets AND the 4 new standardized lifecycle sheets:
    - ALL_RAW_PROFILES
    - ELIGIBLE_CANDIDATES
    - NEEDS_REVIEW
    - REJECTED_CANDIDATES
    """
    max_retries = 5
    retry_delay = 1.0

    wb = None
    for attempt in range(max_retries):
        try:
            if os.path.exists(path):
                wb = openpyxl.load_workbook(path)
            else:
                wb = openpyxl.Workbook()
                if 'Sheet' in wb.sheetnames:
                    wb.remove(wb['Sheet'])
            break
        except PermissionError:
            logger.warning(f"[Excel] PermissionError: File {path} is locked. Retrying in {retry_delay}s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(retry_delay)
            retry_delay *= 2
        except Exception as e:
            logger.error(f"[Excel] Error loading workbook: {e}")
            break

    if wb is None:
        fallback_path = path.replace(".xlsx", f"_pending_{int(time.time())}.xlsx")
        logger.error(f"[Excel] Could not write to main database file. Saving fallback data to {fallback_path}")
        wb = openpyxl.Workbook()
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        path = fallback_path

    # Prune any legacy sheets to keep workbook neat and clean
    for s in list(wb.sheetnames):
        if s in ["SET_1", "SET_2", "SET_3", "Sheet"] or s.startswith("_Rejected_"):
            wb.remove(wb[s])

    def get_or_create_sheet(title, columns):
        # Prune legacy sheets if any remain
        for s in list(wb.sheetnames):
            if s in ["SET_1", "SET_2", "SET_3", "Sheet"] or s.startswith("_Rejected_"):
                wb.remove(wb[s])
        if title in wb.sheetnames:
            ws = wb[title]
            first_row = list(ws.iter_rows(max_row=1, values_only=True))
            header = list(first_row[0]) if first_row else []
            if header != columns:
                wb.remove(ws)
                ws = wb.create_sheet(title=title)
                ws.append(columns)
        else:
            ws = wb.create_sheet(title=title)
            ws.append(columns)
        return ws

    def clean_val(val, default="Not Available"):
        if val is None or str(val).strip().lower() in ("none", "null", "unknown", "not available", "not_available", "n/a", ""):
            return default
        return str(val).strip()

    def get_existing_keys(ws, name_idx=0, url_idx=3):
        keys = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and len(row) > max(name_idx, url_idx):
                name = str(row[name_idx] or "").strip().lower()
                url = str(row[url_idx] or "").strip().lower()
                if name or url:
                    keys.add((name, url))
        return keys

    # 1. Standardized ELIGIBLE_CANDIDATES Sheet
    ws_elig = get_or_create_sheet("ELIGIBLE_CANDIDATES", COLUMNS_ELIGIBLE)
    elig_keys = get_existing_keys(ws_elig, name_idx=0, url_idx=19)
    for c in set3_candidates:
        name = getattr(c, "full_name", "") or ""
        url = getattr(c, "linkedin_url", "") or ""
        key = (name.strip().lower(), url.strip().lower())
        if key not in elig_keys:
            elig_keys.add(key)
            skills_raw = getattr(c, "skills", "") or ""
            skills_str = ", ".join(skills_raw) if isinstance(skills_raw, list) else str(skills_raw)
            visa_val = getattr(c, "visa_status", None) or getattr(c, "work_authorization", None)
            otw_val = "YES (Verified)" if getattr(c, "is_open_to_work", False) else "NO"
            exp_bracket = ">5 years (Senior)" if (getattr(c, "years_of_experience", 0.0) or 0.0) >= 5.0 else "<5 years (Junior/Mid)"
            score_val = getattr(c, "ta_score", None) or getattr(c, "relevance_score", 85)
            ws_elig.append([
                name,
                getattr(c, "current_title", "NOT_AVAILABLE") or "NOT_AVAILABLE",
                getattr(c, "current_company", "NOT_AVAILABLE") or "NOT_AVAILABLE",
                clean_val(getattr(c, "location", "USA"), default="USA"),
                getattr(c, "years_of_experience", 0.0) or 0.0,
                getattr(c, "experience_bracket", exp_bracket),
                getattr(c, "relevant_experience_years", getattr(c, "years_of_experience", 0.0)),
                getattr(c, "primary_domain", getattr(c, "technology", "General Tech")),
                getattr(c, "technology", "Generalist"),
                getattr(c, "relevance_score", 80) or 80,
                skills_str,
                clean_val(getattr(c, "education_level", "Bachelor's"), default="Bachelor's"),
                clean_val(visa_val, default="Not Available"),
                otw_val,
                clean_val(getattr(c, "email", "NOT_AVAILABLE")),
                clean_val(getattr(c, "phone", "NOT_AVAILABLE")),
                clean_val(getattr(c, "signalhire_phone", "Not Available")),
                clean_val(getattr(c, "signalhire_email", "Not Available")),
                clean_val(getattr(c, "signalhire_status", "Not Available")),
                url,
                clean_val(getattr(c, "github_url", "NOT_AVAILABLE")),
                time.strftime("%Y-%m-%dT%H:%M:%SZ")
            ])

    # 2. Standardized NEEDS_REVIEW Sheet
    ws_review = get_or_create_sheet("NEEDS_REVIEW", COLUMNS_NEEDS_REVIEW)
    review_keys = get_existing_keys(ws_review, name_idx=0, url_idx=18)
    for c in set2_candidates:
        name = getattr(c, "full_name", "") or ""
        url = getattr(c, "linkedin_url", "") or ""
        key = (name.strip().lower(), url.strip().lower())
        if key not in elig_keys and key not in review_keys:
            review_keys.add(key)
            visa_val = getattr(c, "visa_status", None) or getattr(c, "work_authorization", None)
            otw_val = "YES (Verified)" if getattr(c, "is_open_to_work", False) else "NO"
            exp_bracket = ">5 years (Senior)" if (getattr(c, "years_of_experience", 0.0) or 0.0) >= 5.0 else "<5 years (Junior/Mid)"
            score_val = getattr(c, "ta_score", None) or getattr(c, "relevance_score", 65)
            ws_review.append([
                name,
                getattr(c, "current_title", "NOT_AVAILABLE") or "NOT_AVAILABLE",
                getattr(c, "current_company", "NOT_AVAILABLE") or "NOT_AVAILABLE",
                clean_val(getattr(c, "location", "USA"), default="USA"),
                getattr(c, "years_of_experience", 0.0) or 0.0,
                getattr(c, "experience_bracket", exp_bracket),
                getattr(c, "years_of_experience", 0.0) or 0.0,
                getattr(c, "technology", "General Tech"),
                "Direct contact details or explicit visa unverified",
                "Review candidate on LinkedIn for contact info and work authorization",
                getattr(c, "relevance_score", 65) or 65,
                clean_val(visa_val, default="Not Available"),
                otw_val,
                clean_val(getattr(c, "email", "NOT_AVAILABLE")),
                clean_val(getattr(c, "phone", "NOT_AVAILABLE")),
                clean_val(getattr(c, "signalhire_phone", "Not Available")),
                clean_val(getattr(c, "signalhire_email", "Not Available")),
                clean_val(getattr(c, "signalhire_status", "Not Available")),
                url,
                clean_val(getattr(c, "github_url", "NOT_AVAILABLE")),
                time.strftime("%Y-%m-%dT%H:%M:%SZ")
            ])

    # 3. Standardized REJECTED_CANDIDATES Sheet
    ws_rej = get_or_create_sheet("REJECTED_CANDIDATES", COLUMNS_REJECTED)
    rej_keys = get_existing_keys(ws_rej, name_idx=0, url_idx=11)
    for stage_name, list_of_rejections in rejected_candidates.items():
        for c in list_of_rejections:
            name = c.get("full_name") or c.get("name") or "Unknown"
            url = c.get("linkedin_url") or c.get("profile_url") or ""
            key = (name.strip().lower(), url.strip().lower())
            if key not in rej_keys:
                rej_keys.add(key)
                yoe = c.get("years_of_experience") or 0.0
                try:
                    yoe_float = float(yoe)
                except (ValueError, TypeError):
                    yoe_float = 0.0
                exp_bracket = ">5 years (Senior)" if yoe_float >= 5.0 else "<5 years (Junior/Mid)"
                primary_domain = c.get("primary_domain") or c.get("technology") or "General Tech"
                otw_val = "YES (Verified)" if c.get("is_open_to_work") else "NO"
                ws_rej.append([
                    name,
                    c.get("current_title") or c.get("position") or "NOT_AVAILABLE",
                    c.get("company") or c.get("current_company") or "NOT_AVAILABLE",
                    clean_val(c.get("location", "USA"), default="USA"),
                    yoe_float,
                    exp_bracket,
                    primary_domain,
                    otw_val,
                    c.get("rejection_stage") or stage_name,
                    c.get("rejection_reason") or "Failed qualification checks",
                    c.get("rejection_reason") or "Failed mandatory criteria",
                    url,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ")
                ])

    # 4. Standardized ALL_RAW_PROFILES Sheet
    ws_raw = get_or_create_sheet("ALL_RAW_PROFILES", COLUMNS_RAW)
    raw_keys = get_existing_keys(ws_raw, name_idx=0, url_idx=16)
    all_candidates_pool = list(set1_candidates) + list(set2_candidates) + list(set3_candidates)
    for c in all_candidates_pool:
        name = getattr(c, "full_name", "") or ""
        url = getattr(c, "linkedin_url", "") or ""
        key = (name.strip().lower(), url.strip().lower())
        if key not in raw_keys:
            raw_keys.add(key)
            ws_raw.append([
                name,
                getattr(c, "headline", "NOT_AVAILABLE") or "NOT_AVAILABLE",
                clean_val(getattr(c, "location", "USA"), default="USA"),
                getattr(c, "current_title", "NOT_AVAILABLE") or "NOT_AVAILABLE",
                getattr(c, "current_company", "NOT_AVAILABLE") or "NOT_AVAILABLE",
                clean_val(getattr(c, "connection_count", "NOT_AVAILABLE")),
                1,
                clean_val(getattr(c, "education", "NOT_AVAILABLE")),
                clean_val(getattr(c, "skills", "NOT_AVAILABLE")),
                clean_val(getattr(c, "certifications", "NOT_AVAILABLE")),
                "NOT_AVAILABLE",
                "NOT_AVAILABLE",
                clean_val(getattr(c, "email", "NOT_AVAILABLE")),
                clean_val(getattr(c, "phone", "NOT_AVAILABLE")),
                clean_val(getattr(c, "website", "NOT_AVAILABLE")),
                url,
                clean_val(getattr(c, "github_url", "NOT_AVAILABLE")),
                clean_val(getattr(c, "pronouns", "NOT_SPECIFIED")),
                clean_val(getattr(c, "age", "NOT_AVAILABLE")),
                time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "{}"
            ])

    # Auto-adjust column widths
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = 0
            for cell in col:
                val = str(cell.value or '')
                if len(val) > max_len:
                    max_len = len(val)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(min(max_len + 3, 50), 12)

    # Save workbook
    retry_delay = 1.0
    for attempt in range(max_retries):
        try:
            wb.save(path)
            logger.info(f"[Excel] Successfully saved database to {path}")
            return
        except PermissionError:
            logger.warning(f"[Excel] PermissionError saving {path}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
        except Exception as e:
            logger.error(f"[Excel] Failed to save database file: {e}")
            break

    try:
        fallback_path = path.replace(".xlsx", f"_LOCKED_{int(time.time())}.xlsx")
        wb.save(fallback_path)
        logger.info(f"[Excel] Successfully saved fallback database file to {fallback_path}")
    except Exception as e:
        logger.critical(f"[Excel] CRITICAL: Could not write database file fallback: {e}")
