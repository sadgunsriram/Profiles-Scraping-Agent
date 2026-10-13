"""
campaign_manager.py — Campaign orchestration, pacing, session limits, and role configuration.

Provides dynamic campaign configuration for diverse domains:
- Cybersecurity / IAM
- Cloud Engineering
- SAP
- Network Engineering
- Databricks
- Snowflake
- AI/ML
- Python Engineering
"""

import time
import random
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from loguru import logger

from skills.profile_scraper.eligibility_engine import JobRequirements
from skills.profile_scraper.candidate_models import CandidateQualificationDecision, EligibilityDecision


@dataclass
class CampaignConfig:
    target_role: str
    target_count: int = 10
    batch_size: int = 5
    min_delay_seconds: float = 1.5
    max_delay_seconds: float = 3.5
    cooldown_seconds: float = 8.0
    max_session_profiles: int = 25
    requirements: Optional[JobRequirements] = None


def is_open_to_work_query(query: str) -> bool:
    """Checks if query contains explicit 'open to work' or '#opentowork' terms."""
    clean = (query or "").strip().lower()
    return any(term in clean for term in ["open to work", "#opentowork", "opentowork", "open_to_work", "open-to-work"])


def create_job_requirements(role_query: str, require_open_to_work: Optional[bool] = None) -> JobRequirements:
    """
    Constructs parameterized JobRequirements tailored to the target domain without hardcoding.
    Automatically enables require_open_to_work if role_query contains open to work syntax.
    """
    clean = (role_query or "").strip().lower()
    otw_required = require_open_to_work if require_open_to_work is not None else is_open_to_work_query(role_query)

    if any(k in clean for k in ["cyber", "security", "iam", "infosec", "soc", "penetration", "threat"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=3.0,
            min_total_experience_years=3.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    elif any(k in clean for k in ["cloud", "devops", "sre", "infrastructure", "platform", "aws", "azure", "gcp"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=3.0,
            min_total_experience_years=3.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    elif any(k in clean for k in ["sap", "abap", "hana", "fiori", "erp"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=3.0,
            min_total_experience_years=3.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    elif any(k in clean for k in ["network", "cisco", "routing", "switching", "firewall", "bgp"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=3.0,
            min_total_experience_years=3.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    elif any(k in clean for k in ["databricks", "spark", "delta lake", "pyspark"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=2.0,
            min_total_experience_years=2.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    elif any(k in clean for k in ["snowflake", "data warehouse", "dbt", "dwh"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=2.0,
            min_total_experience_years=2.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    elif any(k in clean for k in ["ai", "machine learning", "ml", "nlp", "computer vision", "llm", "deep learning"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=2.0,
            min_total_experience_years=2.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    elif any(k in clean for k in ["python", "django", "fastapi", "flask"]):
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=2.0,
            min_total_experience_years=2.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=40,
            require_open_to_work=otw_required
        )
    else:
        # Generic role fallback
        return JobRequirements(
            target_role=role_query,
            min_relevant_experience_years=2.0,
            min_total_experience_years=2.0,
            require_us_location=True,
            reject_c2c_recruiters=True,
            min_skill_score=35,
            require_open_to_work=otw_required
        )


class CampaignManager:
    """
    Manages pacing, limits, batching, and metrics for a sourcing campaign run.
    """

    def __init__(
        self,
        target_role: str,
        target_count: int = 10,
        batch_size: int = 5,
        min_delay_seconds: float = 1.5,
        max_delay_seconds: float = 3.5,
        cooldown_seconds: float = 8.0,
        max_session_profiles: int = 25
    ):
        self.config = CampaignConfig(
            target_role=target_role,
            target_count=target_count,
            batch_size=batch_size,
            min_delay_seconds=min_delay_seconds,
            max_delay_seconds=max_delay_seconds,
            cooldown_seconds=cooldown_seconds,
            max_session_profiles=max_session_profiles,
            requirements=create_job_requirements(target_role)
        )
        self.requirements = self.config.requirements
        self.processed_count: int = 0
        self.eligible_count: int = 0
        self.review_count: int = 0
        self.rejected_count: int = 0
        self._batch_counter: int = 0
        self._start_time = time.time()
        logger.info(f"[CampaignManager] Initialized campaign for '{target_role}' (Target: {target_count} ELIGIBLE candidates)")

    def can_process_next(self) -> bool:
        """Verifies if additional candidates should be processed within session limits."""
        if self.eligible_count >= self.config.target_count:
            return False
        if self.processed_count >= self.config.max_session_profiles:
            logger.warning(f"[CampaignManager] Maximum session profile limit ({self.config.max_session_profiles}) reached.")
            return False
        return True

    def is_goal_reached(self) -> bool:
        """Returns True if the target count of ELIGIBLE candidates has been achieved."""
        return self.eligible_count >= self.config.target_count

    def apply_inter_profile_pacing(self) -> None:
        """Applies randomized human-like delay between candidate profile evaluations."""
        delay = round(random.uniform(self.config.min_delay_seconds, self.config.max_delay_seconds), 2)
        logger.debug(f"[CampaignManager] Applying inter-profile pacing: {delay}s...")
        time.sleep(delay)

    def check_batch_cooldown(self) -> None:
        """Checks batch boundary and pauses for cooldown if needed."""
        self._batch_counter += 1
        if self._batch_counter >= self.config.batch_size:
            logger.info(f"[CampaignManager] Batch limit ({self.config.batch_size}) reached. Pausing for cooldown ({self.config.cooldown_seconds}s)...")
            time.sleep(self.config.cooldown_seconds)
            self._batch_counter = 0

    def record_candidate(self, decision: CandidateQualificationDecision) -> None:
        """Updates campaign metrics from evaluation decision."""
        self.processed_count += 1
        if decision.decision == EligibilityDecision.ELIGIBLE:
            self.eligible_count += 1
        elif decision.decision == EligibilityDecision.NEEDS_REVIEW:
            self.review_count += 1
        elif decision.decision == EligibilityDecision.REJECTED:
            self.rejected_count += 1

    def get_summary(self) -> Dict[str, Any]:
        """Returns dictionary of campaign performance metrics."""
        duration_s = round(time.time() - self._start_time, 1)
        return {
            "target_role": self.config.target_role,
            "target_count": self.config.target_count,
            "total_processed": self.processed_count,
            "eligible_count": self.eligible_count,
            "needs_review_count": self.review_count,
            "rejected_count": self.rejected_count,
            "elapsed_seconds": duration_s,
            "goal_reached": self.is_goal_reached()
        }
