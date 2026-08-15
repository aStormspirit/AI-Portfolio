from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.job_store import JobStore
from app.services.llm_pipeline import (
    LLMPipelineError,
    ResumeLLMPipeline,
    resume_preview_markdown,
)
from app.services.pdf_extract import (
    PDFExtractionError,
    extract_text_from_pdf,
    is_pdf_content_type,
    looks_like_pdf,
)
from app.services.pdf_render import PDFRenderError, render_resume_pdf

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))
job_store = JobStore(settings)


def _error_partial(request: Request, message: str) -> HTMLResponse:
    # Return 200 so HTMX always swaps the error into #result.
    logger.warning("adapt failed: %s", message)
    return templates.TemplateResponse(
        request,
        "partials/result.html",
        {"error": message},
    )


@router.post("/adapt", response_class=HTMLResponse)
async def adapt_resume(
    request: Request,
    resume_pdf: UploadFile = File(...),
    vacancy_text: str = Form(...),
) -> HTMLResponse:
    vacancy = (vacancy_text or "").strip()
    if len(vacancy) < 40:
        return _error_partial(
            request,
            "Текст вакансии слишком короткий. Вставьте полное описание вакансии.",
        )

    filename = (resume_pdf.filename or "").lower()
    if not filename.endswith(".pdf") and not is_pdf_content_type(resume_pdf.content_type):
        return _error_partial(request, "Загрузите файл в формате PDF.")

    data = await resume_pdf.read()
    if not data:
        return _error_partial(request, "Файл пустой.")

    if len(data) > settings.max_pdf_size_bytes:
        return _error_partial(
            request,
            f"Файл больше {settings.max_pdf_size_mb} МБ. Уменьшите размер PDF.",
        )

    if not looks_like_pdf(data):
        return _error_partial(request, "Файл не похож на PDF.")

    try:
        resume_text = extract_text_from_pdf(data)
    except PDFExtractionError as exc:
        return _error_partial(request, str(exc))

    try:
        pipeline = ResumeLLMPipeline(settings)

        def _run() -> tuple:
            result = pipeline.run(resume_text, vacancy)
            pdf_bytes = render_resume_pdf(result.resume, settings.templates_dir)
            return result, pdf_bytes

        result, pdf_bytes = await asyncio.to_thread(_run)
    except LLMPipelineError as exc:
        return _error_partial(request, str(exc))
    except PDFRenderError as exc:
        return _error_partial(request, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected adapt error")
        return _error_partial(request, f"Непредвиденная ошибка: {exc}")

    preview = resume_preview_markdown(result.resume)
    record = job_store.save(
        pdf_bytes=pdf_bytes,
        change_notes=result.change_notes,
        preview_markdown=preview,
    )
    logger.info("adapt ok job_id=%s", record.job_id)

    return templates.TemplateResponse(
        request,
        "partials/result.html",
        {
            "error": None,
            "job_id": record.job_id,
            "change_notes": record.change_notes,
            "preview_markdown": record.preview_markdown,
            "auto_download": True,
        },
    )


@router.get("/download/{job_id}", response_model=None)
async def download_pdf(job_id: str) -> FileResponse | HTMLResponse:
    record = job_store.get(job_id)
    if record is None or not record.pdf_path.exists():
        return HTMLResponse(
            "<p>Файл не найден или срок хранения истёк. Сгенерируйте резюме ещё раз.</p>",
            status_code=404,
        )
    return FileResponse(
        path=record.pdf_path,
        media_type="application/pdf",
        filename="tailored_resume.pdf",
    )
