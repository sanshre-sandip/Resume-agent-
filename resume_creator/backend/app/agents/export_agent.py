import logging
import shutil
import subprocess
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


def convert_to_docx(pdf_path: str, output_path: str) -> str | None:
    if not Path(pdf_path).exists():
        return None
    try:
        proc = subprocess.run(
            ["pandoc", pdf_path, "-o", output_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning("pandoc stderr: %s", proc.stderr[-800:])
            return None
        return output_path if Path(output_path).exists() else None
    except FileNotFoundError:
        logger.error("pandoc not found in PATH; install pandoc")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("DOCX generation failed: %s", exc)
        return None


def persist_artifacts(tex_content: str, user_id: str, resume_id: str, generated_dir: str, timestamp: str) -> dict:
    base = Path(generated_dir) / user_id / resume_id
    base.mkdir(parents=True, exist_ok=True)
    tex_path = str(base / f"resume_{timestamp}.tex")
    with open(tex_path, "w", encoding="utf-8") as fh:
        fh.write(tex_content)
    pdf_path = compile_pdflatex(tex_path=tex_path, output_dir=str(base))
    docx_path = None
    if pdf_path:
        docx_path = convert_to_docx(pdf_path=pdf_path, output_path=str(base / f"resume_{timestamp}.docx"))
    return {"tex_path": tex_path, "pdf_path": pdf_path, "docx_path": docx_path}
