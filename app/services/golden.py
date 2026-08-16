"""Load golden cover-letter examples used as few-shot style references."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"


@dataclass(frozen=True)
class GoldenExample:
    id: str
    title: str
    letter: str
    path: Path


def load_golden_set(directory: Path | None = None) -> list[GoldenExample]:
    """Load golden letters from ``*.txt`` files in the golden directory.

    Optional first line ``# Title`` is treated as the example title and stripped
    from the letter body. Otherwise the filename stem is used as title/id.
    """
    root = directory or DEFAULT_GOLDEN_DIR
    if not root.is_dir():
        return []

    examples: list[GoldenExample] = []
    for path in sorted(root.glob("*.txt")):
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        lines = raw.splitlines()
        title = path.stem.replace("-", " ").replace("_", " ")
        body_lines = lines
        if lines and lines[0].startswith("#"):
            title = lines[0].lstrip("#").strip() or title
            body_lines = lines[1:]
        letter = "\n".join(body_lines).strip()
        if not letter:
            continue
        examples.append(
            GoldenExample(
                id=path.stem,
                title=title,
                letter=letter,
                path=path,
            )
        )
    return examples


def format_golden_few_shot(examples: list[GoldenExample], limit: int = 3) -> str:
    """Format golden letters for inclusion in the LLM prompt (letters only)."""
    if not examples:
        return "(no examples)"
    blocks: list[str] = []
    for i, ex in enumerate(examples[:limit], start=1):
        blocks.append(f"EXAMPLE {i} — {ex.title}\n{ex.letter}")
    return "\n\n---\n\n".join(blocks)
