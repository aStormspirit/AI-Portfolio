from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings


@dataclass
class JobRecord:
    job_id: str
    pdf_path: Path
    change_notes: list[str] = field(default_factory=list)
    preview_markdown: str = ""
    created_at: float = field(default_factory=time.time)


class JobStore:
    """Simple in-memory store for generated PDF jobs."""

    def __init__(self, settings: Settings, ttl_seconds: int = 3600) -> None:
        self._settings = settings
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def save(
        self,
        pdf_bytes: bytes,
        change_notes: list[str],
        preview_markdown: str,
    ) -> JobRecord:
        self.cleanup()
        job_id = uuid.uuid4().hex
        pdf_path = self._settings.outputs_dir / f"{job_id}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        record = JobRecord(
            job_id=job_id,
            pdf_path=pdf_path,
            change_notes=change_notes,
            preview_markdown=preview_markdown,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            return None
        if time.time() - record.created_at > self._ttl:
            self.delete(job_id)
            return None
        return record

    def delete(self, job_id: str) -> None:
        with self._lock:
            record = self._jobs.pop(job_id, None)
        if record and record.pdf_path.exists():
            record.pdf_path.unlink(missing_ok=True)

    def cleanup(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                job_id
                for job_id, record in self._jobs.items()
                if now - record.created_at > self._ttl
            ]
        for job_id in expired:
            self.delete(job_id)
