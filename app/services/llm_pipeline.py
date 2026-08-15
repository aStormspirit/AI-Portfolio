from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.schemas.resume import ResumeDocument, TailorResult, VacancyAnalysis


STRUCTURE_SYSTEM = """You are an expert resume parser.
Convert raw resume text into the given structured schema.
Rules:
- Preserve facts exactly: names, companies, dates, metrics, degrees.
- Do not invent missing information. Use empty strings/lists when unknown.
- Keep original language of the resume content (Russian or English).
- Put contact fields into contacts.email, contacts.phone, contacts.linkedin, contacts.github, contacts.location, contacts.website (use empty string if unknown).
"""

ANALYZE_SYSTEM = """You are an expert recruiter and ATS specialist.
Analyze the job vacancy and extract structured hiring signals.
Respond in the same language as the vacancy text when writing summary/priorities.
"""

TAILOR_SYSTEM = """You are an expert resume editor who aggressively rewrites EXPERIENCE bullets to match a target job vacancy.

Primary goal for EXPERIENCE sections:
- Rewrite each job's bullets so the candidate appears to have already done work similar to the vacancy's tasks/responsibilities at those previous companies.
- Map vacancy duties onto the candidate's real background (stack, domain, seniority) and phrase bullets as concrete past achievements.
- Prefer wording and keywords from the vacancy (tools, processes, responsibilities) when they plausibly fit the candidate's roles.
- Reorder bullets: most vacancy-relevant first. Drop weak/irrelevant bullets. Add new bullets ONLY if they are a fair reframing of existing experience (same company/period), not new fake jobs.
- Keep 3–6 strong bullets per role when possible.
- Write bullets in past tense (or present for current role), action + context + result. Keep original metrics if present; do not invent new numbers.

Hard constraints (do not break):
1. NEVER invent companies, job titles, employment dates, education, certifications, or numeric metrics that were not in the original resume.
2. NEVER invent tools/tech the candidate clearly never used; you MAY emphasize adjacent real skills from the resume stack.
3. Keep company names and date ranges unchanged. Job titles may be lightly normalized but stay truthful.
4. Rewrite summary and reorder skills for the vacancy; put matching skills first.
5. change_notes: short list of what was reframed for EXPERIENCE and why (same language as vacancy).
6. Keep resume language consistent with the original resume (Russian stays Russian, English stays English) unless vacancy requires otherwise; default to original.
"""


class LLMPipelineError(Exception):
    """Raised when the LLM adaptation pipeline fails."""


class ResumeLLMPipeline:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise LLMPipelineError(
                "OPENAI_API_KEY не задан. Скопируйте .env.example в .env и укажите ключ."
            )
        kwargs: dict = {
            "model": settings.llm_model,
            "api_key": settings.openai_api_key,
            "temperature": 0.35,
            "timeout": 120,
            "max_retries": 2,
        }
        base_url = settings.resolved_openai_base_url
        if base_url:
            kwargs["base_url"] = base_url
        self._llm = ChatOpenAI(**kwargs)

    def _structured(self, schema: type):
        # function_calling is more compatible with OpenRouter providers than json_schema.
        return self._llm.with_structured_output(schema, method="function_calling")

    def structure_resume(self, raw_text: str) -> ResumeDocument:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", STRUCTURE_SYSTEM),
                (
                    "human",
                    "Parse this resume into the structured schema.\n\nRESUME TEXT:\n{resume_text}",
                ),
            ]
        )
        chain = prompt | self._structured(ResumeDocument)
        try:
            result = chain.invoke({"resume_text": raw_text})
        except Exception as exc:  # noqa: BLE001
            raise LLMPipelineError(f"Не удалось разобрать резюме: {exc}") from exc
        if not isinstance(result, ResumeDocument):
            result = ResumeDocument.model_validate(result)
        if not result.full_name and not result.experience and not result.skills:
            raise LLMPipelineError("Модель не смогла извлечь структуру резюме из текста.")
        return result

    def analyze_vacancy(self, vacancy_text: str) -> VacancyAnalysis:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ANALYZE_SYSTEM),
                (
                    "human",
                    "Analyze this job vacancy.\n\nVACANCY:\n{vacancy_text}",
                ),
            ]
        )
        chain = prompt | self._structured(VacancyAnalysis)
        try:
            result = chain.invoke({"vacancy_text": vacancy_text})
        except Exception as exc:  # noqa: BLE001
            raise LLMPipelineError(f"Не удалось проанализировать вакансию: {exc}") from exc
        if not isinstance(result, VacancyAnalysis):
            result = VacancyAnalysis.model_validate(result)
        return result

    def tailor_resume(
        self,
        resume: ResumeDocument,
        vacancy: VacancyAnalysis,
        vacancy_text: str,
    ) -> TailorResult:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", TAILOR_SYSTEM),
                (
                    "human",
                    (
                        "Rewrite the resume for this vacancy with STRONG focus on EXPERIENCE bullets.\n"
                        "For every experience role, rewrite bullets as if the candidate already performed "
                        "vacancy-like tasks in that company (truthful reframing only).\n\n"
                        "STRUCTURED RESUME (JSON):\n{resume_json}\n\n"
                        "VACANCY ANALYSIS (JSON):\n{vacancy_json}\n\n"
                        "FULL VACANCY TEXT:\n{vacancy_text}\n\n"
                        "Return the tailored resume and change_notes describing EXPERIENCE rewrites."
                    ),
                ),
            ]
        )
        chain = prompt | self._structured(TailorResult)
        try:
            result = chain.invoke(
                {
                    "resume_json": resume.model_dump_json(indent=2),
                    "vacancy_json": vacancy.model_dump_json(indent=2),
                    "vacancy_text": vacancy_text,
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMPipelineError(f"Не удалось адаптировать резюме: {exc}") from exc
        if not isinstance(result, TailorResult):
            result = TailorResult.model_validate(result)
        return result

    def run(self, resume_text: str, vacancy_text: str) -> TailorResult:
        structured = self.structure_resume(resume_text)
        analysis = self.analyze_vacancy(vacancy_text)
        tailored = self.tailor_resume(structured, analysis, vacancy_text)
        # Attach vacancy summary into change notes header context if empty.
        if not tailored.change_notes and analysis.summary:
            tailored.change_notes = [
                f"Адаптация под роль: {analysis.role_title}",
                analysis.summary,
            ]
        return tailored


def resume_preview_markdown(resume: ResumeDocument) -> str:
    """Build a simple markdown preview for the UI."""
    lines: list[str] = [f"# {resume.full_name}", ""]

    if resume.contacts:
        contact_bits = [
            f"**{k}:** {v}" for k, v in resume.contacts.items_non_empty()
        ]
        if contact_bits:
            lines.append(" | ".join(contact_bits))
            lines.append("")

    if resume.summary:
        lines.extend(["## Summary", resume.summary, ""])

    if resume.skills:
        lines.extend(["## Skills", ", ".join(resume.skills), ""])

    if resume.experience:
        lines.append("## Experience")
        for item in resume.experience:
            period = f"{item.start} — {item.end or 'Present'}"
            lines.append(f"### {item.title} @ {item.company}")
            lines.append(f"*{period}*")
            for bullet in item.bullets:
                lines.append(f"- {bullet}")
            lines.append("")

    if resume.education:
        lines.append("## Education")
        for edu in resume.education:
            title = " — ".join(part for part in [edu.degree, edu.institution] if part)
            lines.append(f"- **{title}** {edu.years}".strip())
            if edu.details:
                lines.append(f"  - {edu.details}")
        lines.append("")

    if resume.projects:
        lines.append("## Projects")
        for project in resume.projects:
            lines.append(f"### {project.name}")
            if project.description:
                lines.append(project.description)
            if project.technologies:
                lines.append(f"Tech: {', '.join(project.technologies)}")
            lines.append("")

    if resume.languages:
        lines.extend(["## Languages", ", ".join(resume.languages), ""])

    if resume.certifications:
        lines.extend(["## Certifications", ""])
        for cert in resume.certifications:
            lines.append(f"- {cert}")

    return "\n".join(lines).strip()


def dump_resume_json(resume: ResumeDocument) -> str:
    return json.dumps(resume.model_dump(), ensure_ascii=False, indent=2)
