from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

# rxresu.me caps the base64 payload of a parsed PDF.
MAX_BASE64_CHARS = 13_981_018


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

    async def import_resume(self, resume_data: dict[str, Any]) -> ImportedResume:
        """POST /resumes/import → creates a resume from parsed data."""
        title = self._guess_title(resume_data)
        payload = {"data": resume_data, "title": title, "slug": _slugify(title)}
        result = await self._post("/resumes/import", payload)
        resume_id = self._extract_id(result)
        app = self._settings.rxresume_app_base
        return ImportedResume(
            resume_id=resume_id,
            title=title,
            builder_url=f"{app}/builder/{resume_id}",
            dashboard_url=f"{app}/dashboard/resumes",
        )

    async def create_from_pdf(self, filename: str, pdf_bytes: bytes) -> ImportedResume:
        resume_data = await self.parse_pdf(filename, pdf_bytes)
        return await self.import_resume(resume_data)

    # -- internals -------------------------------------------------------

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
                return f"{name} — Portfolio"
        return "Portfolio"
