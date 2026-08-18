from __future__ import annotations

import copy
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.services.golden import format_golden_few_shot, load_golden_set

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


COVER_LETTER_SYSTEM = """You are an expert career coach who writes personalized cover letters
(сопроводительные письма) for job applications on HH.ru / email / Telegram.

Before writing, analyze the vacancy:
- Extract key requirements, skills, responsibilities, and company values.
- Note the role title, company name, recruiter/hiring manager name if present,
  and where the vacancy was posted if mentioned.
- Find personalization hooks (products, mission, tech stack, culture).

Write in the SAME language as the vacancy. Plain text only: no markdown, no HTML,
no bullet lists, no subject line.

Required length: exactly 2–4 sentences total (not paragraphs). Pack the essentials tightly.

What to cover inside those 2–4 sentences:
- Greeting (by name if known, else a short polite address) + the exact role and source
  ([источник: HH.ru / сайт компании] if unknown).
- Why THIS role/company is interesting: name a concrete product/task/stack item from the vacancy
  (never «Я впечатлён…» / empty praise); tie it to fit or use [что привлекает в компании].
- A brief relevant fit: 1–2 concrete results or strengths mapped to vacancy needs — NOT a resume paste.
  Prefer results («повысил X на Y%», «сократил …»). Unknown facts → [placeholders].
- Benefit for the company + readiness for a call/interview + contacts as
  [телефон] / [email] / [Telegram] (can be the last sentence). Soft CTA is OK.

Style rules:
- Personalized for THIS vacancy — not a generic template.
- Laconic: 2–4 sentences, roughly 250–700 characters.
- Businesslike but not stiff; light creativity only if the vacancy is clearly creative.
- Avoid clichés without proof («ответственный», «коммуникабельный», «быстро обучаюсь») —
  replace with examples or placeholders for examples.
- Never invent employers, dates, metrics, tools, or company facts not present in the vacancy;
  use [placeholders] instead.
- Self-check: grammar/spelling clean; readable in a few seconds.

Hard rules (never break):
1. The cover letter MUST be 2–4 sentences (no more, no fewer). Not 2–4 paragraphs.
2. Do NOT duplicate the resume or paste resume sections. The letter must COMPLEMENT the CV
   and never contradict it.
3. Before writing, use whatever is known about the company from the vacancy (product, domain,
   stack, values). Personalize with those hooks; if little is known, use a short placeholder
   like [что привлекает в компании] — do not invent company facts.
4. Do NOT tell a life biography / chronological life story. Only a brief relevant extract.
5. Do NOT ask questions about salary, schedule, remote policy, benefits, etc. Those topics
   belong in the interview.
6. Avoid empty formalities and tired templates, e.g.:
   «Добрый день! Высылаю свое резюме на вакансию … С уважением, …»
   «Здравствуйте! Ознакомьтесь, пожалуйста, с моим резюме.»
   «Я ответственен/дисциплинирован/стрессоустойчив. Стремлюсь к развитию и умею работать в команде.»
   «Я впечатлён вашим подходом…», «Восхищён современными технологиями», «Мне очень нравится ваш подход».
7. Do NOT mention qualities irrelevant to the vacancy, unrelated experience, or that this role
   is a backup / «запасной аэродром». Never write that you could not find another job and are
   therefore considering anything, or that you want «any role / high management role» vaguely.
   Stay focused on THIS vacancy and the value you bring to THIS company.
8. Do NOT use empty flattery: «Я впечатлён/восхищён/вдохновлён…»,
   «нравится ваш подход», «современные технологии» without a concrete hook from the vacancy.
   Motivation must name a specific product, task, or stack item from the vacancy and tie it
   to candidate fit (or a [placeholder] for a concrete result).

Bad example to avoid (anti-pattern):
«Я не могу найти работу по основной специальности, поэтому рассматриваю другие предложения…
Интересуюсь всем новым. Легко обучаем. Есть опыт продаж и руководящей работы. Думаю, мне
подойдёт должность менеджера или высокая руководящая должность. Готов рассмотреть любые
варианты. Проживаю недалеко от вашей компании.»

Use the GOLDEN EXAMPLES below as style and tone references (example letters only,
not vacancy→letter pairs). Match their quality and specificity, but YOUR letter must
still be only 2–4 sentences — do not copy the examples verbatim or match their length.
"""


CLIENT_OUTREACH_SYSTEM = """You write short SALES outreach messages to potential clients (заказчикам).
Goal: get a reply / call — not to prove technical depth.

Input is a TASK / BRIEF (problem or project need) — not a job vacancy.

Write in the SAME language as the brief. Plain text only: no markdown, no HTML,
no bullet lists, no subject line.

Required length: exactly 2–4 sentences total.

What to cover:
- Short greeting («Здравствуйте!» or by name if known).
- Speak to the client's BUSINESS outcome: what will work for them after the project
  (leads flow, fewer drop-offs, payments, clear funnel stages, reliable handoff between channels).
  Name 1–2 specifics from THEIR brief in plain language (e.g. Instagram→Telegram→обучение→оплата),
  not as an architecture plan.
- Soft confidence that you can deliver this kind of project + CTA (short call) +
  contacts [Telegram]/[email]/[телефон]. Optional: [релевантный кейс] / [срок оценки].

Sales style (must follow):
- Sell the result and peace of mind, not the stack.
- Sound human and commercial: clear benefit → why you → next step.
- Laconic: 2–4 sentences, roughly 250–650 characters.
- At most ONE light tech hint if the brief already names a tool (e.g. GetCourse, Telegram-бот) —
  never a shopping list of technologies.

Hard bans (never write):
- Technical dumps: state-machine, webhooks, merge-rules, ClickHouse, BigQuery, Metabase,
  дедупликация identifiers, API surface, schemas, dashboards stack, etc.
- «подниму / реализую / настрою» followed by a long checklist of components
- «Я понимаю, что вам нужен…», «Как я понял…», «Судя по описанию…»
- Empty flattery, resume dump, biography, budget questions in the first message
- Invented metrics, company names, or tools not in the brief

Bad (too technical — do not imitate):
«Возьму реализацию воронки… подниму бота со state-машиной, синхронизацию через API/webhooks,
единый профиль с дедупликацией, трекинг этапов… аналитика в ClickHouse/BigQuery + Metabase…»

Good direction (sales, shape only):
«Здравствуйте! Могу собрать для вас сквозную воронку Instagram → Telegram → GetCourse с оплатой
и возвратом «отвалившихся» на каждом шаге — без потери заявок и с понятной картиной конверсий.
Делал похожие интеграционные проекты [релевантный кейс]; предложу план и сроки после короткого
созвона: [Telegram].»
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
        self._cover_llm = ChatOpenAI(
            **{
                **kwargs,
                "temperature": settings.cover_letter_temperature,
                "max_tokens": settings.cover_letter_max_tokens,
            }
        )
        self._golden_few_shot = format_golden_few_shot(
            load_golden_set(),
            limit=settings.cover_letter_golden_limit,
        )

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
                (
                    "human",
                    "Analyze this vacancy, then write a personalized cover letter "
                    "following the required structure.\n\n"
                    "GOLDEN EXAMPLES:\n{golden_examples}\n\n"
                    "VACANCY:\n{vacancy}\n\n"
                    "Write the letter now.",
                ),
            ]
        )
        chain = prompt | self._cover_llm
        try:
            result = chain.invoke(
                {
                    "vacancy": vacancy_text,
                    "golden_examples": self._golden_few_shot,
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise AdaptationError(
                f"Не удалось сгенерировать сопроводительное письмо: {exc}"
            ) from exc
        return _response_text(result, empty_error="Модель вернула пустое письмо. Попробуйте ещё раз.")

    def generate_client_message(self, task_description: str) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", CLIENT_OUTREACH_SYSTEM),
                (
                    "human",
                    "Write a short SALES outreach message for this client brief. "
                    "Sell the business outcome, not the architecture.\n\n"
                    "TASK DESCRIPTION:\n{task}\n\n"
                    "Write the message now.",
                ),
            ]
        )
        chain = prompt | self._cover_llm
        try:
            result = chain.invoke({"task": task_description})
        except Exception as exc:  # noqa: BLE001
            raise AdaptationError(
                f"Не удалось сгенерировать сообщение для заказчика: {exc}"
            ) from exc
        return _response_text(
            result,
            empty_error="Модель вернула пустое сообщение. Попробуйте ещё раз.",
        )


def _response_text(result: Any, *, empty_error: str) -> str:
    text = getattr(result, "content", None) or str(result)
    if isinstance(text, list):
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in text
        )
    text = str(text).strip()
    if not text:
        raise AdaptationError(empty_error)
    return text


def _as_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
