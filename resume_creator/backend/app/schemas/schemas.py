from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
from typing import Any, Optional
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


class CreateResumeRequest(BaseModel):
    user_profile: PersonalInfo
    education: list[EducationItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    certificates: list[CertificateItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    target_role: str = Field(..., min_length=2, max_length=255)
    template_name: str = Field(default="modern", max_length=100)


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
    user_id: str
    target_role: str
    template_name: str
    structured_data: Optional[dict[str, Any]] = None
    latex_content: Optional[str] = None
    pdf_path: Optional[str] = None
    docx_path: Optional[str] = None
    created_at: datetime


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
