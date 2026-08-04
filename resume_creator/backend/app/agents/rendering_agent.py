import logging
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import Any

logger = logging.getLogger(__name__)


class LaTeXRenderer:
    def __init__(self, template_dir: str) -> None:
        if not os.path.isdir(template_dir):
            raise FileNotFoundError(f"Template directory not found: {template_dir}")
        self.env = Environment(
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
        self.template_dir = template_dir

    def list_templates(self) -> list[str]:
        return [p.stem for p in Path(self.template_dir).glob("*.tex") if p.is_file()]

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        safe_name = f"{template_name}.tex" if not template_name.endswith(".tex") else template_name
        template = self.env.get_template(safe_name)
        return template.render(**context)


def render_latex(template_name: str, context: dict[str, Any], template_dir: str) -> str:
    renderer = LaTeXRenderer(template_dir=template_dir)
    return renderer.render(template_name=template_name, context=context)
