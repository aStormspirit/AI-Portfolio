from __future__ import annotations

import copy
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings

TAILOR_SYSTEM = """You are an expert resume editor who rewrites a resume to match a target job vacancy.

The resume content fields are HTML (they may contain <p>, <ul>, <li>, <strong>). Keep them valid HTML.

Goals:
- Rewrite the professional SUMMARY so it targets the vacancy, using the candidate's real background.
- Rewrite each EXPERIENCE entry's bullets so the candidate appears to have already done vacancy-like
  work at those companies. Map vacancy duties onto the candidate's real roles and phrase them as concrete
  past achievements. Reorder bullets: most vacancy-relevant first. Keep 3-6 strong bullets per role.
  Use <ul><li>…</li></ul> for bullet lists.
- Reorder skills so the ones matching the vacancy come first.

Hard constraints (never break):
1. NEVER invent companies, job titles, employment dates, education, certifications, or numeric metrics
   that were not in the original resume.
2. NEVER invent tools/tech the candidate clearly never used; you MAY emphasize adjacent real skills.
3. Keep the original language of the resume (Russian stays Russian, English stays English).
4. skills_order must only contain skill names taken from the provided skills list (reordered, not invented).
5. change_notes: a short list (same language as the resume) describing what was reframed and why.
"""


COVER_LETTER_SYSTEM = """You are an expert career writer. Write a concise, compelling cover letter tailored to the given job vacancy.

Rules:
- Base the letter on the vacancy: address its key requirements, responsibilities, and the company/role if named.
- Structure: greeting, a strong opening hook, one or two short paragraphs matching a candidate to the role, and a closing with a call to action and sign-off.
- Keep it ~200-280 words. Professional but warm. Plain text only (no markdown), suitable as a message/email body.
- Write in the SAME language as the vacancy text.
- Where personal specifics are unknown, use clear placeholders in square brackets like [Ваше имя] / [Your Name], [компания], [достижение]. Never invent concrete facts, employers, or metrics.
"""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExperienceEdit(StrictModel):
    index: int = Field(description="Index of the experience item being rewritten")
    summary: str = Field(description="Rewritten bullets as HTML (<ul><li>…</li></ul>)")


class AdaptationResult(StrictModel):
    summary: str = Field(default="", description="Rewritten professional summary as HTML")
    experiences: list[ExperienceEdit] = Field(default_factory=list)
    skills_order: list[str] = Field(
        default_factory=list,
        description="Skill names reordered by relevance to the vacancy",
    )
    change_notes: list[str] = Field(default_factory=list)


class AdaptationError(Exception):
    """Raised when the LLM adaptation fails."""


def _section_items(resume_data: dict[str, Any], name: str) -> list[dict[str, Any]]:
    sections = resume_data.get("sections")
    if not isinstance(sections, dict):
        return []
    section = sections.get(name)
    if not isinstance(section, dict):
        return []
    items = section.get("items")
    return items if isinstance(items, list) else []


def _summary_node(resume_data: dict[str, Any]) -> dict[str, Any] | None:
    summary = resume_data.get("summary")
    if isinstance(summary, dict):
        return summary
    sections = resume_data.get("sections")
    if isinstance(sections, dict) and isinstance(sections.get("summary"), dict):
        return sections["summary"]
    return None


def extract_editable(resume_data: dict[str, Any]) -> dict[str, Any]:
    summary_node = _summary_node(resume_data)
    experiences = [
        {
            "index": i,
            "company": str(item.get("company") or item.get("name") or ""),
            "position": str(item.get("position") or ""),
            "summary": str(item.get("summary") or ""),
        }
        for i, item in enumerate(_section_items(resume_data, "experience"))
    ]
    skills = [
        str(item.get("name") or "")
        for item in _section_items(resume_data, "skills")
        if str(item.get("name") or "")
    ]
    return {
        "summary": str(summary_node.get("content") or "") if summary_node else "",
        "experiences": experiences,
        "skills": skills,
    }


def merge_adaptation(
    resume_data: dict[str, Any],
    result: AdaptationResult,
) -> dict[str, Any]:
    """Return a deep copy of resume_data with tailored text merged in."""
    adapted = copy.deepcopy(resume_data)

    if result.summary:
        node = _summary_node(adapted)
        if node is not None:
            node["content"] = result.summary

    experience_items = _section_items(adapted, "experience")
    for edit in result.experiences:
        if 0 <= edit.index < len(experience_items) and edit.summary:
            experience_items[edit.index]["summary"] = edit.summary

    if result.skills_order:
        skill_items = _section_items(adapted, "skills")
        order = {name.strip().lower(): pos for pos, name in enumerate(result.skills_order)}
        skill_items.sort(
            key=lambda item: order.get(str(item.get("name") or "").strip().lower(), 10_000)
        )

    return adapted


class ResumeAdapter:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise AdaptationError(
                "OPENAI_API_KEY не задан. Укажите ключ OpenAI/OpenRouter в .env."
            )
        kwargs: dict[str, Any] = {
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

    def adapt(self, resume_data: dict[str, Any], vacancy_text: str) -> tuple[dict[str, Any], list[str]]:
        editable = extract_editable(resume_data)
        if not editable["summary"] and not editable["experiences"]:
            raise AdaptationError(
                "В резюме не нашлось разделов «О себе»/«Опыт» для адаптации."
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", TAILOR_SYSTEM),
                (
                    "human",
                    "Adapt this resume to the vacancy. Rewrite the summary and each experience "
                    "entry's HTML bullets, and reorder skills.\n\n"
                    "VACANCY:\n{vacancy}\n\n"
                    "RESUME SUMMARY (HTML):\n{summary}\n\n"
                    "EXPERIENCE ENTRIES (JSON):\n{experiences}\n\n"
                    "SKILLS:\n{skills}",
                ),
            ]
        )
        chain = prompt | self._llm.with_structured_output(
            AdaptationResult, method="function_calling"
        )
        try:
            result = chain.invoke(
                {
                    "vacancy": vacancy_text,
                    "summary": editable["summary"] or "(empty)",
                    "experiences": _as_json(editable["experiences"]),
                    "skills": ", ".join(editable["skills"]) or "(none)",
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise AdaptationError(f"Не удалось адаптировать резюме: {exc}") from exc

        if not isinstance(result, AdaptationResult):
            result = AdaptationResult.model_validate(result)

        merged = merge_adaptation(resume_data, result)
        return merged, result.change_notes

    def generate_cover_letter(self, vacancy_text: str) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", COVER_LETTER_SYSTEM),
                ("human", "VACANCY:\n{vacancy}\n\nWrite the cover letter now."),
            ]
        )
        chain = prompt | self._llm
        try:
            result = chain.invoke({"vacancy": vacancy_text})
        except Exception as exc:  # noqa: BLE001
            raise AdaptationError(
                f"Не удалось сгенерировать сопроводительное письмо: {exc}"
            ) from exc
        text = getattr(result, "content", None) or str(result)
        text = text.strip()
        if not text:
            raise AdaptationError("Модель вернула пустое письмо. Попробуйте ещё раз.")
        return text


def _as_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
