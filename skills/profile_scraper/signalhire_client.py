"""
signalhire_client.py — Official SignalHire REST API Client.

Enriches AI-qualified candidate profiles with verified direct phone numbers and emails.
Strictly invoked only on qualified candidates to protect paid credits.
"""

import os
import time
import re
from typing import Dict, Any, List, Optional
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class SignalHireClient:
    """
    Client for SignalHire Candidate Search & Enrichment REST API.
    Supports API Key pooling and automatic failover rotation across multiple keys
    when individual trial/free account credits are exhausted (HTTP 402/quota limits).
    """

    BASE_URL = "https://www.signalhire.com/api/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        timeout: float = 30.0,
        callback_url: Optional[str] = None
    ):
        self.timeout = timeout
        self.callback_url = (callback_url or os.getenv("SIGNALHIRE_CALLBACK_URL", "https://example.com/signalhire-callback")).strip()

        # Parse and populate the key pool
        raw_keys: List[str] = []
        if api_keys is not None:
            raw_keys.extend(api_keys)
        if api_key is not None:
            raw_keys.extend(re.split(r'[,;\n]+', api_key))

        # Fallback to environment variables ONLY if neither parameter was explicitly provided
        if api_keys is None and api_key is None:
            env_pool = os.getenv("SIGNALHIRE_API_KEYS") or os.getenv("SIGNALHIRE_API_KEY", "")
            if env_pool:
                raw_keys.extend(re.split(r'[,;\n]+', env_pool))

        # Filter out empty and placeholder keys
        self.api_keys: List[str] = [
            k.strip() for k in raw_keys
            if k and k.strip() and k.strip().lower() not in ("none", "null", "your_signalhire_api_key_here", "")
        ]

        # Deduplicate keys while preserving order
        seen = set()
        deduped = []
        for k in self.api_keys:
            if k not in seen:
                seen.add(k)
                deduped.append(k)
        self.api_keys = deduped

        self.current_key_index: int = 0
        self.exhausted_keys: set = set()
        self.enabled: bool = len(self.api_keys) > 0

        if not self.enabled:
            logger.debug("[SignalHire] No valid SIGNALHIRE_API_KEY found. SignalHire enrichment will be skipped.")
        else:
            logger.info(
                f"[SignalHire] Initialized key pool with {len(self.api_keys)} API key(s). "
                f"Active key: {self._mask_key(self.current_api_key)}"
            )

    @property
    def current_api_key(self) -> str:
        """Returns the currently active API key, or empty string if pool is empty/exhausted."""
        if 0 <= self.current_key_index < len(self.api_keys):
            return self.api_keys[self.current_key_index]
        return ""

    @property
    def api_key(self) -> str:
        """Backwards-compatibility property returning the current active API key."""
        return self.current_api_key

    @api_key.setter
    def api_key(self, val: str) -> None:
        """Backwards-compatibility setter."""
        if val and val.strip().lower() not in ("none", "null", "your_signalhire_api_key_here", ""):
            parsed = [k.strip() for k in re.split(r'[,;\n]+', val) if k.strip()]
            self.api_keys = parsed
            self.current_key_index = 0
            self.exhausted_keys.clear()
            self.enabled = len(self.api_keys) > 0
        else:
            self.api_keys = []
            self.current_key_index = 0
            self.exhausted_keys.clear()
            self.enabled = False

    @staticmethod
    def _mask_key(key: str) -> str:
        """Helper to safely mask API keys for log output."""
        if not key:
            return "None"
        if len(key) <= 8:
            return key[:3] + "***"
        return key[:6] + "..." + key[-3:]

    def _rotate_key(self, reason: str = "out of credits") -> Optional[str]:
        """
        Marks current key as exhausted and advances to the next key in the pool.
        Returns the new active key, or None if all keys are exhausted.
        """
        curr = self.current_api_key
        if curr:
            self.exhausted_keys.add(curr)
        old_idx = self.current_key_index + 1
        total = len(self.api_keys)

        self.current_key_index += 1
        if self.current_key_index < total:
            new_key = self.api_keys[self.current_key_index]
            logger.warning(
                f"[SignalHire] Key {old_idx}/{total} ({self._mask_key(curr)}) {reason}. "
                f"Rotating to Key {self.current_key_index + 1}/{total} ({self._mask_key(new_key)})..."
            )
            return new_key
        else:
            logger.error(
                f"[SignalHire] Key {old_idx}/{total} ({self._mask_key(curr)}) {reason}. "
                f"ALL {total} API key(s) in the SignalHire pool are now exhausted!"
            )
            return None

    def get_pool_status(self) -> Dict[str, Any]:
        """Returns diagnostic status of the API key pool."""
        return {
            "total_keys": len(self.api_keys),
            "active_index": self.current_key_index,
            "remaining_keys": max(0, len(self.api_keys) - self.current_key_index),
            "exhausted_keys_count": len(self.exhausted_keys),
            "current_key_masked": self._mask_key(self.current_api_key),
            "has_available_keys": self.current_key_index < len(self.api_keys)
        }

    def enrich_candidate(
        self,
        linkedin_url: str,
        full_name: Optional[str] = None,
        company: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Queries SignalHire REST API to discover verified phone and email addresses.
        Supports automatic rotation across keys if quota or auth limits are reached.

        Returns:
            Dict containing:
                - status: 'SUCCESS', 'NOT_FOUND', 'OUT_OF_CREDITS', 'API_ERROR', or 'SKIPPED_NO_API_KEY'
                - phone: Primary phone number string or 'Not Available'
                - email: Primary email string or 'Not Available'
                - all_phones: List of all discovered phone numbers
                - all_emails: List of all discovered email addresses
                - raw: Raw response payload for auditability
        """
        clean_url = (linkedin_url or "").strip()
        if not clean_url or "linkedin.com" not in clean_url.lower():
            return {
                "status": "INVALID_URL",
                "phone": "Not Available",
                "email": "Not Available",
                "all_phones": [],
                "all_emails": [],
                "raw": {}
            }

        if not self.enabled or not self.current_api_key:
            return {
                "status": "SKIPPED_NO_API_KEY",
                "phone": "Not Available",
                "email": "Not Available",
                "all_phones": [],
                "all_emails": [],
                "raw": {}
            }

        search_payload: Dict[str, Any] = {
            "items": [clean_url],
            "callbackUrl": self.callback_url
        }
        endpoint = f"{self.BASE_URL}/candidate/search"

        # Rotation loop: advance through pool if keys fail due to credit exhaustion or auth error
        while self.current_api_key:
            active_key = self.current_api_key
            headers = {
                "apikey": active_key,
                "Content-Type": "application/json",
                "User-Agent": "ProfileScrapingAgent/1.0"
            }

            logger.info(
                f"[SignalHire] Requesting contact enrichment for: {clean_url} "
                f"(Key {self.current_key_index + 1}/{len(self.api_keys)}: {self._mask_key(active_key)})"
            )

            max_retries = 3
            backoff = 2.0
            key_rotated = False

            for attempt in range(max_retries):
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        response = client.post(endpoint, json=search_payload, headers=headers)

                    # Check for credit exhaustion in response body or status code 402
                    is_credit_exhausted = (response.status_code == 402)
                    if not is_credit_exhausted and response.text:
                        lower_text = response.text.lower()
                        if any(phrase in lower_text for phrase in ("not enough credits", "out of credits", "insufficient credits", "credits exhausted")):
                            is_credit_exhausted = True

                    # 1. Handle Out of Credits (HTTP 402 / credit exhaustion payload)
                    if is_credit_exhausted:
                        new_key = self._rotate_key(reason="out of credits or subscription expired (HTTP 402)")
                        if new_key:
                            key_rotated = True
                            break  # Break retry loop, retry candidate with next active key
                        return {
                            "status": "OUT_OF_CREDITS",
                            "phone": "Not Available",
                            "email": "Not Available",
                            "all_phones": [],
                            "all_emails": [],
                            "raw": response.json() if response.text else {}
                        }

                    # 2. Handle Rate Limits (HTTP 429)
                    if response.status_code == 429:
                        logger.warning(f"[SignalHire] Rate limited (HTTP 429). Retrying in {backoff}s (attempt {attempt+1}/{max_retries})...")
                        time.sleep(backoff)
                        backoff *= 2.0
                        continue

                    # 3. Handle Bad Request / Auth Failures (401, 403)
                    if response.status_code in (401, 403):
                        logger.error(f"[SignalHire] Authentication failed (HTTP {response.status_code}) for key {self._mask_key(active_key)}.")
                        new_key = self._rotate_key(reason=f"authentication failed (HTTP {response.status_code})")
                        if new_key:
                            key_rotated = True
                            break  # Break retry loop, retry candidate with next active key
                        return {
                            "status": "AUTH_ERROR",
                            "phone": "Not Available",
                            "email": "Not Available",
                            "all_phones": [],
                            "all_emails": [],
                            "raw": {"error": response.text}
                        }

                    if response.status_code not in (200, 201, 202):
                        logger.warning(f"[SignalHire] API error HTTP {response.status_code}: {response.text[:200]}")
                        return {
                            "status": f"HTTP_{response.status_code}",
                            "phone": "Not Available",
                            "email": "Not Available",
                            "all_phones": [],
                            "all_emails": [],
                            "raw": {"error": response.text}
                        }

                    # 4. Parse Successful Response
                    data = response.json()

                    # Check if async requestId was returned
                    if isinstance(data, dict) and "requestId" in data:
                        req_id = str(data["requestId"])
                        data = self._poll_request_results(req_id, clean_url, headers)

                    # Extract Candidate Records
                    return self._extract_contacts_from_payload(data, clean_url)

                except httpx.RequestError as exc:
                    logger.warning(f"[SignalHire] Request exception: {exc}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2.0
                except Exception as e:
                    logger.error(f"[SignalHire] Unexpected error during candidate enrichment: {e}")
                    return {
                        "status": "API_ERROR",
                        "phone": "Not Available",
                        "email": "Not Available",
                        "all_phones": [],
                        "all_emails": [],
                        "raw": {"error": str(e)}
                    }

            if key_rotated:
                continue  # Retry with next key

            return {
                "status": "MAX_RETRIES_EXCEEDED",
                "phone": "Not Available",
                "email": "Not Available",
                "all_phones": [],
                "all_emails": [],
                "raw": {}
            }

        # If loop terminated with all keys exhausted
        return {
            "status": "OUT_OF_CREDITS",
            "phone": "Not Available",
            "email": "Not Available",
            "all_phones": [],
            "all_emails": [],
            "raw": {"error": "All API keys in pool exhausted"}
        }

    def _poll_request_results(self, request_id: str, linkedin_url: str, headers: Dict[str, str], max_polls: int = 10, interval: float = 2.5) -> Any:
        """Polls async search result when candidate request is queued, then retrieves full candidate contacts."""
        poll_url = f"{self.BASE_URL}/candidate/request/{request_id}"
        logger.debug(f"[SignalHire] Polling async request: {request_id}")

        clean_norm = (linkedin_url or "").strip().rstrip("/").lower()
        cand_username = clean_norm.split("/in/")[-1].split("/")[0] if "/in/" in clean_norm else ""

        for poll_idx in range(max_polls):
            time.sleep(interval)
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(poll_url, headers=headers)
                    if resp.status_code == 200:
                        res_data = resp.json()
                        item = {}
                        if isinstance(res_data, dict):
                            # Try exact or normalized URL match
                            for k, v in res_data.items():
                                k_norm = str(k).strip().rstrip("/").lower()
                                if k_norm == clean_norm or (cand_username and cand_username in k_norm):
                                    item = v
                                    break
                            if not item and res_data:
                                first_val = next(iter(res_data.values()), {})
                                if isinstance(first_val, dict):
                                    item = first_val
                        elif isinstance(res_data, list) and len(res_data) > 0:
                            first_item = res_data[0]
                            if isinstance(first_item, dict):
                                item = first_item

                        if isinstance(item, dict):
                            st = str(item.get("status", "")).lower()
                            if st == "success" and item.get("uid"):
                                uid = item["uid"]
                                cand_url = f"{self.BASE_URL}/candidate/{uid}"
                                cand_resp = client.get(cand_url, headers=headers)
                                if cand_resp.status_code == 200:
                                    return cand_resp.json()
                            elif st in ("failed", "error", "not_found"):
                                logger.info(f"[SignalHire] Candidate not found or failed in SignalHire database (status: {st})")
                                return {"status": "NOT_FOUND"}
                            else:
                                logger.debug(f"[SignalHire] Request {request_id} still processing (status: '{st}', poll {poll_idx+1}/{max_polls})...")
            except Exception as ex:
                logger.debug(f"[SignalHire] Polling attempt error: {ex}")

        logger.warning(f"[SignalHire] Async request {request_id} polling timed out after {max_polls * interval}s")
        return {}

    def _extract_contacts_from_payload(self, data: Any, requested_url: str) -> Dict[str, Any]:
        """Extracts and normalizes phone and email items from SignalHire payload, prioritizing mobile numbers."""
        candidate_obj = None

        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict):
                candidate_obj = first_item.get("candidate") or first_item
        elif isinstance(data, dict):
            candidate_obj = data.get("candidate") or data

        if not candidate_obj:
            logger.info(f"[SignalHire] No candidate record returned for {requested_url}")
            return {
                "status": "NOT_FOUND",
                "phone": "Not Available",
                "email": "Not Available",
                "all_phones": [],
                "all_emails": [],
                "raw": data if isinstance(data, dict) else {}
            }

        contacts_list = candidate_obj.get("contacts") or []
        emails: List[str] = []
        phones: List[str] = []

        for item in contacts_list:
            if not isinstance(item, dict):
                continue
            c_type = str(item.get("type", "")).lower()
            sub_type = str(item.get("subType", "")).lower()
            val = str(item.get("value", "")).strip()
            if not val:
                continue

            if c_type in ("email", "work_email", "personal_email") or "@" in val:
                if val not in emails:
                    emails.append(val)
            elif c_type in ("phone", "mobile", "direct", "cell") or any(ch.isdigit() for ch in val):
                # Basic sanity check for phone string
                digits = re.sub(r'\D', '', val)
                if len(digits) >= 7:
                    if sub_type == "mobile" or c_type == "mobile":
                        if val not in phones:
                            phones.insert(0, val)
                    elif val not in phones:
                        phones.append(val)

        # Also inspect top-level fields
        if not emails:
            for em_key in ("email", "primaryEmail", "workEmail"):
                em_val = candidate_obj.get(em_key)
                if em_val and "@" in str(em_val) and str(em_val) not in emails:
                    emails.append(str(em_val).strip())

        if not phones:
            for ph_key in ("phone", "mobile", "mobilePhone", "primaryPhone"):
                ph_val = candidate_obj.get(ph_key)
                if ph_val and any(ch.isdigit() for ch in str(ph_val)):
                    ph_str = str(ph_val).strip()
                    if ph_str not in phones:
                        phones.append(ph_str)

        primary_phone = phones[0] if phones else "Not Available"
        primary_email = emails[0] if emails else "Not Available"

        status = "SUCCESS" if (phones or emails) else "NO_CONTACT_DETAILS"
        logger.info(f"[SignalHire] Enrichment complete: Phone='{primary_phone}', Email='{primary_email}' (Status: {status})")

        return {
            "status": status,
            "phone": primary_phone,
            "email": primary_email,
            "all_phones": phones,
            "all_emails": emails,
            "raw": data if isinstance(data, dict) else {"items": data}
        }
