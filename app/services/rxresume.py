from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings

# rxresu.me caps the base64 payload of a parsed PDF.
MAX_BASE64_CHARS = 13_981_018

# Path segments that are app routes, not `{username}/{slug}` public resumes.
_RESERVED_SEGMENTS = {
    "api",
    "auth",
    "builder",
    "dashboard",
    "resumes",
    "settings",
}
_ID_RE = re.compile(r"^[a-z0-9]{16,32}$", re.IGNORECASE)


class RxResumeError(Exception):
    """Raised when a call to the Reactive Resume API fails."""


@dataclass
class ImportedResume:
    resume_id: str
    title: str
    builder_url: str
    dashboard_url: str


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "resume"


class RxResumeClient:
    """Thin async client over the Reactive Resume OpenAPI surface.

    Flow: parse a PDF into structured resume data, then import that data as a
    new resume in the account tied to the API key.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.rxresume_api_key:
            raise RxResumeError(
                "RXRESUME_API_KEY не задан. Создайте ключ в rxresu.me → Settings → API Keys."
            )
        self._settings = settings
        self._base = settings.rxresume_api_base
        self._headers = {
            "x-api-key": settings.rxresume_api_key,
            "Content-Type": "application/json",
        }

    async def parse_pdf(self, filename: str, pdf_bytes: bytes) -> dict[str, Any]:
        """POST /ai/parse-pdf → structured ResumeData object."""
        encoded = base64.b64encode(pdf_bytes).decode("ascii")
        if len(encoded) > MAX_BASE64_CHARS:
            raise RxResumeError(
                "PDF слишком большой для парсинга. Уменьшите размер файла."
            )

        payload: dict[str, Any] = {
            "file": {"name": filename or "portfolio.pdf", "data": encoded},
        }
        if self._settings.rxresume_ai_provider_id:
            payload["aiProviderId"] = self._settings.rxresume_ai_provider_id

        data = await self._post("/ai/parse-pdf", payload)
        # The endpoint may return the ResumeData directly or wrapped.
        if isinstance(data, dict) and "data" in data and "basics" not in data:
            data = data["data"]
        if not isinstance(data, dict):
            raise RxResumeError("AI-парсер вернул неожиданный ответ.")
        return data

    async def fetch_resume_by_reference(self, reference: str) -> dict[str, Any]:
        """Resolve a rxresu.me link (or bare id) to its ResumeData object."""
        path = self._reference_to_api_path(reference)
        if path is None:
            raise RxResumeError(
                "Не удалось распознать ссылку на резюме. Пришлите ссылку вида "
                "https://rxresu.me/username/slug или ссылку из редактора."
            )
        result = await self._get(path)
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict):
                return data
            if "basics" in result:  # already the ResumeData object
                return result
        raise RxResumeError(
            "По ссылке не удалось получить данные резюме. Проверьте, что оно "
            "публичное или принадлежит вашему аккаунту."
        )

    @staticmethod
    def _reference_to_api_path(reference: str) -> str | None:
        ref = (reference or "").strip()
        if not ref:
            return None

        # Bare resume id.
        if _ID_RE.match(ref):
            return f"/resumes/{ref}"

        if "://" not in ref and not ref.startswith("rxresu"):
            ref_with_scheme = f"https://{ref}" if "/" in ref else ref
        else:
            ref_with_scheme = ref if "://" in ref else f"https://{ref}"

        parsed = urlparse(ref_with_scheme)
        segments = [s for s in parsed.path.split("/") if s]
        if not segments:
            return None

        # Editor / private link: /builder/{id} (or /dashboard/resumes/{id}).
        if segments[0] in {"builder", "dashboard"} and len(segments) >= 2:
            resume_id = segments[-1]
            if resume_id != "resumes":
                return f"/resumes/{resume_id}"

        # Public link: /{username}/{slug}
        if len(segments) >= 2 and segments[0] not in _RESERVED_SEGMENTS:
            username, slug = segments[0], segments[1]
            return f"/resumes/{username}/{slug}"

        return None

    async def import_resume(
        self,
        resume_data: dict[str, Any],
        title: str | None = None,
    ) -> ImportedResume:
        """POST /resumes/import → creates a resume from resume data."""
        title = (title or self._guess_title(resume_data)).strip() or "Resume"
        # A short suffix keeps the slug unique across repeated imports.
        slug = f"{_slugify(title)}-{uuid.uuid4().hex[:6]}"
        payload = {"data": resume_data, "title": title, "slug": slug}
        result = await self._post("/resumes/import", payload)
        resume_id = self._extract_id(result)
        app = self._settings.rxresume_app_base
        return ImportedResume(
            resume_id=resume_id,
            title=title,
            builder_url=f"{app}/builder/{resume_id}",
            dashboard_url=f"{app}/dashboard/resumes",
        )

    # -- internals -------------------------------------------------------

    async def _get(self, path: str) -> Any:
        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise RxResumeError(f"Сеть недоступна при запросе к rxresu.me: {exc}") from exc

        if response.status_code >= 400:
            raise RxResumeError(self._describe_error(response))

        try:
            return response.json()
        except ValueError as exc:
            raise RxResumeError("rxresu.me вернул неожиданный ответ.") from exc

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(url, headers=self._headers, json=payload)
        except httpx.HTTPError as exc:
            raise RxResumeError(f"Сеть недоступна при запросе к rxresu.me: {exc}") from exc

        if response.status_code >= 400:
            raise RxResumeError(self._describe_error(response))

        try:
            return response.json()
        except ValueError:
            text = response.text.strip().strip('"')
            if text:
                return text
            raise RxResumeError("rxresu.me вернул пустой ответ.")

    @staticmethod
    def _describe_error(response: httpx.Response) -> str:
        detail = response.text
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("message") or body.get("error") or detail
        except ValueError:
            pass
        detail = (detail or "").strip()[:300]
        return f"rxresu.me вернул ошибку {response.status_code}: {detail or 'без деталей'}"

    @staticmethod
    def _extract_id(result: Any) -> str:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("id", "resumeId", "_id"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value
        raise RxResumeError("Не удалось определить ID созданного резюме в ответе API.")

    @staticmethod
    def _guess_title(resume_data: dict[str, Any]) -> str:
        basics = resume_data.get("basics") if isinstance(resume_data, dict) else None
        if isinstance(basics, dict):
            name = str(basics.get("name") or "").strip()
            if name:
                return f"{name} — Resume"
        return "Resume"


def looks_like_resume_reference(text: str) -> bool:
    """Heuristic: does this text look like a rxresu.me link or a resume id?"""
    ref = (text or "").strip()
    if not ref or " " in ref or "\n" in ref:
        return False
    if _ID_RE.match(ref):
        return True
    lowered = ref.lower()
    return "rxresu" in lowered or lowered.startswith(("http://", "https://"))
