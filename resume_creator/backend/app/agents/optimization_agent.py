import json
import logging
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from ..utils.llm_providers import LLMProvider

logger = logging.getLogger(__name__)

OPTIMIZATION_SYSTEM = (
    "You are a senior resume optimization agent and career coach. Improve the user's resume data "
    "to match the target role while keeping content truthful and evidence-based. Never invent experience.\n\n"
    "Rules:\n"
    "- Create a concise professional summary (max 4 sentences).\n"
    "- Prioritize skills matching research keywords.\n"
    "- Rewrite project/experience descriptions using strong action verbs and measurable impact.\n"
    "- Ensure ATS-friendly phrasing with standard section titles and simple bullet points.\n"
    "Return ONLY valid JSON with keys: summary, optimized_experience, optimized_projects, prioritized_skills, professional_title, ats_score_estimate."
)


async def run_optimization_agent(llm: LLMProvider, user_profile: dict, research_data: dict) -> dict:
    prompt = (
        "Target role: {target_role}\n"
        "User profile: {user_profile}\n"
        "Job research data: {research_data}\n\n"
        "Optimize the resume now."
    )
    template = PromptTemplate.from_template(prompt)
    messages = [
        SystemMessage(content=OPTIMIZATION_SYSTEM),
        HumanMessage(content=template.format(target_role=user_profile.get("target_role", ""), user_profile=json.dumps(user_profile, ensure_ascii=False), research_data=json.dumps(research_data, ensure_ascii=False))),
    ]
    try:
        import json as _json
        raw: str = llm.invoke(messages)
        logger.info("Optimization agent response length: %s", len(raw))
        data = _extract_json(raw)
        return {
            "summary": data.get("summary", ""),
            "optimized_experience": data.get("optimized_experience", user_profile.get("experience", [])),
            "optimized_projects": data.get("optimized_projects", user_profile.get("projects", [])),
            "prioritized_skills": data.get("prioritized_skills", user_profile.get("skills", [])),
            "professional_title": data.get("professional_title", user_profile.get("target_role", "")),
            "ats_score_estimate": data.get("ats_score_estimate", "Good"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Optimization agent failed: %s", exc)
        return {
            "summary": "",
            "optimized_experience": user_profile.get("experience", []),
            "optimized_projects": user_profile.get("projects", []),
            "prioritized_skills": user_profile.get("skills", []),
            "professional_title": user_profile.get("target_role", ""),
            "ats_score_estimate": "Good",
        }


def _extract_json(raw: str) -> dict:
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("No JSON found in response")
    return __import__("json").loads(m.group(0))
