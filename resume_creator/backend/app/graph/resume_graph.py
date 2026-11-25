import logging
from typing import Any, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from ..config import settings
from ..utils.llm_providers import get_llm_provider
from ..schemas.schemas import CreateResumeRequest
from ..services.research_service import get_or_create_research
from ..agents.optimization_agent import run_optimization_agent
from ..agents.structuring_agent import run_structuring_agent
from ..agents.rendering_agent import LaTeXRenderer
from ..agents.export_agent import persist_artifacts
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class ResumeState(TypedDict, total=False):
    input: dict
    payload: dict
    research_data: dict
    optimized_resume: dict
    structured_data: dict
    latex_content: str
    pdf_path: str
    docx_path: str
    logs: list


async def validate_node(state: ResumeState) -> ResumeState:
    payload = state["payload"] = CreateResumeRequest(**state["input"]).model_dump(
        exclude={"ai_config", "file_name", "layout_id"}
    )
    state.setdefault("logs", []).append("validated")
    return state


async def research_node(state: ResumeState) -> ResumeState:
    role = state["input"]["target_role"]
    llm = get_llm_provider(state["input"]["ai_config"])
    data = await get_or_create_research(llm_provider=llm, role=role)
    state["research_data"] = data
    state.setdefault("logs", []).append("researched")
    return state


async def optimize_node(state: ResumeState) -> ResumeState:
    profile = {
        "personal_info": dict(state["input"]["user_profile"]),
        "education": state["input"].get("education", []),
        "experience": state["input"].get("experience", []),
        "projects": state["input"].get("projects", []),
        "certificates": state["input"].get("certificates", []),
        "skills": state["input"].get("skills", []),
        "target_role": state["input"]["target_role"],
    }
    llm = get_llm_provider(state["input"]["ai_config"])
    optimized = await run_optimization_agent(llm=llm, user_profile=profile, research_data=state["research_data"])
    state["optimized_resume"] = optimized
    state.setdefault("logs", []).append("optimized")
    return state


async def structure_node(state: ResumeState) -> ResumeState:
    llm = get_llm_provider(state["input"]["ai_config"])
    structured = await run_structuring_agent(llm=llm, optimized_resume=state.get("optimized_resume", {}), user_profile=state["payload"] or {})
    state["structured_data"] = structured
    state.setdefault("logs", []).append("structured")
    return state


async def render_node(state: ResumeState) -> ResumeState:
    from ..services.resume_service import build_context

    template_name = state["input"].get("template_name", "modern") or "modern"
    structured = dict(state.get("structured_data") or {})

    header = dict(structured.get("header") or {})
    personal = dict(state["input"].get("user_profile") or {})
    for key in ("full_name", "email", "phone", "address", "linkedin", "github", "portfolio"):
        if not header.get(key) and personal.get(key):
            header[key] = personal[key]
    structured["header"] = header

    renderer = LaTeXRenderer(template_dir=settings.template_dir)
    context = build_context(structured, None, state["input"].get("style"))
    latex = renderer.render(template_name=template_name, context=context)
    state["latex_content"] = latex
    state.setdefault("logs", []).append("rendered")
    return state


async def export_node(state: ResumeState) -> ResumeState:
    user_id = state["input"].get("user_id") or str(uuid.uuid4())
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    artifacts = persist_artifacts(
        tex_content=state.get("latex_content", ""),
        user_id=user_id,
        resume_id=state["input"]["resume_id"],
        generated_dir=settings.generated_dir,
        timestamp=ts,
    )
    state["pdf_path"] = artifacts.get("pdf_path")
    state["docx_path"] = artifacts.get("docx_path")
    state.setdefault("logs", []).append("exported")
    return state


def build_resume_graph():
    graph = StateGraph(ResumeState)
    graph.add_node("validate", validate_node)
    graph.add_node("research", research_node)
    graph.add_node("optimize", optimize_node)
    graph.add_node("structure", structure_node)
    graph.add_node("render", render_node)
    graph.add_node("export", export_node)
    graph.set_entry_point("validate")
    graph.add_edge("validate", "research")
    graph.add_edge("research", "optimize")
    graph.add_edge("optimize", "structure")
    graph.add_edge("structure", "render")
    graph.add_edge("render", "export")
    graph.add_edge("export", END)
    return graph.compile(checkpointer=MemorySaver())
