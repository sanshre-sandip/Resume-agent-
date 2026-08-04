import json
import logging
import os
import re
from typing import Any
from ..agents.rendering_agent import render_latex
from ..agents.export_agent import persist_artifacts
from ..config import settings

logger = logging.getLogger(__name__)


def normalize_title(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t.title() if t else ""


def build_context(structured: dict[str, Any], pdf_path: str | None) -> dict[str, Any]:
    header = {**(structured.get("header") or {})}
    header.setdefault("name", header.get("full_name") or "")
    header["full_name"] = header.get("name") or header.get("full_name") or ""
    header["title"] = normalize_title(
        structured.get("professional_title") or structured.get("header", {}).get("title", "")
    )
    header["email"] = header.get("email") or ""
    header["phone"] = header.get("phone") or ""
    header["address"] = header.get("address") or ""
    header["linkedin"] = header.get("linkedin") or ""
    header["github"] = header.get("github") or ""
    header["portfolio"] = header.get("portfolio") or ""

    skills = structured.get("skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in re.split(r"[,;|\n]", skills) if s.strip()]
    skills_line = ", ".join(skills)

    return {
        "header": header,
        "summary": structured.get("summary") or "",
        "experience": structured.get("experience") or [],
        "projects": structured.get("projects") or [],
        "education": structured.get("education") or [],
        "skills_line": skills_line,
        "skills": skills,
        "certificates": structured.get("certificates") or [],
        "pdf_path": pdf_path or "",
    }


def build_latex(structured_data: dict[str, Any], template_name: str) -> str:
    ctx = build_context(structured_data, None)
    return render_latex(template_name=template_name, context=ctx, template_dir=settings.template_dir)


def build_rendered_paths(structured_data: dict[str, Any], template_name: str, user_id: str, resume_id: str, ts: str) -> dict:
    latex_content = build_latex(structured_data, template_name)
    return persist_artifacts(
        tex_content=latex_content,
        user_id=user_id,
        resume_id=resume_id,
        generated_dir=settings.generated_dir,
        timestamp=ts,
    )
