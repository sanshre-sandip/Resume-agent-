import logging
import os
import re
from typing import Any
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def get_env(template_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(),
        block_start_string="\\BLOCK{",
        block_end_string="}",
        variable_start_string="\\VAR{",
        variable_end_string="}",
        comment_start_string="\\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
    )


def list_available_templates(template_dir: str | None = None) -> list[dict]:
    template_dir = template_dir or DEFAULT_TEMPLATES_DIR
    if not os.path.isdir(template_dir):
        return []
    items = []
    for path in sorted(Path(template_dir).glob("*.tex")):
        items.append({"name": path.stem, "filename": path.name, "available": True})
    return items


def render_template(template_name: str, context: dict[str, Any], template_dir: str | None = None) -> str:
    tdir = template_dir or DEFAULT_TEMPLATES_DIR
    env = get_env(tdir)
    fname = f"{template_name}.tex" if not template_name.endswith(".tex") else template_name
    return env.get_template(fname).render(**context)


def write_file(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
