import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from langchain_core.messages import HumanMessage, SystemMessage

from ..agents.export_agent import persist_artifacts
from ..agents.resume_editor_agent import edit_resume
from ..config import settings
from ..database.file_store import get_record, list_records, now_iso, save_record
from ..graph.resume_graph import build_resume_graph
from ..schemas.schemas import (
    AIConfig,
    CreateResumeRequest,
    GenerateLayoutsRequest,
    LayoutProposal,
    ResumeChatRequest,
    ResumeChatResponse,
    ResumeDetailResponse,
    ResumeSummaryResponse,
    SavedLayoutResponse,
    TemplateResponse,
)
from ..services.resume_service import build_context, normalize_style
from ..utils.llm_providers import get_llm_provider
from ..utils.renderer import list_available_templates
from ..agents.rendering_agent import LaTeXRenderer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["resume"])

BUILT_IN_LAYOUTS = [
    {
        "id": "modern-blue", "name": "Modern Blue", "description": "Clean headings with a vivid blue accent.",
        "template_name": "modern", "style": normalize_style({"accent_color": "1F6FEB"}), "built_in": True,
    },
    {
        "id": "classic-teal", "name": "Classic Teal", "description": "Centered header and polished teal section titles.",
        "template_name": "professional",
        "style": normalize_style({"accent_color": "0F766E", "header_alignment": "center", "section_style": "accent-rule"}),
        "built_in": True,
    },
    {
        "id": "simple-violet", "name": "Simple Violet", "description": "A calm, spacious format with minimal dividers.",
        "template_name": "simple",
        "style": normalize_style({"accent_color": "6F42C1", "font_size": "12pt", "section_style": "minimal", "spacing": "airy"}),
        "built_in": True,
    },
]


def _detail(record: dict[str, Any]) -> ResumeDetailResponse:
    return ResumeDetailResponse(
        id=record["id"], file_name=record.get("file_name", "My resume"),
        user_id=record["user_id"], target_role=record["target_role"],
        template_name=record.get("template_name", "modern"),
        structured_data=record.get("structured_data"), latex_content=record.get("latex_content"),
        pdf_path=record.get("pdf_path"), docx_path=record.get("docx_path"),
        source_data=record.get("source_data"), style=record.get("style"),
        layout_id=record.get("layout_id"),
        created_at=datetime.fromisoformat(record["created_at"]),
        updated_at=datetime.fromisoformat(record.get("updated_at", record["created_at"])),
    )


def _check_unique_name(file_name: str, exclude_id: str | None = None) -> None:
    duplicate = next(
        (row for row in list_records("resumes")
         if row.get("file_name", "").casefold() == file_name.casefold() and row.get("id") != exclude_id),
        None,
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="That resume file name already exists. Choose a different name.")


def _profile_id() -> str:
    return "single-owner"


async def _generate_new_content(payload: CreateResumeRequest, record: dict[str, Any]) -> dict[str, Any]:
    graph_input = payload.model_dump()
    graph_input.update({"user_id": record["user_id"], "resume_id": record["id"]})
    graph = build_resume_graph()
    final_state = await graph.ainvoke(
        {"input": graph_input}, config={"configurable": {"thread_id": record["id"]}}
    )
    record["structured_data"] = final_state.get("structured_data")
    record["latex_content"] = final_state.get("latex_content")
    record["pdf_path"] = final_state.get("pdf_path")
    record["docx_path"] = final_state.get("docx_path")
    return record


def _safe_error(exc: Exception, api_key: str = "") -> str:
    message = str(exc) or "The AI request could not be completed."
    return message.replace(api_key, "[hidden] ") if api_key else message


def _render_record(record: dict[str, Any]) -> None:
    data = record.get("structured_data") or {}
    style = normalize_style(record.get("style"))
    template_name = record.get("template_name", "modern")
    context = build_context(data, None, style)
    latex = LaTeXRenderer(template_dir=settings.template_dir).render(template_name, context)
    artifacts = persist_artifacts(
        tex_content=latex,
        user_id=record["user_id"],
        resume_id=record["id"],
        generated_dir=settings.generated_dir,
    )
    record["latex_content"] = latex
    record["pdf_path"] = artifacts.get("pdf_path")
    record["docx_path"] = artifacts.get("docx_path")
    record["updated_at"] = now_iso()
    save_record("resumes", record)


def _save_layout_suggestions(proposals: list[dict[str, Any]]) -> list[SavedLayoutResponse]:
    saved: list[SavedLayoutResponse] = []
    for item in proposals[:3]:
        try:
            proposal = LayoutProposal.model_validate(item)
        except Exception:
            continue
        layout = {
            "id": str(uuid.uuid4()),
            "name": proposal.name.strip(),
            "description": proposal.description.strip(),
            "template_name": proposal.template_name,
            "style": normalize_style(proposal.style),
            "built_in": False,
            "created_at": now_iso(),
        }
        save_record("layouts", layout)
        saved.append(SavedLayoutResponse(**layout))
    return saved


@router.post("/resume/create", response_model=ResumeDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_resume(payload: CreateResumeRequest):
    _check_unique_name(payload.file_name)
    owner = get_record("users", "id", _profile_id()) or {
        "id": _profile_id(), "created_at": now_iso(),
    }
    owner.update({"name": payload.user_profile.full_name, "email": str(payload.user_profile.email), "updated_at": now_iso()})
    save_record("users", owner)
    style = normalize_style(payload.style)
    record = {
        "id": str(uuid.uuid4()), "file_name": payload.file_name, "user_id": owner["id"],
        "target_role": payload.target_role, "template_name": payload.template_name,
        "style": style, "layout_id": None,
        "source_data": payload.model_dump(exclude={"ai_config", "file_name"}),
        "structured_data": None, "latex_content": None, "pdf_path": None, "docx_path": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    try:
        record = await _generate_new_content(payload, record)
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.ai_config.api_key)
        logger.error("Resume generation failed: %s", detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from None
    save_record("resumes", record)
    return _detail(record)


@router.put("/resume/{resume_id}", response_model=ResumeDetailResponse)
async def update_resume(resume_id: str, payload: CreateResumeRequest):
    record = get_record("resumes", "id", resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume file not found")
    _check_unique_name(payload.file_name, exclude_id=resume_id)
    previous_created = record["created_at"]
    record.update({
        "file_name": payload.file_name, "target_role": payload.target_role,
        "template_name": payload.template_name, "style": normalize_style(payload.style),
        "source_data": payload.model_dump(exclude={"ai_config", "file_name"}),
        "updated_at": now_iso(),
    })
    record["created_at"] = previous_created
    try:
        record = await _generate_new_content(payload, record)
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.ai_config.api_key)
        logger.error("Resume update failed: %s", detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from None
    save_record("resumes", record)
    return _detail(record)


@router.get("/resumes", response_model=list[ResumeSummaryResponse])
def list_resumes():
    records = sorted(list_records("resumes"), key=lambda row: row.get("updated_at", row.get("created_at", "")), reverse=True)
    return [ResumeSummaryResponse(
        id=row["id"], file_name=row.get("file_name", "My resume"),
        target_role=row["target_role"], template_name=row.get("template_name", "modern"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row.get("updated_at", row["created_at"])),
    ) for row in records]


@router.get("/resume/{resume_id}", response_model=ResumeDetailResponse)
def get_resume(resume_id: str):
    resume = get_record("resumes", "id", resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume file not found")
    return _detail(resume)


@router.post("/resume/{resume_id}/chat", response_model=ResumeChatResponse)
def chat_with_resume(resume_id: str, payload: ResumeChatRequest):
    record = get_record("resumes", "id", resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume file not found")
    if not record.get("structured_data"):
        raise HTTPException(status_code=409, detail="Create this resume before asking the layout assistant to edit it.")
    try:
        llm = get_llm_provider(payload.ai_config)
        result = edit_resume(
            llm=llm, message=payload.message,
            structured_data=record["structured_data"],
            template_name=record.get("template_name", "modern"),
            style=normalize_style(record.get("style")),
            conversation=payload.conversation,
        )
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.ai_config.api_key)
        logger.error("Resume assistant request failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from None

    record["structured_data"] = result["structured_data"]
    record["template_name"] = result["template_name"]
    record["style"] = normalize_style(result["style"])
    try:
        _render_record(record)
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.ai_config.api_key)
        logger.error("Resume re-render failed: %s", detail)
        raise HTTPException(status_code=500, detail=detail) from None
    layouts = _save_layout_suggestions(result.get("layouts", []))
    return ResumeChatResponse(reply=result["reply"], resume=_detail(record), layouts=layouts)


@router.post("/resume/{resume_id}/apply-layout", response_model=ResumeDetailResponse)
def apply_layout(resume_id: str, body: dict[str, str]):
    record = get_record("resumes", "id", resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume file not found")
    layout_id = body.get("layout_id", "")
    layout = next((item for item in BUILT_IN_LAYOUTS if item["id"] == layout_id), None)
    if layout is None:
        layout = get_record("layouts", "id", layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail="Layout not found")
    record["template_name"] = layout["template_name"]
    record["style"] = normalize_style(layout["style"])
    record["layout_id"] = layout["id"]
    try:
        _render_record(record)
    except Exception as exc:  # noqa: BLE001
        logger.error("Applying layout failed: %s", _safe_error(exc))
        raise HTTPException(status_code=500, detail="Could not render this layout") from None
    return _detail(record)


@router.get("/layouts", response_model=list[SavedLayoutResponse])
def list_layouts():
    saved = [SavedLayoutResponse(**row) for row in list_records("layouts")]
    builtins = [SavedLayoutResponse(**row) for row in BUILT_IN_LAYOUTS]
    return builtins + saved


@router.post("/layouts/generate", response_model=list[SavedLayoutResponse])
def generate_layouts(payload: GenerateLayoutsRequest):
    try:
        llm = get_llm_provider(payload.ai_config)
        response = llm.invoke([
            SystemMessage(content=(
                "You design polished, print-friendly resume layouts. Return only JSON shaped as "
                "{\"layouts\":[{\"name\":string,\"description\":string,\"template_name\":\"modern|professional|simple\","
                "\"style\":{\"accent_color\":string,\"font_size\":string,\"paper_size\":string,\"margin\":string,"
                "\"header_alignment\":string,\"section_style\":string,\"spacing\":string}}]}. "
                "Generate exactly three visibly distinct proposals based on the user's request. "
                "Only use accent colors 1F6FEB, 6F42C1, 0F766E, B45309, 1F2937, BE123C; "
                "font_size 10pt, 11pt, 12pt; paper_size a4paper or letterpaper; margin 1.4cm, 1.8cm, 2cm; "
                "header_alignment left or center; section_style accent-rule, uppercase-rule, minimal; "
                "spacing compact, balanced, airy. Do not return LaTeX or code."
            )),
            HumanMessage(content=payload.request),
        ])
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise ValueError("The AI did not return layout options. Try describing the style again.")
        result = json.loads(match.group(0))
        layouts = _save_layout_suggestions(result.get("layouts", []))
        if not layouts:
            raise ValueError("The AI did not return usable layout options. Try again.")
        return layouts
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.ai_config.api_key)
        logger.error("Layout generation failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from None


@router.post("/ai/test")
def test_ai(payload: AIConfig):
    try:
        llm = get_llm_provider(payload)
        reply = llm.invoke([SystemMessage(content="Reply with only the word ready."), HumanMessage(content="Connection test")])
        if not reply:
            raise ValueError("The provider returned an empty response")
        return {"ok": True, "message": "AI connection is ready."}
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.api_key)
        logger.error("AI provider test failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from None


def _artifact(resume_id: str, kind: str):
    resume = get_record("resumes", "id", resume_id)
    path = resume.get(f"{kind}_path") if resume else None
    if not path or path == "#pending" or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{kind.upper()} not available")
    media = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    safe_name = re.sub(r"[^\w .-]+", "", resume.get("file_name", "resume")).strip() or "resume"
    return FileResponse(path, media_type=media, filename=f"{safe_name}.{kind}")


@router.get("/resume/{resume_id}/pdf")
def get_resume_pdf(resume_id: str):
    return _artifact(resume_id, "pdf")


@router.get("/resume/{resume_id}/docx")
def get_resume_docx(resume_id: str):
    return _artifact(resume_id, "docx")


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates():
    items = list_available_templates(settings.template_dir)
    return [TemplateResponse(name=item["name"], description=item["filename"], available=item["available"])
            for item in items]
