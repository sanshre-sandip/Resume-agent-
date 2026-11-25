from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
from typing import Any, Optional, Literal
from datetime import datetime


class PersonalInfo(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"full_name": "John Doe"}})
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=20)
    address: Optional[str] = Field(default=None, max_length=512)
    linkedin: Optional[str] = Field(default=None, max_length=255)
    github: Optional[str] = Field(default=None, max_length=255)
    portfolio: Optional[str] = Field(default=None, max_length=255)


class EducationItem(BaseModel):
    degree: str = Field(..., max_length=255)
    institution: str = Field(..., max_length=255)
    graduation_year: str = Field(..., max_length=10)


class ExperienceItem(BaseModel):
    company: str = Field(..., max_length=255)
    role: str = Field(..., max_length=255)
    duration: str = Field(..., max_length=100)
    description: str = Field(..., max_length=4000)


class ProjectItem(BaseModel):
    name: str = Field(..., max_length=255)
    technologies: str = Field(..., max_length=512)
    description: str = Field(..., max_length=4000)
    github_link: Optional[str] = Field(default=None, max_length=255)


class CertificateItem(BaseModel):
    name: str = Field(..., max_length=255)
    issuer: str = Field(..., max_length=255)
    date: str = Field(..., max_length=50)
    file_path: Optional[str] = Field(default=None, max_length=512)


class AIConfig(BaseModel):
    provider: Literal["openai", "anthropic", "google", "openrouter", "groq", "ollama"] = "openai"
    api_key: str = Field(default="", max_length=512)
    model: str = Field(default="", max_length=160)
    base_url: str = Field(default="", max_length=512)
    cloud_authorized: bool = False


class CreateResumeRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=80)
    layout_id: Optional[str] = None
    user_profile: PersonalInfo
    education: list[EducationItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    certificates: list[CertificateItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    target_role: str = Field(..., min_length=2, max_length=255)
    template_name: str = Field(default="modern", max_length=100)
    style: dict[str, str] = Field(default_factory=dict)
    ai_config: AIConfig

    @field_validator("file_name")
    @classmethod
    def normalize_file_name(cls, value: str) -> str:
        value = " ".join(value.strip().split())
        if not value or value in {".", ".."}:
            raise ValueError("Enter a name for this resume file")
        return value


class ResumeChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    ai_config: AIConfig


class LayoutProposal(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: str = Field(..., max_length=300)
    template_name: Literal["modern", "professional", "simple"] = "modern"
    style: dict[str, str] = Field(default_factory=dict)


class GenerateLayoutsRequest(BaseModel):
    request: str = Field(..., min_length=3, max_length=1000)
    ai_config: AIConfig


class SavedLayoutResponse(LayoutProposal):
    id: str
    built_in: bool = False


class ResumeSummaryResponse(BaseModel):
    id: str
    file_name: str
    target_role: str
    template_name: str
    created_at: datetime
    updated_at: datetime


class ResumeResponse(BaseModel):
    id: str
    user_id: str
    target_role: str
    template_name: str
    pdf_path: Optional[str] = None
    docx_path: Optional[str] = None
    created_at: datetime


class ResumeDetailResponse(BaseModel):
    id: str
    file_name: str
    user_id: str
    target_role: str
    template_name: str
    structured_data: Optional[dict[str, Any]] = None
    latex_content: Optional[str] = None
    pdf_path: Optional[str] = None
    docx_path: Optional[str] = None
    source_data: Optional[dict[str, Any]] = None
    style: Optional[dict[str, Any]] = None
    layout_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ResumeChatResponse(BaseModel):
    reply: str
    resume: ResumeDetailResponse
    layouts: list[SavedLayoutResponse] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    role: str
    skills: list[str]
    keywords: list[str]
    requirements: list[str]
    trending_technologies: list[str]
    cached: bool
    updated_at: Optional[datetime] = None


class TemplateResponse(BaseModel):
    name: str
    description: str
    available: bool
