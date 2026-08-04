import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..database.models import ResearchCache
from ..schemas.schemas import ResearchResponse
from ..config import settings
from ..utils.llm_providers import get_llm_provider
from ..services.research_service import get_or_create_research

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["research"])


@router.get("/research/{role}", response_model=ResearchResponse)
async def research_role(role: str, db: Session = Depends(get_db)):
    try:
        llm = get_llm_provider(settings)
        data = await get_or_create_research(llm_provider=llm, role=role)
        return ResearchResponse(
            role=role,
            skills=data.get("skills", []),
            keywords=data.get("keywords", []),
            requirements=data.get("requirements", []),
            trending_technologies=data.get("trending_technologies", []),
            cached=bool(data.get("cached")),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Research failed for role=%s: %s", role, exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Research failed") from exc
