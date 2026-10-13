"""
database_repository.py — Relational Database Persistence Layer for Eligible Candidates.

Maintains the `eligible_candidates` table in PostgreSQL (or SQLite for local fallback),
providing atomic deduplication and upserts based on `linkedin_url`.
Designed to fail gracefully: if the database is unreachable or disabled, scraping continues uninterrupted.
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
from loguru import logger
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    select,
    func
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from skills.profile_scraper.candidate_models import (
    CandidateQualificationDecision,
    EligibilityDecision,
    NormalizedCandidateProfile,
    CandidateAnalysisResult
)

load_dotenv()

Base = declarative_base()


class EligibleCandidateModel(Base):
    """SQLAlchemy model for fully qualified eligible candidates."""
    __tablename__ = "eligible_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    linkedin_url = Column(String(512), unique=True, nullable=False, index=True)
    full_name = Column(String(256), nullable=False)
    current_title = Column(String(256), nullable=True)
    company = Column(String(256), nullable=True)
    location = Column(String(256), nullable=True)

    # Experience & Qualifications
    total_experience_years = Column(Float, nullable=True)
    experience_bracket = Column(String(64), nullable=True)
    relevant_tech_years = Column(Float, nullable=True)
    primary_domain = Column(String(128), nullable=True, index=True)
    tech_specialization = Column(String(256), nullable=True)
    skill_relevance_score = Column(Integer, nullable=True)
    top_skills = Column(Text, nullable=True)
    highest_education = Column(String(128), nullable=True)
    work_authorization = Column(String(128), nullable=True)
    is_open_to_work = Column(Boolean, default=True)

    # Direct & Verified Contact Info
    email = Column(String(256), nullable=True)
    phone = Column(String(64), nullable=True)
    signalhire_phone = Column(String(64), nullable=True)
    signalhire_email = Column(String(256), nullable=True)
    signalhire_status = Column(String(64), nullable=True)
    github_url = Column(String(512), nullable=True)

    # Audit & Tracking
    date_qualified = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    full_profile_json = Column(Text, nullable=True)


class DatabaseCandidateRepository:
    """
    Manages persistent storage and atomic upserting of eligible candidates into PostgreSQL / SQLite.
    """

    def __init__(self, db_url: Optional[str] = None, enabled: Optional[bool] = None):
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = os.getenv("DATABASE_ENABLED", "false").lower() in ("true", "1", "yes")

        raw_url = (db_url or os.getenv("DATABASE_URL", "")).strip()

        # Normalize URL prefixes for SQLAlchemy if needed (e.g. postgres:// -> postgresql://)
        if raw_url.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql://", 1)

        self.db_url = raw_url
        self.engine = None
        self.SessionLocal = None
        self.dialect_name = ""

        if not self.enabled or not self.db_url:
            logger.debug("[DatabaseRepository] Database persistence is disabled or DATABASE_URL not set.")
            self.enabled = False
            return

        try:
            # Configure engine with reasonable pool and timeout defaults
            if "sqlite" in self.db_url:
                self.engine = create_engine(
                    self.db_url,
                    connect_args={"check_same_thread": False}
                )
            else:
                self.engine = create_engine(
                    self.db_url,
                    pool_pre_ping=True,
                    pool_recycle=300
                )

            self.dialect_name = self.engine.dialect.name
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            self._create_tables_if_needed()
            logger.info(f"[DatabaseRepository] Successfully connected to {self.dialect_name.upper()} database.")
        except Exception as e:
            logger.error(f"[DatabaseRepository] Failed to initialize database connection: {e}")
            self.enabled = False

    def _create_tables_if_needed(self):
        """Creates table schema if it doesn't already exist."""
        if self.engine:
            Base.metadata.create_all(bind=self.engine)

    def save_eligible_candidate(self, decision: CandidateQualificationDecision) -> bool:
        """
        Atomically saves or updates an ELIGIBLE candidate in the database.
        Skips non-eligible candidates.

        Returns True if saved/updated, False otherwise.
        """
        if not self.enabled or not self.engine or not self.SessionLocal:
            return False

        if decision.decision != EligibilityDecision.ELIGIBLE:
            logger.debug(f"[DatabaseRepository] Skipping candidate '{decision.candidate.full_name}' - decision is {decision.decision.value}")
            return False

        cand = decision.candidate
        analysis = decision.analysis

        # Prepare values dictionary
        record_values = {
            "linkedin_url": cand.linkedin_url.strip(),
            "full_name": cand.full_name.strip(),
            "current_title": cand.current_title or cand.headline or "NOT_AVAILABLE",
            "company": cand.current_company or "NOT_AVAILABLE",
            "location": cand.location or "NOT_AVAILABLE",
            "total_experience_years": getattr(analysis, "total_experience_years", 0.0),
            "experience_bracket": getattr(analysis, "experience_bracket", "NOT_AVAILABLE"),
            "relevant_tech_years": getattr(analysis, "relevant_technology_years", 0.0),
            "primary_domain": getattr(analysis, "primary_professional_domain", "NOT_AVAILABLE"),
            "tech_specialization": getattr(analysis, "technology_specialization", "NOT_AVAILABLE"),
            "skill_relevance_score": getattr(analysis, "skill_relevance_score", 0),
            "top_skills": ", ".join(cand.skills[:10]) if cand.skills else "NOT_AVAILABLE",
            "highest_education": getattr(analysis, "highest_education", "NOT_AVAILABLE"),
            "work_authorization": getattr(analysis, "work_authorization", "NOT_AVAILABLE"),
            "is_open_to_work": cand.is_open_to_work,
            "email": cand.email if cand.email not in ("NOT_AVAILABLE", "Not Available", "") else None,
            "phone": cand.phone if cand.phone not in ("NOT_AVAILABLE", "Not Available", "") else None,
            "signalhire_phone": getattr(cand, "signalhire_phone", None),
            "signalhire_email": getattr(cand, "signalhire_email", None),
            "signalhire_status": getattr(cand, "signalhire_status", "NOT_AVAILABLE"),
            "github_url": cand.github_url if cand.github_url not in ("NOT_AVAILABLE", "Not Available", "") else None,
            "date_qualified": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "full_profile_json": json.dumps(cand.to_dict(), default=str)
        }

        try:
            with self.SessionLocal() as session:
                if self.dialect_name == "postgresql":
                    # Native PostgreSQL Upsert
                    stmt = pg_insert(EligibleCandidateModel).values(**record_values)
                    update_dict = {
                        k: v for k, v in record_values.items()
                        if k not in ("id", "linkedin_url", "date_qualified")
                    }
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["linkedin_url"],
                        set_=update_dict
                    )
                    session.execute(stmt)
                    session.commit()
                elif self.dialect_name == "sqlite":
                    # Native SQLite Upsert
                    stmt = sqlite_insert(EligibleCandidateModel).values(**record_values)
                    update_dict = {
                        k: v for k, v in record_values.items()
                        if k not in ("id", "linkedin_url", "date_qualified")
                    }
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["linkedin_url"],
                        set_=update_dict
                    )
                    session.execute(stmt)
                    session.commit()
                else:
                    # Generic fallback upsert (Query then Insert/Update)
                    existing = session.query(EligibleCandidateModel).filter_by(linkedin_url=record_values["linkedin_url"]).first()
                    if existing:
                        for k, v in record_values.items():
                            if k not in ("id", "linkedin_url", "date_qualified"):
                                setattr(existing, k, v)
                    else:
                        new_candidate = EligibleCandidateModel(**record_values)
                        session.add(new_candidate)
                    session.commit()

            logger.info(f"[DatabaseRepository] Successfully persisted ELIGIBLE candidate '{cand.full_name}' to table 'eligible_candidates'.")
            return True

        except Exception as e:
            logger.error(f"[DatabaseRepository] Error saving candidate '{cand.full_name}' to database: {e}")
            return False

    def get_candidate_by_url(self, linkedin_url: str) -> Optional[Dict[str, Any]]:
        """Retrieves a candidate by linkedin_url."""
        if not self.enabled or not self.SessionLocal:
            return None

        clean_url = (linkedin_url or "").strip()
        try:
            with self.SessionLocal() as session:
                stmt = select(EligibleCandidateModel).filter_by(linkedin_url=clean_url)
                result = session.execute(stmt).scalars().first()
                if not result:
                    return None
                return {
                    col.name: getattr(result, col.name)
                    for col in EligibleCandidateModel.__table__.columns
                }
        except Exception as e:
            logger.error(f"[DatabaseRepository] Error retrieving candidate by URL: {e}")
            return None

    def get_eligible_count(self) -> int:
        """Returns the total number of eligible candidates in the database."""
        if not self.enabled or not self.SessionLocal:
            return 0

        try:
            with self.SessionLocal() as session:
                count = session.query(func.count(EligibleCandidateModel.id)).scalar()
                return count or 0
        except Exception as e:
            logger.error(f"[DatabaseRepository] Error querying eligible candidate count: {e}")
            return 0
