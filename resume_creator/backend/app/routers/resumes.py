import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from ..database.file_store import get_record, now_iso, save_record
from ..schemas.schemas import CreateResumeRequest, ResumeDetailResponse, TemplateResponse
from ..config import settings
from ..graph.resume_graph import build_resume_graph
from ..utils.renderer import list_available_templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["resume"])


def _detail(record: dict) -> ResumeDetailResponse:
    return ResumeDetailResponse(
        id=record["id"], user_id=record["user_id"], target_role=record["target_role"],
        template_name=record["template_name"], structured_data=record.get("structured_data"),
        latex_content=record.get("latex_content"), pdf_path=record.get("pdf_path"),
        docx_path=record.get("docx_path"), created_at=datetime.fromisoformat(record["created_at"]),
    )


@router.post("/resume/create", response_model=ResumeDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_resume(payload: CreateResumeRequest):
    user = get_record("users", "email", payload.user_profile.email)
    if user is None:
        user = {"id": str(uuid.uuid4()), "name": payload.user_profile.full_name,
                "email": payload.user_profile.email, "created_at": now_iso()}
        save_record("users", user)

    resume = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "target_role": payload.target_role,
        "template_name": payload.template_name or "modern", "pdf_path": "#pending",
        "docx_path": "#pending", "structured_data": None, "latex_content": None,
        "created_at": now_iso(),
    }
    save_record("resumes", resume)
    try:
        graph = build_resume_graph()
        graph_input = {**payload.model_dump(), "user_id": resume["user_id"]}
        final_state = await graph.ainvoke(
            {"input": graph_input}, config={"configurable": {"thread_id": resume["id"]}}
        )
        resume["structured_data"] = final_state.get("structured_data")
        resume["latex_content"] = final_state.get("latex_content")
        resume["pdf_path"] = final_state.get("pdf_path") or None
        resume["docx_path"] = final_state.get("docx_path") or None
        save_record("resumes", resume)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Resume generation workflow failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Resume generation failed: {exc}") from exc
    return _detail(resume)


@router.get("/resume/{resume_id}", response_model=ResumeDetailResponse)
def get_resume(resume_id: str):
    resume = get_record("resumes", "id", resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return _detail(resume)


def _artifact(resume_id: str, kind: str):
    resume = get_record("resumes", "id", resume_id)
    path = resume.get(f"{kind}_path") if resume else None
    if not path or path == "#pending" or not __import__("os").path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{kind.upper()} not available")
    media = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media, filename=f"resume_{resume_id}.{kind}")


@router.get("/resume/{resume_id}/pdf")
def get_resume_pdf(resume_id: str):
    return _artifact(resume_id, "pdf")


@router.get("/resume/{resume_id}/docx")
def get_resume_docx(resume_id: str):
    return _artifact(resume_id, "docx")


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates():
    items = list_available_templates(settings.template_dir)
    return [TemplateResponse(name=i["name"], description=i["filename"], available=i["available"]) for i in items]


