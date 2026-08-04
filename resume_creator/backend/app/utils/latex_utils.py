import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def latex_to_pdf(tex_path: str) -> str | None:
    outdir = str(Path(tex_path).parent)
    cmd = ["pdflatex", "-interaction=nonstopmode", f"-output-directory={outdir}", tex_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.warning("pdflatex stderr: %s", proc.stderr[-1000:])
            return None
        pdf_path = str(Path(tex_path).with_suffix(".pdf"))
        return pdf_path if Path(pdf_path).exists() else None
    except FileNotFoundError:
        logger.error("pdflatex is not available. Please install texlive-latex-base")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("latex_to_pdf failed: %s", exc)
        return None


def latex_to_docx(tex_path: str) -> str | None:
    pdf_path = latex_to_pdf(tex_path)
    if not pdf_path:
        return None
    docx_path = str(Path(tex_path).with_suffix(".docx"))
    cmd = ["pandoc", pdf_path, "-o", docx_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.warning("pandoc stderr: %s", proc.stderr[-1000:])
            return None
        return docx_path if Path(docx_path).exists() else None
    except FileNotFoundError:
        logger.error("pandoc is not available. Please install pandoc")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("latex_to_docx failed: %s", exc)
        return None
