import json
import logging
import os
import re
import uuid
import shutil
import time
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import HumanMessage, SystemMessage

from ..agents.export_agent import persist_artifacts
from ..agents.resume_editor_agent import edit_resume
from ..config import settings
from ..database.file_store import get_record, list_records, lock_resume, now_iso, save_record
from ..graph.resume_graph import build_resume_graph
from ..schemas.schemas import (
    AIConfig,
    CreateResumeRequest,
    GenerateLayoutsRequest,
    LayoutProposal,
    ResumeChatRequest,
    ResumeChatResponse,
    ResumeDetailResponse,
    ResumeUndoRequest,
    ResumeSummaryResponse,
    SavedLayoutResponse,
    TemplateResponse,
)
from ..services.resume_service import build_context, normalize_style
from ..utils.llm_providers import get_llm_provider
from ..security.auth import get_current_user
from ..utils.renderer import list_available_templates
from ..agents.rendering_agent import LaTeXRenderer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["resume"])
_ai_requests: dict[str, list[float]] = {}


def _rate_limit_ai(owner_id: str, max_requests: int = 30, window: int = 60) -> None:
    now = time.monotonic()
    recent = [stamp for stamp in _ai_requests.get(owner_id, []) if now - stamp < window]
    if len(recent) >= max_requests:
        raise HTTPException(status_code=429, detail="AI requests are temporarily limited. Wait a minute and try again.")
    recent.append(now)
    _ai_requests[owner_id] = recent


def _serialize_resume(func):
    @wraps(func)
    def wrapped(resume_id: str, *args, **kwargs):
        with lock_resume(resume_id):
            return func(resume_id, *args, **kwargs)
    return wrapped


class ResumeTitleUpdate(BaseModel):
    title: str = Field(min_length=2, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return " ".join(value.strip().split())

BUILT_IN_LAYOUTS = [
    {
        "id": "ats-standard", "name": "ATS-Friendly Standard", "description": "ATS-conscious single column, conventional headings, chronological work history, and black-and-white styling.",
        "template_name": "ats", "style": normalize_style({"accent_color": "1F2937", "section_style": "uppercase-rule", "spacing": "compact"}), "built_in": True, "form_choice": True,
    },
    {
        "id": "modern-minimalist", "name": "Modern Minimalist", "description": "A clean single column with generous whitespace, sans-serif type, and simple dividers.",
        "template_name": "modern", "style": normalize_style({"accent_color": "1F2937", "section_style": "minimal", "spacing": "airy"}), "built_in": True, "form_choice": True,
    },
    {
        "id": "student-graduate", "name": "Student & Fresh Graduate", "description": "Education-first with room for projects, internships, skills, and limited work history.",
        "template_name": "student", "style": normalize_style({"accent_color": "6F42C1", "section_style": "accent-rule", "spacing": "compact"}), "built_in": True, "form_choice": True,
    },
    {
        "id": "technical-developer", "name": "Technical Developer", "description": "Skills and software projects lead, with visible repository and project links.",
        "template_name": "developer", "style": normalize_style({"accent_color": "0F766E", "section_style": "uppercase-rule", "spacing": "compact"}), "built_in": True, "form_choice": True,
    },
    {
        "id": "ai-ml-research", "name": "AI/ML Research", "description": "Research profile, education, AI/ML projects, technical skills, and certifications.",
        "template_name": "research", "style": normalize_style({"accent_color": "1F6FEB", "section_style": "accent-rule", "spacing": "balanced"}), "built_in": True, "form_choice": True,
    },
]


def _detail(record: dict[str, Any]) -> ResumeDetailResponse:
    return ResumeDetailResponse(
        id=record["id"], file_name=record.get("file_name", "My resume"),
        user_id=record["user_id"], target_role=record["target_role"],
        page_size="letter" if normalize_style(record.get("style")).get("paper_size") == "letterpaper" else "a4",
        template_name=record.get("template_name", "modern"),
        structured_data=record.get("structured_data"), latex_content=record.get("latex_content"),
        pdf_path=record.get("pdf_path"), docx_path=record.get("docx_path"),
        source_data=record.get("source_data"), style=record.get("style"),
        layout_id=record.get("layout_id"),
        created_at=datetime.fromisoformat(record["created_at"]),
        updated_at=datetime.fromisoformat(record.get("updated_at", record["created_at"])),
    )


def _check_unique_name(file_name: str, owner_id: str, exclude_id: str | None = None) -> None:
    duplicate = next(
        (row for row in list_records("resumes")
         if row.get("user_id") == owner_id and row.get("file_name", "").casefold() == file_name.casefold()
         and row.get("id") != exclude_id),
        None,
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="That resume file name already exists. Choose a different name.")


def _validate_layout_selection(payload: CreateResumeRequest, owner_id: str) -> None:
    if payload.template_name not in {"ats", "modern", "student", "developer", "research"}:
        raise HTTPException(status_code=422, detail="Choose one of the available resume layouts.")
    if payload.layout_id:
        known_ids = {layout["id"] for layout in BUILT_IN_LAYOUTS if layout.get("form_choice")}
        known_ids.update(row["id"] for row in list_records("layouts") if row.get("owner_id") == owner_id)
        if payload.layout_id not in known_ids and payload.layout_id != "custom":
            raise HTTPException(status_code=422, detail="Choose a layout from the layout list.")


def _owned_resume(resume_id: str, owner_id: str) -> dict[str, Any]:
    record = get_record("resumes", "id", resume_id)
    if not record or record.get("user_id") != owner_id:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return record


def _structured_from_request(payload: CreateResumeRequest) -> dict[str, Any]:
    profile = payload.user_profile.model_dump(exclude_none=True)
    return {
        "header": profile,
        "professional_title": payload.target_role,
        "summary": payload.summary,
        "skills": payload.skills,
        "experience": [item.model_dump(exclude_none=True) for item in payload.experience],
        "education": [item.model_dump(exclude_none=True) for item in payload.education],
        "projects": [item.model_dump(exclude_none=True) for item in payload.projects],
        "certificates": [item.model_dump(exclude_none=True) for item in payload.certificates],
        "awards": [item.model_dump(exclude_none=True) for item in payload.awards],
        "languages": [item.model_dump(exclude_none=True) for item in payload.languages],
        "publications": [item.model_dump(exclude_none=True) for item in payload.publications],
    }


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


def _safe_error(exc: Exception, *secrets: str) -> str:
    message = str(exc) or "The requested operation could not be completed."
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    return re.sub(r"(?i)(sk-[A-Za-z0-9_-]{12,}|gsk_[A-Za-z0-9_-]{12,}|sk-or-v1-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,})", "[redacted]", message)[:500]


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
        structured_data=data,
        style=style,
        template_name=template_name,
    )
    record["latex_content"] = latex
    record["pdf_path"] = artifacts.get("pdf_path")
    record["docx_path"] = artifacts.get("docx_path")
    record["updated_at"] = now_iso()
    save_record("resumes", record)


def _source_data_from_structured(record: dict[str, Any]) -> dict[str, Any]:
    structured = record.get("structured_data") or {}
    header = structured.get("header") or {}
    old_source = record.get("source_data") or {}
    old_profile = old_source.get("user_profile") or {}
    profile = {
        "full_name": header.get("full_name") or header.get("name") or old_profile.get("full_name", ""),
        "email": header.get("email") or old_profile.get("email", ""),
        "phone": header.get("phone") or old_profile.get("phone", ""),
        "address": header.get("address") or old_profile.get("address"),
        "linkedin": header.get("linkedin") or old_profile.get("linkedin"),
        "github": header.get("github") or old_profile.get("github"),
        "portfolio": header.get("portfolio") or old_profile.get("portfolio"),
        "links": header.get("links") or old_profile.get("links", []),
    }
    return {
        **old_source,
        "user_profile": profile,
        "summary": structured.get("summary", ""),
        "target_role": record.get("target_role", ""),
        "template_name": record.get("template_name", "modern"),
        "style": normalize_style(record.get("style")),
        "experience": structured.get("experience", []),
        "education": structured.get("education", []),
        "projects": structured.get("projects", []),
        "certificates": structured.get("certificates", []),
        "awards": structured.get("awards", []),
        "languages": structured.get("languages", []),
        "publications": structured.get("publications", []),
        "skills": structured.get("skills", []),
    }


def _save_layout_suggestions(proposals: list[dict[str, Any]], owner_id: str) -> list[SavedLayoutResponse]:
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
            "owner_id": owner_id,
        }
        save_record("layouts", layout)
        saved.append(SavedLayoutResponse(**layout))
    return saved


def _matching_layout_id(template_name: str, style: dict[str, str], owner_id: str) -> str | None:
    owned_layouts = [row for row in list_records("layouts") if row.get("owner_id") == owner_id]
    for layout in BUILT_IN_LAYOUTS + owned_layouts:
        if layout.get("template_name") == template_name and normalize_style(layout.get("style")) == style:
            return layout.get("id")
    return None


def _is_inline_contact_request(message: str) -> bool:
    return bool(
        re.search(r"\b(one|same|single)\s+line\b|\binline\b", message, re.IGNORECASE)
        and re.search(r"\b(link|contact|github|portfolio|linkedin|url)\b", message, re.IGNORECASE)
    )


def _apply_inline_contact_format(record: dict[str, Any], message: str) -> str:
    source = record.get("source_data") or {}
    data = record.get("structured_data") or {
        "header": source.get("user_profile") or {},
        "summary": source.get("summary", ""),
        "experience": source.get("experience", []),
        "projects": source.get("projects", []),
        "education": source.get("education", []),
        "skills": source.get("skills", []),
        "certificates": source.get("certificates", []),
    }
    header = dict(data.get("header") or {})
    links = [dict(link) for link in header.get("links", []) if isinstance(link, dict) and link.get("url")]
    for key, label in (("github", "GitHub"), ("portfolio", "Portfolio")):
        url = header.get(key)
        if url and not any(link.get("url") == url for link in links):
            links.append({"label": label, "url": url})

    github_url = re.search(r"https?://(?:www\.)?github\.com/[^\s,;]+", message, re.IGNORECASE)
    updated_github = ""
    if github_url:
        updated_github = github_url.group(0).rstrip(").]}!? ")
        index = next((i for i, link in enumerate(links) if "github" in link.get("label", "").lower() or "github.com" in link.get("url", "").lower()), None)
        github_link = {"label": "GitHub", "url": updated_github}
        if index is None:
            links.append(github_link)
        else:
            links[index] = github_link

    header["links"] = links
    data["header"] = header
    record["structured_data"] = data
    record["style"] = {**normalize_style(record.get("style")), "contact_layout": "inline"}
    record["layout_id"] = _matching_layout_id(record.get("template_name", "modern"), record["style"], record["user_id"])
    record["source_data"] = _source_data_from_structured(record)
    _render_record(record)
    if updated_github:
        return f"Done — I put the contact details and links on one line, updated GitHub to {updated_github}, and kept your other links."
    return "Done — I put the contact details and existing links on one line."


@router.post("/resume/create", response_model=ResumeDetailResponse, status_code=status.HTTP_201_CREATED)
def create_resume(payload: CreateResumeRequest, current_user: dict = Depends(get_current_user)):
    owner_id = current_user["id"]
    _validate_layout_selection(payload, owner_id)
    _check_unique_name(payload.file_name, owner_id)
    record = {
        "id": str(uuid.uuid4()), "file_name": payload.file_name, "user_id": owner_id,
        "target_role": payload.target_role, "template_name": payload.template_name,
        "style": normalize_style({**payload.style, "paper_size": "letterpaper" if payload.page_size == "letter" else "a4paper"}), "layout_id": payload.layout_id,
        "source_data": payload.model_dump(exclude={"ai_config", "file_name", "layout_id"}),
        "structured_data": _structured_from_request(payload), "latex_content": None, "pdf_path": None, "docx_path": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    try:
        _render_record(record)
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc)
        logger.error("Resume generation failed: %s", detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from None
    save_record("resumes", record)
    return _detail(record)


@router.put("/resume/{resume_id}", response_model=ResumeDetailResponse)
@_serialize_resume
def update_resume(resume_id: str, payload: CreateResumeRequest, current_user: dict = Depends(get_current_user)):
    owner_id = current_user["id"]
    _validate_layout_selection(payload, owner_id)
    record = _owned_resume(resume_id, owner_id)
    if not payload.expected_updated_at:
        raise HTTPException(status_code=428, detail="Reopen the saved resume before updating it so the latest version can be protected.")
    if payload.expected_updated_at != record.get("updated_at", record.get("created_at")):
        raise HTTPException(status_code=409, detail="This resume changed elsewhere. Reopen the latest version before saving your edits.")
    _check_unique_name(payload.file_name, owner_id, exclude_id=resume_id)
    previous_created = record["created_at"]
    record.update({
        "file_name": payload.file_name, "target_role": payload.target_role,
        "template_name": payload.template_name,
        "style": normalize_style({**payload.style, "paper_size": "letterpaper" if payload.page_size == "letter" else "a4paper"}),
        "structured_data": _structured_from_request(payload),
        "layout_id": payload.layout_id,
        "source_data": payload.model_dump(exclude={"ai_config", "file_name", "layout_id"}),
        "updated_at": now_iso(),
    })
    record["created_at"] = previous_created
    try:
        _render_record(record)
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc)
        logger.error("Resume update failed: %s", detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from None
    save_record("resumes", record)
    return _detail(record)


@router.get("/resumes", response_model=list[ResumeSummaryResponse])
def list_resumes(current_user: dict = Depends(get_current_user)):
    records = sorted((row for row in list_records("resumes") if row.get("user_id") == current_user["id"]), key=lambda row: row.get("updated_at", row.get("created_at", "")), reverse=True)
    return [ResumeSummaryResponse(
        id=row["id"], file_name=row.get("file_name", "My resume"),
        target_role=row["target_role"], template_name=row.get("template_name", "modern"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row.get("updated_at", row["created_at"])),
    ) for row in records]


@router.get("/resume/{resume_id}", response_model=ResumeDetailResponse)
@_serialize_resume
def get_resume(resume_id: str, current_user: dict = Depends(get_current_user)):
    return _detail(_owned_resume(resume_id, current_user["id"]))


@router.patch("/resume/{resume_id}/title", response_model=ResumeSummaryResponse)
@_serialize_resume
def rename_resume(resume_id: str, payload: ResumeTitleUpdate, current_user: dict = Depends(get_current_user)):
    owner_id = current_user["id"]
    record = _owned_resume(resume_id, owner_id)
    title = " ".join(payload.title.strip().split())
    _check_unique_name(title, owner_id, exclude_id=resume_id)
    record["file_name"] = title
    record["updated_at"] = now_iso()
    save_record("resumes", record)
    return ResumeSummaryResponse(
        id=record["id"], file_name=title, target_role=record["target_role"],
        template_name=record.get("template_name", "modern"),
        created_at=datetime.fromisoformat(record["created_at"]),
        updated_at=datetime.fromisoformat(record["updated_at"]),
    )


@router.post("/resume/{resume_id}/duplicate", response_model=ResumeDetailResponse, status_code=status.HTTP_201_CREATED)
@_serialize_resume
def duplicate_resume(resume_id: str, current_user: dict = Depends(get_current_user)):
    owner_id = current_user["id"]
    source = _owned_resume(resume_id, owner_id)
    base_title = f"{source.get('file_name', 'Resume')} copy"
    title, suffix = base_title, 2
    owned_names = {row.get("file_name", "").casefold() for row in list_records("resumes") if row.get("user_id") == owner_id}
    while title.casefold() in owned_names:
        title = f"{base_title} {suffix}"
        suffix += 1
    record = {**source, "id": str(uuid.uuid4()), "file_name": title, "created_at": now_iso(), "updated_at": now_iso()}
    record.pop("pdf_path", None)
    record.pop("docx_path", None)
    record.pop("latex_content", None)
    _render_record(record)
    save_record("resumes", record)
    return _detail(record)


@router.delete("/resume/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
@_serialize_resume
def delete_resume(resume_id: str, current_user: dict = Depends(get_current_user)):
    record = _owned_resume(resume_id, current_user["id"])
    generated_root = Path(settings.generated_dir).resolve()
    resume_dir = (generated_root / current_user["id"] / resume_id).resolve()
    if resume_dir.parent == (generated_root / current_user["id"]).resolve():
        shutil.rmtree(resume_dir, ignore_errors=True)
    from ..database.file_store import delete_records
    delete_records("resumes", lambda row: row.get("id") == resume_id and row.get("user_id") == current_user["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/resume/{resume_id}/chat", response_model=ResumeChatResponse)
@_serialize_resume
def chat_with_resume(resume_id: str, payload: ResumeChatRequest, current_user: dict = Depends(get_current_user)):
    record = _owned_resume(resume_id, current_user["id"])
    conversation = [item.model_dump() for item in payload.conversation]
    recent_context = "\n".join(item.get("content", "") for item in conversation[-4:])
    formatting_context = f"{recent_context}\n{payload.message}"
    if _is_inline_contact_request(formatting_context):
        try:
            reply = _apply_inline_contact_format(record, formatting_context)
        except Exception as exc:  # noqa: BLE001
            logger.error("Inline contact formatting failed: %s", _safe_error(exc))
            raise HTTPException(status_code=500, detail="Could not format the contact details") from None
        return ResumeChatResponse(reply=reply, resume=_detail(record), layouts=[])
    if not record.get("structured_data"):
        raise HTTPException(status_code=409, detail="This resume has no generated content yet. Apply the inline contact format in the live draft, then save the resume.")
    _rate_limit_ai(current_user["id"])
    try:
        llm = get_llm_provider(payload.ai_config)
        result = edit_resume(
            llm=llm, message=payload.message,
            structured_data=record["structured_data"],
            template_name=record.get("template_name", "modern"),
            style=normalize_style(record.get("style")),
            conversation=conversation,
        )
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.ai_config.api_key.get_secret_value() if payload.ai_config.api_key else "")
        logger.error("Resume assistant request failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from None

    suggestion_only = bool(re.search(
        r"\b(more|new|some|three|two|different|another)\b.{0,40}\b(layout|design)s?\b|\b(layout|design)s?\b.{0,40}\b(ideas?|options?|suggestions?)\b",
        payload.message.lower(),
    ))
    if not suggestion_only:
        record["structured_data"] = result["structured_data"]
        record["template_name"] = result["template_name"]
        record["style"] = normalize_style(result["style"])
        record["layout_id"] = _matching_layout_id(record["template_name"], record["style"], current_user["id"])
        record["source_data"] = _source_data_from_structured(record)
        try:
            _render_record(record)
        except Exception as exc:  # noqa: BLE001
            detail = _safe_error(exc)
            logger.error("Resume re-render failed: %s", detail)
            raise HTTPException(status_code=500, detail=detail) from None
    layouts = _save_layout_suggestions(result.get("layouts", []), current_user["id"])
    return ResumeChatResponse(reply=result["reply"], resume=_detail(record), layouts=layouts)


@router.post("/resume/{resume_id}/undo", response_model=ResumeDetailResponse)
@_serialize_resume
def undo_resume(resume_id: str, payload: ResumeUndoRequest, current_user: dict = Depends(get_current_user)):
    record = _owned_resume(resume_id, current_user["id"])
    record["structured_data"] = payload.structured_data
    record["template_name"] = payload.template_name
    record["style"] = normalize_style(payload.style)
    record["layout_id"] = _matching_layout_id(record["template_name"], record["style"], current_user["id"])
    record["source_data"] = _source_data_from_structured(record)
    try:
        _render_record(record)
    except Exception as exc:  # noqa: BLE001
        logger.error("Undo render failed: %s", _safe_error(exc))
        raise HTTPException(status_code=500, detail="Could not restore the previous resume version") from None
    return _detail(record)


@router.post("/resume/{resume_id}/apply-layout", response_model=ResumeDetailResponse)
@_serialize_resume
def apply_layout(resume_id: str, body: dict[str, str], current_user: dict = Depends(get_current_user)):
    record = _owned_resume(resume_id, current_user["id"])
    layout_id = body.get("layout_id", "")
    layout = next((item for item in BUILT_IN_LAYOUTS if item["id"] == layout_id and item.get("form_choice")), None)
    if layout is None:
        layout = get_record("layouts", "id", layout_id)
    if layout is None or (not layout.get("built_in") and layout.get("owner_id") != current_user["id"]):
        raise HTTPException(status_code=404, detail="Layout not found")
    record["template_name"] = layout["template_name"]
    record["style"] = normalize_style(layout["style"])
    record["layout_id"] = layout["id"]
    record["source_data"] = _source_data_from_structured(record)
    try:
        _render_record(record)
    except Exception as exc:  # noqa: BLE001
        logger.error("Applying layout failed: %s", _safe_error(exc))
        raise HTTPException(status_code=500, detail="Could not render this layout") from None
    return _detail(record)


@router.get("/layouts", response_model=list[SavedLayoutResponse])
def list_layouts(current_user: dict = Depends(get_current_user)):
    legacy_templates = {"professional": "modern", "simple": "ats", "creative": "modern"}
    saved = []
    for row in list_records("layouts"):
        if row.get("owner_id") != current_user["id"]:
            continue
        compatible = {**row, "template_name": legacy_templates.get(row.get("template_name"), row.get("template_name", "modern"))}
        saved.append(SavedLayoutResponse(**compatible))
    builtins = [SavedLayoutResponse(**row) for row in BUILT_IN_LAYOUTS]
    return builtins + saved


@router.post("/layouts/generate", response_model=list[SavedLayoutResponse])
def generate_layouts(payload: GenerateLayoutsRequest, current_user: dict = Depends(get_current_user)):
    _rate_limit_ai(current_user["id"], max_requests=10, window=60)
    try:
        llm = get_llm_provider(payload.ai_config)
        response = llm.invoke([
            SystemMessage(content=(
                "You design polished, print-friendly resume layouts. Return only JSON shaped as "
                "{\"layouts\":[{\"name\":string,\"description\":string,\"template_name\":\"ats|modern|student|developer|research\","
                "\"style\":{\"accent_color\":string,\"font_size\":string,\"paper_size\":string,\"margin\":string,"
                "\"header_alignment\":string,\"section_style\":string,\"spacing\":string,\"show_logo\":\"yes|no\",\"contact_layout\":\"inline|separate\"}}]}. "
                "Generate exactly three visibly distinct proposals based on the user's request. "
                "Use a six-digit hex accent color without #; "
                "font_size 10pt, 11pt, 12pt; paper_size a4paper or letterpaper; margin 1.4cm, 1.8cm, 2cm; "
                "header_alignment left or center; section_style accent-rule, uppercase-rule, minimal; "
                "spacing compact, balanced, airy; show_logo yes or no for an initials monogram; contact_layout inline or separate. Do not return LaTeX or code."
            )),
            HumanMessage(content=payload.request),
        ])
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise ValueError("The AI did not return layout options. Try describing the style again.")
        result = json.loads(match.group(0))
        layouts = _save_layout_suggestions(result.get("layouts", []), current_user["id"])
        if not layouts:
            raise ValueError("The AI did not return usable layout options. Try again.")
        return layouts
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.ai_config.api_key.get_secret_value() if payload.ai_config.api_key else "")
        logger.error("Layout generation failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from None


@router.post("/ai/test")
def test_ai(payload: AIConfig, current_user: dict = Depends(get_current_user)):
    _rate_limit_ai(current_user["id"], max_requests=5, window=60)
    try:
        llm = get_llm_provider(payload)
        reply = llm.invoke([SystemMessage(content="Reply with only the word ready."), HumanMessage(content="Connection test")])
        if not reply:
            raise ValueError("The provider returned an empty response")
        return {"ok": True, "message": "AI connection is ready."}
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc, payload.api_key.get_secret_value() if payload.api_key else "")
        logger.error("AI provider test failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from None


def _artifact(resume_id: str, kind: str, owner_id: str, inline: bool = False):
    resume = _owned_resume(resume_id, owner_id)
    path = resume.get(f"{kind}_path") if resume else None
    if not path or path == "#pending" or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{kind.upper()} not available")
    root = (Path(settings.generated_dir) / owner_id / resume_id).resolve()
    resolved = Path(path).resolve()
    if resolved.parent != root or not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"{kind.upper()} not available")
    media = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    safe_name = re.sub(r"[^\w .-]+", "", resume.get("file_name", "resume")).strip() or "resume"
    return FileResponse(
        path, media_type=media, filename=f"{safe_name}.{kind}",
        content_disposition_type="inline" if inline else "attachment",
    )


@router.get("/resume/{resume_id}/pdf")
def get_resume_pdf(resume_id: str, inline: bool = False, current_user: dict = Depends(get_current_user)):
    return _artifact(resume_id, "pdf", current_user["id"], inline=inline)


@router.get("/resume/{resume_id}/docx")
def get_resume_docx(resume_id: str, current_user: dict = Depends(get_current_user)):
    return _artifact(resume_id, "docx", current_user["id"])


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates():
    items = list_available_templates(settings.template_dir)
    return [TemplateResponse(name=item["name"], description=item["filename"], available=item["available"])
            for item in items]
