#!/usr/bin/env python3
"""Local runner for /message client-outreach generation.

Examples:
  make test-client-message
  .venv/bin/python -m scripts.test_client_message
  .venv/bin/python -m scripts.test_client_message --task path/to/task.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings
from app.services.adapt import AdaptationError, ResumeAdapter

DEFAULT_TASK = ROOT / "tests" / "fixtures" / "sample_client_task.txt"


def _read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"Файл пустой: {path}")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test /message client outreach locally")
    parser.add_argument(
        "--task",
        type=Path,
        default=DEFAULT_TASK,
        help="Path to task description (default: tests/fixtures/sample_client_task.txt)",
    )
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    get_settings.cache_clear()
    settings = Settings()
    if args.temperature is not None:
        settings.cover_letter_temperature = args.temperature

    task = _read_text(args.task)
    print(f"Model: {settings.llm_model}")
    print(f"Task: {args.task} ({len(task)} chars)")
    print("-" * 60)

    try:
        adapter = ResumeAdapter(settings)
        text = adapter.generate_client_message(task)
    except AdaptationError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(text)
    print("-" * 60)
    print(f"Length: {len(text)} chars")
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
