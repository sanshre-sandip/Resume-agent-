import json
import logging
import os
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..database.models import User, Resume
from ..schemas.schemas import CreateResumeRequest, ResumeResponse, ResumeDetailResponse, TemplateResponse
from ..config import settings
from ..graph.resume_graph import build_resume_graph
from ..utils.renderer import list_available_templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["resume"])


@router.post("/resume/create", response_model=ResumeDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_resume(payload: CreateResumeRequest, db: Session = Depends(get_db)):
    import uuid

    try:
        user = db.query(User).filter(User.email == payload.user_profile.email).first()
        if not user:
            user = User(id=str(uuid.uuid4()), name=payload.user_profile.full_name, email=payload.user_profile.email)
            db.add(user)
            db.flush()
        resume = Resume(
            id=str(uuid.uuid4()),
            user_id=user.id,
            target_role=payload.target_role,
            template_name=payload.template_name or "modern",
            pdf_path="#pending",
            docx_path="#pending",
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Create resume (persist) failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        graph = build_resume_graph()
        graph_input = {**payload.model_dump(), "user_id": resume.user_id}
        final_state = await graph.ainvoke(
            {"input": graph_input},
            config={"configurable": {"thread_id": resume.id}},
        )
        structured = final_state.get("structured_data")
        resume.structured_data = json.dumps(structured) if structured else None
        resume.latex_content = final_state.get("latex_content")
        resume.pdf_path = final_state.get("pdf_path") or None
        resume.docx_path = final_state.get("docx_path") or None
        db.add(resume)
        db.commit()
        db.refresh(resume)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Resume generation workflow failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Resume generation failed: {exc}",
        ) from exc

    return ResumeDetailResponse(
        id=resume.id,
        user_id=resume.user_id,
        target_role=resume.target_role,
        template_name=resume.template_name,
        structured_data=json.loads(resume.structured_data) if resume.structured_data else None,
        latex_content=resume.latex_content,
        pdf_path=resume.pdf_path,
        docx_path=resume.docx_path,
        created_at=resume.created_at,
    )


@router.get("/resume/{resume_id}", response_model=ResumeDetailResponse)
def get_resume(resume_id: str, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    structured = json.loads(resume.structured_data) if resume.structured_data else None
    return ResumeDetailResponse(
        id=resume.id,
        user_id=resume.user_id,
        target_role=resume.target_role,
        template_name=resume.template_name,
        structured_data=structured,
        latex_content=resume.latex_content,
        pdf_path=resume.pdf_path,
        docx_path=resume.docx_path,
        created_at=resume.created_at,
    )


@router.get("/resume/{resume_id}/pdf")
def get_resume_pdf(resume_id: str, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume or not resume.pdf_path or resume.pdf_path == "#pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF not available")
    from fastapi.responses import FileResponse
    return FileResponse(resume.pdf_path, media_type="application/pdf", filename=f"resume_{resume_id}.pdf")


@router.get("/resume/{resume_id}/docx")
def get_resume_docx(resume_id: str, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume or not resume.docx_path or resume.docx_path == "#pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DOCX not available")
    from fastapi.responses import FileResponse
    return FileResponse(resume.docx_path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=f"resume_{resume_id}.docx")


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates():
    items = list_available_templates(settings.template_dir)
    return [TemplateResponse(name=i["name"], description=i["filename"], available=i["available"]) for i in items]


@router.get("/history", response_model=list[ResumeResponse])
def get_history(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Resume).order_by(Resume.created_at.desc()).limit(limit).all()
    return [
        ResumeResponse(
            id=r.id,
            user_id=r.user_id,
            target_role=r.target_role,
            template_name=r.template_name,
            pdf_path=r.pdf_path,
            docx_path=r.docx_path,
            created_at=r.created_at,
        )
        for r in rows
    ]
