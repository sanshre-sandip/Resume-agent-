import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..utils.llm_providers import LLMProvider

SYSTEM_PROMPT = """You are the user's resume editing assistant.
Help edit the current resume content, its visual format, and wording. Be concise and friendly.
Never invent jobs, dates, education, skills, numbers, or achievements. Ask a short follow-up
when a requested factual change needs information the user has not provided. If the request is
only a question, answer it and leave the resume unchanged.

You may choose only these templates: ats, modern, student, developer, research.
Allowed style values:
- accent_color: any six-digit hex color, without # (for example, 15B8A6)
- font_size: 10pt, 11pt, 12pt
- paper_size: a4paper, letterpaper
- margin: 1.4cm, 1.8cm, 2cm
- header_alignment: left, center
- section_style: accent-rule, uppercase-rule, minimal
- spacing: compact, balanced, airy
- show_logo: yes or no. A logo is a small monogram made from the resume owner's initials.
- contact_layout: inline or separate. Inline places email, phone, location, and every link on one line.

Return ONLY one JSON object with keys:
reply (string),
structured_data (the complete updated resume JSON with header, summary, experience, projects,
education, skills, certificates, awards, languages, and publications),
template_name (one allowed template),
style (object containing the allowed style settings, including accent_color, show_logo, and contact_layout).
layouts (an array of zero to three new layout suggestions, each with name, description,
template_name, and style. When the user asks for more layout ideas, return two or three
distinct suggestions and leave the current resume content and layout unchanged. Otherwise return
an empty array.)
Treat formatting requests such as "put my links on one line" as clear instructions: use contact_layout inline, keep every existing link, and do not ask whether another link should be removed. Preserve every field the user did not ask to change. Output no markdown or text outside JSON."""


def edit_resume(
    llm: LLMProvider,
    message: str,
    structured_data: dict[str, Any],
    template_name: str,
    style: dict[str, Any],
    conversation: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    conversation_text = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')[:2000]}"
        for item in (conversation or [])[-12:]
        if item.get("role") in {"user", "assistant"}
    )
    prompt = {
        "current_resume": structured_data,
        "current_template": template_name,
        "current_style": style,
        "recent_chat": conversation_text,
        "user_request": message,
    }
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(prompt, ensure_ascii=False)),
    ])
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if not match:
        raise ValueError("The AI returned an unreadable edit. Please try again.")
    result = json.loads(match.group(0))
    if not isinstance(result.get("structured_data"), dict):
        result["structured_data"] = structured_data
    else:
        for key in ("awards", "languages", "publications"):
            if key not in result["structured_data"]:
                result["structured_data"][key] = structured_data.get(key, [])
    if result.get("template_name") not in {"ats", "modern", "student", "developer", "research"}:
        result["template_name"] = template_name
    if not isinstance(result.get("style"), dict):
        result["style"] = style
    else:
        result["style"] = {**style, **result["style"]}
    if not isinstance(result.get("layouts"), list):
        result["layouts"] = []
    result["layouts"] = [item for item in result["layouts"][:3] if isinstance(item, dict)]
    if not isinstance(result.get("reply"), str):
        result["reply"] = "I’ve updated the resume. Have a look and let me know what you’d like to adjust next."
    return result
