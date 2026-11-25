import logging
import json
from datetime import datetime
from typing import Any
from ..database.file_store import get_record, now_iso, save_record

logger = logging.getLogger(__name__)


async def get_or_create_research(llm_provider: Any, role: str) -> dict:
    row = get_record("research", "role", role)
    if row:
        logger.info("Using cached research for role=%s", role)
        return {"cached": True, "updated_at": row["updated_at"], **row["data"]}

    from ..agents.research_agent import run_research_agent
    data = await run_research_agent(llm=llm_provider, target_role=role)
    updated_at = now_iso()
    save_record("research", {"role": role, "data": data, "updated_at": updated_at}, key="role")
    payload = {"cached": False, "updated_at": updated_at, **data}

    return payload
