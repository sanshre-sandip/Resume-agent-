import logging
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from ..utils.llm_providers import LLMProvider

logger = logging.getLogger(__name__)

STRUCTURING_SYSTEM = (
    "You structure resume JSON for LaTeX rendering. Given optimized data, produce strictly valid JSON "
    "with keys: header, summary, experience, projects, education, skills, certificates. "
    "Never include extra keys or markdown. No commentary."
)


async def run_structuring_agent(llm: LLMProvider, optimized_resume: dict, user_profile: dict) -> dict:
    raw_input = {
        "optimized_resume": optimized_resume,
        "user_profile": user_profile,
    }
    messages = [
        SystemMessage(content=STRUCTURING_SYSTEM),
        HumanMessage(content=f"Structure the following data into resume JSON:\n{raw_input}"),
    ]
    try:
        import json as _json
        raw: str = llm.invoke(messages)
        logger.info("Structuring agent response length: %s", len(raw))
        return _extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Structuring agent failed: %s", exc)
        return {
            "header": user_profile.get("personal_info", {}),
            "summary": optimized_resume.get("summary", ""),
            "experience": optimized_resume.get("optimized_experience", []),
            "projects": optimized_resume.get("optimized_projects", []),
            "education": user_profile.get("education", []),
            "skills": optimized_resume.get("prioritized_skills", []),
            "certificates": user_profile.get("certificates", []),
        }


def _extract_json(raw: str) -> dict:
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("No JSON found in response")
    return __import__("json").loads(m.group(0))
