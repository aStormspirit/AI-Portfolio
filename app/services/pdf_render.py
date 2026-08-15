from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.schemas.resume import ResumeDocument


class PDFRenderError(Exception):
    """Raised when PDF rendering fails."""


def render_resume_pdf(resume: ResumeDocument, templates_dir: Path) -> bytes:
    """Render a ResumeDocument into PDF bytes via HTML template + WeasyPrint."""
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    try:
        template = env.get_template("resume_pdf.html")
        html = template.render(resume=resume)
        pdf_bytes = HTML(string=html, base_url=str(templates_dir)).write_pdf()
    except Exception as exc:  # noqa: BLE001
        raise PDFRenderError(f"Не удалось сгенерировать PDF: {exc}") from exc

    if not pdf_bytes:
        raise PDFRenderError("Генератор PDF вернул пустой результат.")
    return pdf_bytes
