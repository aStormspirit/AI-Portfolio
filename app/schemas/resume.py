from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model tuned for OpenAI/OpenRouter structured outputs."""

    model_config = ConfigDict(extra="forbid")


class ContactInfo(StrictModel):
    email: str = Field(default="", description="Email address or empty string")
    phone: str = Field(default="", description="Phone number or empty string")
    linkedin: str = Field(default="", description="LinkedIn URL or empty string")
    github: str = Field(default="", description="GitHub URL or empty string")
    location: str = Field(default="", description="City/country or empty string")
    website: str = Field(default="", description="Personal website or empty string")
    other: str = Field(default="", description="Any other contact info or empty string")

    def items_non_empty(self) -> list[tuple[str, str]]:
        mapping = [
            ("email", self.email),
            ("phone", self.phone),
            ("linkedin", self.linkedin),
            ("github", self.github),
            ("location", self.location),
            ("website", self.website),
            ("other", self.other),
        ]
        return [(key, value) for key, value in mapping if value.strip()]


class ExperienceItem(StrictModel):
    company: str = Field(description="Company or organization name")
    title: str = Field(description="Job title / role")
    start: str = Field(description="Start date as written in the resume")
    end: str = Field(
        default="",
        description="End date or Present/Current; empty string if unknown",
    )
    bullets: list[str] = Field(
        default_factory=list,
        description="Achievement / responsibility bullets",
    )


class EducationItem(StrictModel):
    institution: str = Field(description="School or university")
    degree: str = Field(default="", description="Degree or program")
    years: str = Field(default="", description="Years attended or graduation year")
    details: str = Field(default="", description="Optional notes, GPA, honors")


class ProjectItem(StrictModel):
    name: str = Field(description="Project name")
    description: str = Field(default="", description="Short project description")
    technologies: list[str] = Field(default_factory=list)
    url: str = Field(default="", description="Optional link")


class ResumeDocument(StrictModel):
    full_name: str = Field(description="Candidate full name")
    contacts: ContactInfo = Field(
        default_factory=ContactInfo,
        description="Contact fields",
    )
    summary: str = Field(default="", description="Professional summary / about section")
    skills: list[str] = Field(default_factory=list, description="Skills list")
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    languages: list[str] = Field(
        default_factory=list,
        description="Spoken languages if present",
    )
    certifications: list[str] = Field(default_factory=list)


class VacancyAnalysis(StrictModel):
    role_title: str = Field(description="Target role title from the vacancy")
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(
        default_factory=list,
        description="ATS-relevant keywords",
    )
    tone: str = Field(
        default="professional",
        description="Desired tone for the tailored resume",
    )
    priorities: list[str] = Field(
        default_factory=list,
        description="What the employer emphasizes most",
    )
    summary: str = Field(
        default="",
        description="Short analysis of what matters for this role",
    )


class TailorResult(StrictModel):
    resume: ResumeDocument
    change_notes: list[str] = Field(
        default_factory=list,
        description="Brief notes describing what was adapted and why",
    )
