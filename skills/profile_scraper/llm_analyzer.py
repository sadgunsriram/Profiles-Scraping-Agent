"""
llm_analyzer.py — LLM-Powered Talent Acquisition Specialist & Profile Analyzer

Evaluates extracted candidate profiles against the target job role using local Ollama.
Acts as a Senior Technical Recruiter / Talent Acquisition Specialist to assess genuine
technical depth, determine seniority, identify red flags, and provide an executive
recruiter fit summary.
"""

import os
import json
import re
from typing import Dict, Any, Optional, List
import httpx
from loguru import logger


class TalentAcquisitionAnalyzer:
    """
    Talent Acquisition Specialist & Profile Analyzer powered by local Ollama.
    """

    def __init__(self):
        self.enabled = os.getenv("LLM_ANALYZER_ENABLED", "true").lower() == "true"
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.primary_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.fallback_model = os.getenv("OLLAMA_FALLBACK_MODEL", "llama3:latest")
        self.min_score = int(os.getenv("LLM_ANALYZER_MIN_SCORE", "50"))
        self.timeout = float(os.getenv("LLM_ANALYZER_TIMEOUT", "45.0"))

    def _build_candidate_summary(self, profile: Dict[str, Any], target_role: str) -> str:
        """Constructs a structured text digest of the candidate's career for the LLM."""
        full_name = profile.get("full_name") or "Candidate"
        headline = profile.get("headline") or ""
        about = profile.get("about") or profile.get("bio") or ""
        skills = profile.get("skills") or []
        skills_str = ", ".join(skills[:25]) if isinstance(skills, list) else str(skills)
        years_exp = profile.get("years_of_experience") or "Unknown"

        # Format experience timeline
        history = profile.get("experience_history") or []
        exp_lines = []
        for i, pos in enumerate(history[:8], start=1):
            title = pos.get("title") or "Role"
            company = pos.get("company_name") or pos.get("company") or "Company"
            start_date = pos.get("start_date") or ""
            end_date = pos.get("end_date") or "Present"
            desc = pos.get("description") or ""
            desc_snippet = desc[:200] + "..." if len(desc) > 200 else desc
            line = f"  [{i}] {title} at {company} ({start_date} - {end_date})"
            if desc_snippet:
                line += f"\n      Description: {desc_snippet}"
            exp_lines.append(line)

        exp_block = "\n".join(exp_lines) if exp_lines else "  No structured experience history provided."

        # Format education
        education = profile.get("education") or []
        edu_lines = [f"  - {str(e)}" for e in education[:4]] if education else ["  Not Available"]
        edu_block = "\n".join(edu_lines)

        prompt_body = f"""TARGET ROLE: {target_role}

CANDIDATE INFORMATION:
Name: {full_name}
Headline: {headline}
Claimed Years of Experience: {years_exp}
About / Summary: {about[:400]}

WORK EXPERIENCE HISTORY:
{exp_block}

SKILLS:
{skills_str or 'Not Available'}

EDUCATION:
{edu_block}
"""
        return prompt_body

    def _call_ollama_chat(self, model: str, prompt_body: str) -> Optional[Dict[str, Any]]:
        """Sends chat request to local Ollama with JSON mode."""
        system_instruction = (
            "You are an elite Senior Technical Recruiter and Talent Acquisition Specialist.\n"
            "Your job is to thoroughly evaluate candidate LinkedIn profiles against the target job role.\n\n"
            "Evaluation Rules:\n"
            "1. Genuine Practitioner Check: Determine if the candidate is an actual hands-on practitioner "
            "for the target role. Strictly REJECT candidates whose primary profession is recruitment, HR, "
            "sales, account management, marketing, legal, or completely unrelated technical domains (e.g. "
            "rejecting a mobile app developer when searching for Network Engineer unless they have real networking experience).\n"
            "2. Score (0-100): Rate candidate fit. 80-100 = Strong Match, 50-79 = Qualified Match, 0-49 = Rejected/Unqualified.\n"
            "3. Seniority Level: Classify into 'Junior', 'Mid-Level', 'Senior', 'Lead / Principal', or 'Architect'.\n"
            "4. TA Fit Summary: Write a concise 1-2 sentence executive recruiter synopsis explaining why they match "
            "or do not match, citing specific technologies and companies.\n"
            "5. Key Strengths: List 3-6 top technical tools/skills proven by their experience.\n"
            "6. Output MUST be valid JSON adhering exactly to the specified format without extra text."
        )

        user_prompt = (
            f"{prompt_body}\n\n"
            "Analyze this candidate as a Talent Acquisition Specialist. Output ONLY a valid JSON object in this exact schema:\n"
            "{\n"
            '  "decision": "QUALIFIED" or "REJECTED",\n'
            '  "relevance_score": <integer 0-100>,\n'
            '  "seniority_level": "Junior" | "Mid-Level" | "Senior" | "Lead / Principal" | "Architect",\n'
            '  "ta_fit_summary": "<1-2 sentence professional recruiter evaluation>",\n'
            '  "key_strengths": ["<strength1>", "<strength2>", "<strength3>"],\n'
            '  "red_flags": "<any concerns such as job hopping or title inflation, or \'None\'>",\n'
            '  "rejection_reason": "<explanation if REJECTED, or null if QUALIFIED>"\n'
            "}"
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "format": "json",
            "keep_alive": "15m",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 200
            }
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.ollama_url}/api/chat", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("message", {}).get("content", "")
                    parsed = json.loads(content)
                    return parsed
                else:
                    logger.warning(f"[TA Analyzer] Ollama {model} returned HTTP {res.status_code}: {res.text[:150]}")
                    return None
        except Exception as e:
            logger.warning(f"[TA Analyzer] Ollama request to {model} failed: {e}")
            return None

    def evaluate_candidate(self, profile: Dict[str, Any], target_role: str) -> Dict[str, Any]:
        """
        Main entrypoint: Evaluates a candidate using local Ollama.
        Returns parsed evaluation dictionary with guaranteed fallback.
        """
        if not self.enabled:
            logger.debug("[TA Analyzer] LLM Analyzer disabled via configuration.")
            return self._default_fallback(profile, "LLM Analyzer disabled")

        prompt_body = self._build_candidate_summary(profile, target_role)

        # 1. Attempt with primary model (e.g. qwen2.5:7b)
        logger.info(f"[TA Analyzer] Evaluating candidate '{profile.get('full_name')}' for '{target_role}' using Ollama model '{self.primary_model}'...")
        result = self._call_ollama_chat(self.primary_model, prompt_body)

        # 2. Fallback to secondary model if primary fails (e.g. llama3:latest)
        if not result and self.fallback_model and self.fallback_model != self.primary_model:
            logger.info(f"[TA Analyzer] Primary model failed. Retrying with fallback model '{self.fallback_model}'...")
            result = self._call_ollama_chat(self.fallback_model, prompt_body)

        # 3. Handle successful response
        if result and isinstance(result, dict):
            decision = str(result.get("decision", "QUALIFIED")).upper()
            score = int(result.get("relevance_score", 70))
            seniority = str(result.get("seniority_level", "Mid-Level"))
            summary = str(result.get("ta_fit_summary", "Candidate meets role requirements."))
            strengths = result.get("key_strengths", [])
            strengths_str = ", ".join(strengths) if isinstance(strengths, list) else str(strengths)
            rejection_reason = result.get("rejection_reason")

            # Validate decision against minimum score threshold
            if score < self.min_score and decision != "REJECTED":
                decision = "REJECTED"
                if not rejection_reason:
                    rejection_reason = f"Relevance score ({score}/100) below minimum threshold ({self.min_score})"

            logger.info(f"[TA Analyzer] Candidate '{profile.get('full_name')}': Decision={decision}, Score={score}, Seniority={seniority}")

            return {
                "decision": decision,
                "score": score,
                "seniority": seniority,
                "fit_summary": summary,
                "key_strengths": strengths_str,
                "red_flags": str(result.get("red_flags", "None")),
                "rejection_reason": rejection_reason,
                "model_used": self.primary_model,
                "analyzer_status": "SUCCESS"
            }

        # 4. Graceful Fallback if Ollama is unreachable
        logger.warning(f"[TA Analyzer] Ollama evaluation failed. Utilizing graceful heuristic fallback.")
        return self._default_fallback(profile, "Ollama service unavailable or timed out")

    def _default_fallback(self, profile: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """Provides safe fallback evaluation when LLM cannot be reached."""
        return {
            "decision": "QUALIFIED",
            "score": 75,
            "seniority": "Mid-Level",
            "fit_summary": f"Automated qualification fallback: {reason}.",
            "key_strengths": str(profile.get("skills", "Not Available")),
            "red_flags": "None",
            "rejection_reason": None,
            "model_used": "heuristic_fallback",
            "analyzer_status": "FALLBACK"
        }
