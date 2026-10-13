"""
workflow_state.py — Granular profile processing state tracker for candidate harvesting.

Tracks discrete stages during the candidate lifecycle:
- PROFILE_OPENED
- PAGE_READY
- INTRO_PROCESSED
- CONTACT_INFO_PROCESSED
- ABOUT_PROCESSED
- EXPERIENCE_PROCESSED
- EDUCATION_PROCESSED
- ADDITIONAL_SECTIONS_PROCESSED
- ANALYSIS_COMPLETED
- ELIGIBILITY_EVALUATED
- PERSISTED
- PROFILE_COMPLETED
- PROFILE_FAILED
"""

import time
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger


class WorkflowStage(str, Enum):
    DISCOVERY = "DISCOVERY"
    PROFILE_OPENED = "PROFILE_OPENED"
    PAGE_READY = "PAGE_READY"
    INTRO_PROCESSED = "INTRO_PROCESSED"
    CONTACT_INFO_PROCESSED = "CONTACT_INFO_PROCESSED"
    ABOUT_PROCESSED = "ABOUT_PROCESSED"
    EXPERIENCE_PROCESSED = "EXPERIENCE_PROCESSED"
    EDUCATION_PROCESSED = "EDUCATION_PROCESSED"
    ADDITIONAL_SECTIONS_PROCESSED = "ADDITIONAL_SECTIONS_PROCESSED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    ELIGIBILITY_EVALUATED = "ELIGIBILITY_EVALUATED"
    PERSISTED = "PERSISTED"
    PROFILE_COMPLETED = "PROFILE_COMPLETED"
    PROFILE_FAILED = "PROFILE_FAILED"


class WorkflowStateTracker:
    """
    State tracking manager for a single candidate profile lifecycle.
    Embeds full state transition diagnostics into the candidate payload.
    """

    def __init__(self, profile_url: str = ""):
        self.profile_url = profile_url
        self.current_stage: WorkflowStage = WorkflowStage.DISCOVERY
        self.start_timestamp: str = datetime.utcnow().isoformat()
        self.transitions: List[Dict[str, Any]] = []
        self._start_perf = time.perf_counter()
        self.record_transition(WorkflowStage.DISCOVERY, "Candidate profile identified for sourcing")

    def record_transition(self, stage: WorkflowStage, details: str = "") -> None:
        """Records transition to a new workflow stage."""
        now = datetime.utcnow().isoformat()
        elapsed_s = round(time.perf_counter() - self._start_perf, 3)
        self.current_stage = stage
        self.transitions.append({
            "stage": stage.value,
            "timestamp": now,
            "elapsed_seconds": elapsed_s,
            "details": details
        })
        logger.debug(f"[WorkflowState] [{self.profile_url}] -> {stage.value}: {details}")

    def fail(self, reason: str) -> None:
        """Marks profile processing as failed with reason."""
        self.record_transition(WorkflowStage.PROFILE_FAILED, reason)

    def complete(self, details: str = "Profile harvested and persisted successfully") -> None:
        """Marks profile processing as completed."""
        self.record_transition(WorkflowStage.PROFILE_COMPLETED, details)

    def to_dict(self) -> Dict[str, Any]:
        """Returns JSON-serializable state tracker history."""
        return {
            "profile_url": self.profile_url,
            "current_stage": self.current_stage.value,
            "start_timestamp": self.start_timestamp,
            "total_elapsed_seconds": round(time.perf_counter() - self._start_perf, 3),
            "transitions_count": len(self.transitions),
            "transitions": self.transitions
        }
