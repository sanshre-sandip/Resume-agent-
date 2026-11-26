import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def compile_pdflatex(tex_path: str, output_dir: str) -> str | None:
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
        tex_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        logger.info("pdflatex rc=%s", proc.returncode)
        pdf_name = Path(tex_path).with_suffix(".pdf").name
        out = str(Path(output_dir) / pdf_name)
        if not Path(out).exists():
            if proc.returncode != 0:
                logger.warning("pdflatex failed, stdout tail: %s", proc.stdout[-800:])
            return None
        if proc.returncode != 0:
            logger.warning("pdflatex exited %s but produced a PDF; stdout tail: %s", proc.returncode, proc.stdout[-800:])
        return out
    except FileNotFoundError:
        logger.error("pdflatex not found in PATH; install TeX Live or teTeX")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("PDF generation failed: %s", exc)
        return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(filter(None, (_text(item) for item in value)))
    if isinstance(value, dict):
        return ", ".join(f"{key.replace('_', ' ').title()}: {_text(item)}" for key, item in value.items() if item)
    return str(value).strip()


def create_docx(
    structured_data: dict[str, Any], output_path: str, style: dict[str, Any] | None = None,
    template_name: str = "modern",
) -> str | None:
    """Create a Word version directly from resume data, independent of TeX tools."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor

        doc = Document()
        section = doc.sections[0]
        style = style or {}
        section.top_margin = section.bottom_margin = Inches(0.55 if style.get("spacing") == "compact" else 0.7)
        section.left_margin = section.right_margin = Inches(0.55 if style.get("margin") == "1.4cm" else 0.7)
        if style.get("paper_size") == "letterpaper":
            section.page_width, section.page_height = Inches(8.5), Inches(11)
        else:
            section.page_width, section.page_height = Inches(8.27), Inches(11.69)
        accent_value = str(style.get("accent_color", "1F6FEB")).removeprefix("#")
        if template_name == "ats":
            accent_value = "222222"
        try:
            accent_rgb = RGBColor.from_string(accent_value.upper())
        except ValueError:
            accent_rgb = RGBColor(31, 111, 235)
        normal = doc.styles["Normal"]
        normal.font.name = "Aptos" if template_name in {"modern", "developer", "student", "ats"} else "Liberation Serif"
        normal.font.size = Pt(9 if style.get("spacing") == "compact" else 10)
        normal.paragraph_format.space_after = Pt(3 if style.get("spacing") == "compact" else 5)
        for heading_name in ("Heading 1", "Heading 2"):
            heading_style = doc.styles[heading_name]
            heading_style.font.name = normal.font.name
            heading_style.font.color.rgb = accent_rgb
            heading_style.font.bold = True
            heading_style.paragraph_format.keep_with_next = True
            heading_style.paragraph_format.space_before = Pt(9)
            heading_style.paragraph_format.space_after = Pt(3)
        header = structured_data.get("header") or {}
        name = _text(header.get("full_name") or header.get("name")) or "Resume"
        title = _text(structured_data.get("professional_title") or header.get("title"))
        p = doc.add_paragraph()
        p.alignment = 1 if style.get("header_alignment") == "center" or template_name == "creative" else 0
        if style.get("show_logo") == "yes":
            initials = "".join(word[0] for word in name.split()[:2]).upper()
            mark = p.add_run(f"{initials}  ")
            mark.bold = True
            mark.font.color.rgb = accent_rgb
        run = p.add_run(name)
        run.bold = True
        run.font.size = Pt(23 if template_name == "creative" else 20)
        run.font.color.rgb = accent_rgb if template_name == "creative" else RGBColor(37, 39, 58)
        if title:
            p = doc.add_paragraph(title)
            p.alignment = 1 if p.alignment == 1 else 0
        contacts = [header.get(key) for key in ("email", "phone", "address")]
        if header.get("linkedin"):
            contacts.append(f"LinkedIn: {_text(header['linkedin'])}")
        contacts.extend(f"{_text(link.get('label'))}: {_text(link.get('url'))}" for link in header.get("links", []) if isinstance(link, dict))
        if not header.get("links"):
            contacts.extend(header.get(key) for key in ("github", "portfolio"))
        contacts = [_text(item) for item in contacts if item]
        if contacts:
            p = doc.add_paragraph("  |  ".join(contacts))
            p.alignment = 1

        def section_title(label: str) -> None:
            doc.add_heading(label, level=1)

        def add_items(values: Any, fields: tuple[str, ...]) -> None:
            if isinstance(values, str):
                values = [values] if values.strip() else []
            for item in values or []:
                if isinstance(item, dict):
                    lead = " — ".join(filter(None, (_text(item.get(field)) for field in fields)))
                    if lead:
                        p = doc.add_paragraph()
                        p.add_run(lead).bold = True
                    for key, value in item.items():
                        if key not in fields and value:
                            doc.add_paragraph(_text(value))
                else:
                    doc.add_paragraph(_text(item))

        def skill_items(values: Any) -> list[str]:
            if isinstance(values, str):
                values = values.replace(";", ",").replace("|", ",").replace("\n", ",").split(",")
            if isinstance(values, dict):
                flattened = []
                for group, items in values.items():
                    entries = items if isinstance(items, list) else [items]
                    flattened.extend(f"{_text(group)}: {_text(item)}" for item in entries if item)
                values = flattened
            return [_text(item) for item in (values or []) if _text(item)]

        summary = _text(structured_data.get("summary"))
        if summary:
            section_title("Research Profile" if template_name == "research" else "Professional Summary" if template_name == "ats" else "Profile" if template_name == "creative" else "Summary")
            doc.add_paragraph(summary)
        section_order = {
            "ats": [("experience", "Work Experience", ("role", "company", "duration")), ("education", "Education", ("degree", "institution", "graduation_year")), ("skills", "Skills", ()), ("projects", "Projects", ("name", "technologies")), ("certificates", "Certifications", ("name", "issuer")), ("awards", "Awards", ("name", "issuer", "date")), ("languages", "Languages", ("name", "proficiency"))],
            "modern": [("experience", "Experience", ("role", "company", "duration")), ("projects", "Projects", ("name", "technologies")), ("education", "Education", ("degree", "institution", "graduation_year")), ("skills", "Skills", ()), ("certificates", "Certifications", ("name", "issuer")), ("awards", "Awards", ("name", "issuer", "date")), ("languages", "Languages", ("name", "proficiency"))],
            "student": [("education", "Education", ("degree", "institution", "graduation_year")), ("projects", "Academic and Selected Projects", ("name", "technologies")), ("experience", "Internships and Experience", ("role", "company", "duration")), ("skills", "Skills", ()), ("certificates", "Certifications", ("name", "issuer")), ("awards", "Awards", ("name", "issuer", "date")), ("languages", "Languages", ("name", "proficiency"))],
            "developer": [("skills", "Technical Skills", ()), ("projects", "Software Projects", ("name", "technologies")), ("experience", "Experience", ("role", "company", "duration")), ("education", "Education", ("degree", "institution", "graduation_year")), ("certificates", "Certifications", ("name", "issuer")), ("awards", "Awards", ("name", "issuer", "date")), ("languages", "Languages", ("name", "proficiency"))],
            "research": [("education", "Education", ("degree", "institution", "graduation_year")), ("experience", "Research Experience", ("role", "company", "duration")), ("projects", "Research and AI/ML Projects", ("name", "technologies")), ("publications", "Publications", ("title", "venue", "date")), ("skills", "Technical Skills and Methods", ()), ("certificates", "Certifications", ("name", "issuer")), ("awards", "Awards", ("name", "issuer", "date")), ("languages", "Languages", ("name", "proficiency"))],
            "creative": [("projects", "Selected Work", ("name", "technologies")), ("experience", "Experience", ("role", "company", "duration")), ("skills", "Skills", ()), ("education", "Education", ("degree", "institution", "graduation_year")), ("certificates", "Recognition", ("name", "issuer"))],
        }
        for key, label, fields in section_order.get(template_name, section_order["modern"]):
            content = structured_data.get(key)
            if not content:
                continue
            section_title(label)
            if key == "skills":
                for skill in skill_items(content):
                    doc.add_paragraph(skill, style="List Bullet")
            else:
                add_items(content, fields)
        doc.save(output_path)
        return output_path if Path(output_path).is_file() else None
    except Exception as exc:  # noqa: BLE001
        logger.exception("DOCX generation failed: %s", exc)
        return None


def convert_docx_to_pdf(docx_path: str, output_dir: str) -> str | None:
    """Use LibreOffice as a PDF fallback when a TeX engine is unavailable."""
    profile = None
    try:
        profile = Path(tempfile.mkdtemp(prefix=".libreoffice-profile-", dir=output_dir))
        xdg_config = profile / "xdg-config"
        xdg_config.mkdir(mode=0o700)
        env = os.environ.copy()
        env["XDG_CONFIG_HOME"] = str(xdg_config)
        proc = subprocess.run(
            ["libreoffice", "--headless", f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "pdf", "--outdir", output_dir, docx_path],
            capture_output=True, text=True, check=False, timeout=60, env=env,
        )
        pdf_path = str(Path(output_dir) / f"{Path(docx_path).stem}.pdf")
        if proc.returncode != 0:
            logger.warning("LibreOffice PDF conversion failed (exit %s): %s", proc.returncode, proc.stderr[-400:])
        return pdf_path if Path(pdf_path).is_file() else None
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("LibreOffice PDF fallback unavailable: %s", exc)
        return None
    finally:
        if profile:
            shutil.rmtree(profile, ignore_errors=True)


def persist_artifacts(tex_content: str, user_id: str, resume_id: str, generated_dir: str, timestamp: str = "", structured_data: dict[str, Any] | None = None, style: dict[str, Any] | None = None, template_name: str = "modern") -> dict:
    base = Path(generated_dir) / user_id / resume_id
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(base.parent, 0o700)
        os.chmod(base, 0o700)
    except OSError:
        pass
    tex_path = str(base / "resume.tex")
    with open(tex_path, "w", encoding="utf-8") as fh:
        fh.write(tex_content)
    docx_path = create_docx(structured_data or {}, str(base / "resume.docx"), style=style, template_name=template_name)
    pdf_path = compile_pdflatex(tex_path=tex_path, output_dir=str(base))
    if not pdf_path and docx_path:
        pdf_path = convert_docx_to_pdf(docx_path, str(base))
    return {"tex_path": tex_path, "pdf_path": pdf_path, "docx_path": docx_path}
