#!/usr/bin/env python3
"""Local runner for /vacancy cover-letter generation.

Examples:
  make test-message
  .venv/bin/python -m scripts.test_message
  .venv/bin/python -m scripts.test_message --vacancy path/to/vacancy.txt
  .venv/bin/python -m scripts.test_message --temperature 0.4 --out letter.txt
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

DEFAULT_VACANCY = ROOT / "tests" / "fixtures" / "sample_vacancy.txt"


def _read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"Файл пустой: {path}")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test /vacancy cover letter locally")
    parser.add_argument(
        "--vacancy",
        type=Path,
        default=DEFAULT_VACANCY,
        help="Path to vacancy text (default: tests/fixtures/sample_vacancy.txt)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Override COVER_LETTER_TEMPERATURE for this run",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override COVER_LETTER_MAX_TOKENS for this run",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to save the generated letter",
    )
    args = parser.parse_args(argv)

    get_settings.cache_clear()
    settings = Settings()
    if args.temperature is not None:
        settings.cover_letter_temperature = args.temperature
    if args.max_tokens is not None:
        settings.cover_letter_max_tokens = args.max_tokens

    vacancy = _read_text(args.vacancy)

    print(f"Model: {settings.llm_model}")
    print(f"Temperature: {settings.cover_letter_temperature}")
    print(f"Max tokens: {settings.cover_letter_max_tokens}")
    print(f"Vacancy: {args.vacancy} ({len(vacancy)} chars)")
    print("-" * 60)

    try:
        adapter = ResumeAdapter(settings)
        letter = adapter.generate_cover_letter(vacancy)
    except AdaptationError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(letter)
    print("-" * 60)
    print(f"Length: {len(letter)} chars")

    if args.out:
        args.out.write_text(letter + "\n", encoding="utf-8")
        print(f"Saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
