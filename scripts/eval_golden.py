#!/usr/bin/env python3
"""Validate golden cover-letter examples and optionally smoke-test /vacancy with them.

Examples:
  make test-golden
  .venv/bin/python -m scripts.eval_golden
  .venv/bin/python -m scripts.eval_golden --generate
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings
from app.services.adapt import AdaptationError, ResumeAdapter
from app.services.golden import load_golden_set

SAMPLE_VACANCY = ROOT / "tests" / "fixtures" / "sample_vacancy.txt"

STRUCTURE_HINTS = (
    ("greeting", re.compile(r"(здравствуйте|добрый|уважаем)", re.I)),
    ("role_mention", re.compile(r"(ваканси|позици|роль)", re.I)),
    ("closing", re.compile(r"(спасибо|буду рад|собеседован|тестов)", re.I)),
    ("contacts", re.compile(r"(телефон|email|telegram|@)", re.I)),
)


def _check_structure(letter: str) -> list[str]:
    missing = []
    for name, pattern in STRUCTURE_HINTS:
        if not pattern.search(letter):
            missing.append(name)
    length = len(letter)
    if length < 200:
        missing.append("too_short")
    if length > 2500:
        missing.append("too_long")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate golden cover letters (style examples, not vacancy pairs)"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Also generate a letter for sample_vacancy.txt using golden few-shot",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Override COVER_LETTER_TEMPERATURE (only with --generate)",
    )
    args = parser.parse_args(argv)

    examples = load_golden_set()
    if not examples:
        print("Golden set is empty.", file=sys.stderr)
        return 1

    print(f"Golden letters: {len(examples)}")
    print("=" * 60)

    failures = 0
    for ex in examples:
        missing = _check_structure(ex.letter)
        status = "OK" if not missing else f"WARN missing={missing}"
        print(f"\n### {ex.id} — {ex.title}")
        print(f"{len(ex.letter)} chars | {status}")
        print("-" * 40)
        print(ex.letter)
        if missing:
            failures += 1

    if args.generate:
        get_settings.cache_clear()
        settings = Settings()
        if args.temperature is not None:
            settings.cover_letter_temperature = args.temperature
        vacancy = SAMPLE_VACANCY.read_text(encoding="utf-8").strip()
        print("\n" + "=" * 60)
        print(f"Smoke generate on {SAMPLE_VACANCY.name} (few-shot={settings.cover_letter_golden_limit})")
        try:
            adapter = ResumeAdapter(settings)
            letter = adapter.generate_cover_letter(vacancy)
        except AdaptationError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        missing = _check_structure(letter)
        status = "OK" if not missing else f"WARN missing={missing}"
        print(f"Generated: {len(letter)} chars | {status}")
        print("-" * 40)
        print(letter)
        if missing:
            failures += 1

    print("\n" + "=" * 60)
    print(f"Done. Warnings: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
