from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.adapt import AdaptationError, ResumeAdapter
from app.services.golden import format_golden_few_shot, load_golden_set

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VACANCY = ROOT / "tests" / "fixtures" / "sample_vacancy.txt"
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"


def _settings(**overrides) -> Settings:
    base = {
        "openai_api_key": "sk-test",
        "llm_model": "gpt-4o-mini",
        "cover_letter_temperature": 0.55,
        "cover_letter_max_tokens": 900,
        "cover_letter_golden_limit": 3,
    }
    base.update(overrides)
    return Settings(**base)


def test_sample_vacancy_fixture_exists() -> None:
    assert FIXTURE_VACANCY.is_file()
    text = FIXTURE_VACANCY.read_text(encoding="utf-8").strip()
    assert len(text) >= 40


def test_golden_set_has_at_least_three_letters() -> None:
    examples = load_golden_set(GOLDEN_DIR)
    assert len(examples) >= 3
    for ex in examples:
        assert ex.letter
        assert ex.title
        assert 200 <= len(ex.letter) <= 2500


def test_format_golden_few_shot_is_letters_only() -> None:
    examples = load_golden_set(GOLDEN_DIR)
    text = format_golden_few_shot(examples, limit=2)
    assert "EXAMPLE 1" in text
    assert "EXAMPLE 2" in text
    assert "VACANCY:" not in text
    assert "COVER LETTER:" not in text
    assert examples[0].letter[:40] in text


def test_generate_cover_letter_passes_golden_examples() -> None:
    settings = _settings()
    vacancy = FIXTURE_VACANCY.read_text(encoding="utf-8")
    captured: dict = {}

    chain = MagicMock()

    def fake_invoke(payload):
        captured["payload"] = payload
        return SimpleNamespace(
            content=(
                "Здравствуйте! Меня заинтересовала позиция Python Backend Developer. "
                "Готов обсудить детали.\n\n[Ваше имя]"
            )
        )

    chain.invoke.side_effect = fake_invoke
    prompt = MagicMock()
    prompt.__or__.return_value = chain

    with (
        patch("app.services.adapt.ChatOpenAI", return_value=MagicMock()),
        patch("app.services.adapt.ChatPromptTemplate") as prompt_cls,
    ):
        prompt_cls.from_messages.return_value = prompt
        adapter = ResumeAdapter(settings)
        letter = adapter.generate_cover_letter(vacancy)

    assert "Python Backend Developer" in letter or "[Ваше имя]" in letter
    assert "FastAPI" in captured["payload"]["vacancy"]
    assert "EXAMPLE 1" in captured["payload"]["golden_examples"]
    assert "VACANCY:" not in captured["payload"]["golden_examples"]


def test_generate_client_message_uses_task() -> None:
    settings = _settings()
    task = (
        "Нужен backend для записи клиентов: FastAPI, Telegram-бот, деплой на VPS. "
        "Сейчас всё в Excel."
    )
    captured: dict = {}

    chain = MagicMock()

    def fake_invoke(payload):
        captured["payload"] = payload
        return SimpleNamespace(
            content=(
                "Здравствуйте! Могу собрать сквозную воронку Instagram → Telegram → GetCourse "
                "с оплатой и возвратом отвалившихся на каждом шаге — без потери заявок. "
                "Делал похожие проекты [релевантный кейс]; обсудим план на коротком созвоне: [Telegram]."
            )
        )

    chain.invoke.side_effect = fake_invoke
    prompt = MagicMock()
    prompt.__or__.return_value = chain

    with (
        patch("app.services.adapt.ChatOpenAI", return_value=MagicMock()),
        patch("app.services.adapt.ChatPromptTemplate") as prompt_cls,
    ):
        prompt_cls.from_messages.return_value = prompt
        adapter = ResumeAdapter(settings)
        text = adapter.generate_client_message(task)

    assert "FastAPI" in text or "Telegram" in text
    assert "Excel" in captured["payload"]["task"]


def test_generate_cover_letter_rejects_empty_model_output() -> None:
    settings = _settings()
    chain = MagicMock()
    chain.invoke.return_value = SimpleNamespace(content="   ")
    prompt = MagicMock()
    prompt.__or__.return_value = chain

    with (
        patch("app.services.adapt.ChatOpenAI", return_value=MagicMock()),
        patch("app.services.adapt.ChatPromptTemplate") as prompt_cls,
    ):
        prompt_cls.from_messages.return_value = prompt
        adapter = ResumeAdapter(settings)
        with pytest.raises(AdaptationError, match="пустое"):
            adapter.generate_cover_letter("x" * 50)


def test_cover_letter_settings_defaults() -> None:
    settings = Settings(openai_api_key="sk-test")
    assert settings.cover_letter_temperature == 0.55
    assert settings.cover_letter_max_tokens == 900
    assert settings.cover_letter_golden_limit == 3
