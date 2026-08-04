import logging
import json
import os
from datetime import datetime
from typing import Any
from ..database.session import get_db
from ..database.models import ResearchCache

logger = logging.getLogger(__name__)


async def get_or_create_research(llm_provider: Any, role: str) -> dict:
    with next(get_db()) as db:
        row = db.query(ResearchCache).filter(ResearchCache.role == role).first()
        if row:
            logger.info("Using cached research for role=%s", role)
            return {"cached": True, "updated_at": row.updated_at.isoformat(), **json.loads(row.research_json)}

    from ..agents.research_agent import run_research_agent
    data = await run_research_agent(llm=llm_provider, target_role=role)
    payload = {"cached": False, "updated_at": datetime.utcnow().isoformat(), **data}

    with next(get_db()) as db:
        existing = db.query(ResearchCache).filter(ResearchCache.role == role).first()
        if existing:
            existing.research_json = json.dumps(data)
        else:
            db.add(ResearchCache(role=role, research_json=json.dumps(data), updated_at=datetime.utcnow()))
        db.commit()

    return payload
