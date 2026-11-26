from pydantic import BaseModel, Field, EmailStr, ConfigDict, SecretStr, field_validator
from typing import Any, Optional, Literal
from datetime import datetime
from urllib.parse import urlsplit


def _safe_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not value.startswith(("https://", "http://")):
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a valid http or https URL.")
    return value


class ResumeLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(..., min_length=1, max_length=40)
    url: str = Field(..., min_length=3, max_length=512)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _safe_url(value) or ""


class PersonalInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"full_name": "John Doe"}})
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=7, max_length=20)
    address: Optional[str] = Field(default=None, max_length=512)
    linkedin: Optional[str] = Field(default=None, max_length=255)
    github: Optional[str] = Field(default=None, max_length=255)
    portfolio: Optional[str] = Field(default=None, max_length=255)
    links: list[ResumeLink] = Field(default_factory=list, max_length=12)

    @field_validator("linkedin", "github", "portfolio")
    @classmethod
    def validate_optional_urls(cls, value: str | None) -> str | None:
        return _safe_url(value)


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

    @field_validator("github_link")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return _safe_url(value)


class CertificateItem(BaseModel):
    name: str = Field(..., max_length=255)
    issuer: str = Field(default="", max_length=255)
    date: str = Field(default="", max_length=50)


class AwardItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    issuer: str = Field(default="", max_length=255)
    date: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=2000)


class LanguageItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    proficiency: str = Field(default="", max_length=100)


class PublicationItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    venue: str = Field(default="", max_length=255)
    date: str = Field(default="", max_length=50)
    url: Optional[str] = Field(default=None, max_length=512)
    description: str = Field(default="", max_length=2000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return _safe_url(value)


class AIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["openai", "anthropic", "google", "openrouter", "groq", "ollama"] = "openai"
    model: str = Field(default="", max_length=160)
    cloud_authorized: bool = False
    # Accepted only on AI action requests; never persist or return this field.
    api_key: SecretStr | None = Field(default=None, max_length=512, repr=False)


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class CreateResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str = Field(..., min_length=1, max_length=80)
    layout_id: Optional[str] = None
    user_profile: PersonalInfo
    education: list[EducationItem] = Field(default_factory=list, max_length=40)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=40)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=40)
    certificates: list[CertificateItem] = Field(default_factory=list, max_length=40)
    awards: list[AwardItem] = Field(default_factory=list, max_length=30)
    languages: list[LanguageItem] = Field(default_factory=list, max_length=30)
    publications: list[PublicationItem] = Field(default_factory=list, max_length=30)
    skills: list[str] = Field(default_factory=list, max_length=100)
    target_role: str = Field(..., min_length=2, max_length=255)
    summary: str = Field(default="", max_length=4000)
    template_name: str = Field(default="modern", max_length=100)
    style: dict[str, str] = Field(default_factory=dict)
    page_size: Literal["a4", "letter"] = "a4"
    expected_updated_at: Optional[str] = Field(default=None, max_length=64)
    ai_config: AIConfig = Field(default_factory=AIConfig)

    @field_validator("file_name")
    @classmethod
    def normalize_file_name(cls, value: str) -> str:
        value = " ".join(value.strip().split())
        if not value or value in {".", ".."}:
            raise ValueError("Enter a name for this resume file")
        return value


class ResumeChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation: list[ChatTurn] = Field(default_factory=list, max_length=20)
    ai_config: AIConfig


class ResumeUndoRequest(BaseModel):
    structured_data: dict[str, Any]
    template_name: Literal["ats", "modern", "student", "developer", "research"]
    style: dict[str, str] = Field(default_factory=dict)


class LayoutProposal(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: str = Field(..., max_length=300)
    template_name: Literal["ats", "modern", "student", "developer", "research"] = "modern"
    style: dict[str, str] = Field(default_factory=dict)


class GenerateLayoutsRequest(BaseModel):
    request: str = Field(..., min_length=3, max_length=1000)
    ai_config: AIConfig = Field(default_factory=AIConfig)


class SavedLayoutResponse(LayoutProposal):
    id: str
    built_in: bool = False
    form_choice: bool = False


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
    page_size: Literal["a4", "letter"] = "a4"
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
