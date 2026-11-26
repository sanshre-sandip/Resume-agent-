import json
import logging
import os
import re
from typing import Any
from ..agents.rendering_agent import render_latex
from ..agents.export_agent import persist_artifacts
from ..config import settings

logger = logging.getLogger(__name__)

DEFAULT_STYLE = {
    "accent_color": "1F6FEB",
    "font_size": "11pt",
    "paper_size": "a4paper",
    "margin": "1.8cm",
    "header_alignment": "left",
    "section_style": "accent-rule",
    "spacing": "balanced",
    "show_logo": "no",
    "contact_layout": "inline",
}
STYLE_OPTIONS = {
    "accent_color": {"1F6FEB", "6F42C1", "0F766E", "B45309", "1F2937", "BE123C"},
    "font_size": {"10pt", "11pt", "12pt"},
    "paper_size": {"a4paper", "letterpaper"},
    "margin": {"1.4cm", "1.8cm", "2cm"},
    "header_alignment": {"left", "center"},
    "section_style": {"accent-rule", "uppercase-rule", "minimal"},
    "spacing": {"compact", "balanced", "airy"},
    "show_logo": {"yes", "no"},
    "contact_layout": {"inline", "separate"},
}


def normalize_style(style: dict[str, Any] | None) -> dict[str, str]:
    normalized = dict(DEFAULT_STYLE)
    for key, allowed_values in STYLE_OPTIONS.items():
        value = (style or {}).get(key)
        if key == "accent_color" and isinstance(value, str):
            color = value.strip().removeprefix("#")
            if re.fullmatch(r"[0-9a-fA-F]{6}", color):
                normalized[key] = color.upper()
            continue
        if value in allowed_values:
            normalized[key] = value
    return normalized


def normalize_title(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t.title() if t else ""


def build_context(
    structured: dict[str, Any], pdf_path: str | None, style: dict[str, Any] | None = None
) -> dict[str, Any]:
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
    header["links"] = header.get("links") or structured.get("links") or []
    public_links = []
    if header["linkedin"]:
        public_links.append({"label": "LinkedIn", "url": header["linkedin"]})
    if header["links"]:
        public_links.extend(link for link in header["links"] if isinstance(link, dict) and link.get("url"))
    else:
        if header["github"]:
            public_links.append({"label": "GitHub", "url": header["github"]})
        if header["portfolio"]:
            public_links.append({"label": "Portfolio", "url": header["portfolio"]})
    header["public_links"] = public_links
    initials = "".join(word[0] for word in (header["full_name"] or "").split()[:2]).upper()

    raw_skills = structured.get("skills") or []
    if isinstance(raw_skills, str):
        raw_skills = re.split(r"[,;|\n]", raw_skills)
    elif isinstance(raw_skills, dict):
        raw_skills = [
            f"{str(group).strip()}: {', '.join(str(item).strip() for item in (items if isinstance(items, list) else [items]) if str(item).strip())}"
            for group, items in raw_skills.items()
        ]
    skills = [str(skill).strip().lstrip("*•·- ") for skill in raw_skills if str(skill).strip()]
    grouped_skills: list[str] = []
    category = ""
    category_skills: list[str] = []
    for skill in skills:
        match = re.match(r"^([^:]{2,60}):\s*(.*)$", skill)
        if match:
            if category:
                grouped_skills.append(f"{category}: {', '.join(category_skills)}")
            category = match.group(1).strip()
            category_skills = [match.group(2).strip()] if match.group(2).strip() else []
        elif category:
            category_skills.append(skill)
        else:
            grouped_skills.append(skill)
    if category:
        grouped_skills.append(f"{category}: {', '.join(category_skills)}")
    skills = grouped_skills
    skills_line = ", ".join(skills)
    skill_columns = min(3, max(2, (len(skills) + 11) // 12))
    repeatable_sections = [
        structured.get(key) or []
        for key in ("experience", "projects", "education", "certificates", "publications", "awards", "languages")
    ]
    max_section_entries = max((len(items) for items in repeatable_sections), default=0)
    section_columns = min(3, max(2, (max_section_entries + 3) // 4))

    return {
        "header": header,
        "summary": structured.get("summary") or "",
        "experience": structured.get("experience") or [],
        "projects": structured.get("projects") or [],
        "education": structured.get("education") or [],
        "skills_line": skills_line,
        "skills": skills,
        "skill_columns": skill_columns,
        "section_columns": section_columns,
        "certificates": structured.get("certificates") or [],
        "awards": structured.get("awards") or [],
        "languages": structured.get("languages") or [],
        "publications": structured.get("publications") or [],
        "logo_initials": initials,
        "pdf_path": pdf_path or "",
        **normalize_style(style),
    }


def build_latex(structured_data: dict[str, Any], template_name: str, style: dict[str, Any] | None = None) -> str:
    ctx = build_context(structured_data, None, style)
    return render_latex(template_name=template_name, context=ctx, template_dir=settings.template_dir)


def build_rendered_paths(structured_data: dict[str, Any], template_name: str, user_id: str, resume_id: str, ts: str, style: dict[str, Any] | None = None) -> dict:
    normalized_style = normalize_style(style)
    latex_content = build_latex(structured_data, template_name, normalized_style)
    return persist_artifacts(
        tex_content=latex_content,
        user_id=user_id,
        resume_id=resume_id,
        generated_dir=settings.generated_dir,
        timestamp=ts,
        structured_data=structured_data,
        style=normalized_style,
        template_name=template_name,
    )
