import logging
import json
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from ..utils.llm_providers import LLMProvider

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM = (
    "You are a job market research agent. Given a target role, extract directly useful resume-building facts only. "
    "Output valid JSON with keys: skills, keywords, requirements, trending_technologies (each an array of strings). "
    "Do not include explanations, commentary, or text outside the JSON object."
)


async def run_research_agent(llm: LLMProvider, target_role: str) -> dict:
    user_text = f"Research the current job market for the role: {target_role}."
    messages = [SystemMessage(content=RESEARCH_SYSTEM), HumanMessage(content=user_text)]
    try:
        raw: str = llm.invoke(messages)
        logger.info("Research agent response length: %s", len(raw))
        data = _extract_json(raw)
        return {
            "skills": data.get("skills", []),
            "keywords": data.get("keywords", []),
            "requirements": data.get("requirements", []),
            "trending_technologies": data.get("trending_technologies", []),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Research agent failed: %s", exc)
        return {"skills": [], "keywords": [], "requirements": [], "trending_technologies": []}


def _extract_json(raw: str) -> dict:
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("No JSON found in response")
    return json.loads(m.group(0))
