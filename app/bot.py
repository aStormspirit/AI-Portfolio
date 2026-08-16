from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import Settings, get_settings
from app.services.adapt import AdaptationError, ResumeAdapter
from app.services.rxresume import (
    RxResumeClient,
    RxResumeError,
    looks_like_resume_reference,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

STATE_KEY = "state"
RESUME_KEY = "resume_data"
STATE_AWAIT_RESUME = "await_resume"
STATE_AWAIT_VACANCY = "await_vacancy"
STATE_AWAIT_COVER = "await_cover"
MIN_VACANCY_LEN = 40

START_TEXT = (
    "👋 Привет! Я помогаю с трудоустройством:\n\n"
    "📄 /portfolio — адаптировать резюме под вакансию и загрузить в Reactive Resume\n"
    "   1) ссылка на резюме из rxresu.me (лучше всего) или PDF-файл\n"
    "   2) текст вакансии → новое резюме в rxresu.me\n\n"
    "✉️ /vacancy — сгенерировать сопроводительное письмо по тексту вакансии\n\n"
    "Отменить текущий шаг — /cancel."
)

COVER_PROMPT = (
    "✉️ Пришлите текст вакансии — сгенерирую сопроводительное письмо под неё.\n\n"
    "Отменить — /cancel."
)

RESUME_PROMPT = (
    "📄 Пришлите резюме:\n"
    "• ссылку из rxresu.me (например https://rxresu.me/username/slug или ссылку из редактора),\n"
    "• либо PDF-файл резюме.\n\n"
    "Отменить — /cancel."
)

VACANCY_PROMPT = (
    "✅ Резюме принято.\n\n"
    "Теперь пришлите текст вакансии целиком — под неё я адаптирую резюме."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _reset(context)
    await update.message.reply_text(START_TEXT, disable_web_page_preview=True)


async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _reset(context)
    context.user_data[STATE_KEY] = STATE_AWAIT_RESUME
    await update.message.reply_text(RESUME_PROMPT, disable_web_page_preview=True)


async def vacancy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _reset(context)
    context.user_data[STATE_KEY] = STATE_AWAIT_COVER
    await update.message.reply_text(COVER_PROMPT)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _reset(context)
    await update.message.reply_text("Ок, отменил. Наберите /portfolio или /vacancy, когда будете готовы.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    document = message.document

    if context.user_data.get(STATE_KEY) != STATE_AWAIT_RESUME:
        await message.reply_text("Сначала наберите /portfolio.")
        return

    settings: Settings = context.bot_data["settings"]
    filename = document.file_name or "resume.pdf"
    is_pdf = (document.mime_type == "application/pdf") or filename.lower().endswith(".pdf")
    if not is_pdf:
        await message.reply_text("Нужен PDF-файл или ссылка на резюме из rxresu.me.")
        return
    if document.file_size and document.file_size > settings.max_pdf_size_bytes:
        await message.reply_text(
            f"Файл больше {settings.max_pdf_size_mb} МБ. Уменьшите размер PDF."
        )
        return

    status = await message.reply_text("⏳ Распознаю PDF через rxresu.me…")
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    try:
        tg_file = await context.bot.get_file(document.file_id)
        pdf_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to download telegram file")
        await status.edit_text(f"Не удалось скачать файл из Telegram: {exc}")
        return

    client: RxResumeClient = context.bot_data["rxresume"]
    try:
        resume_data = await client.parse_pdf(filename, pdf_bytes)
    except RxResumeError as exc:
        await status.edit_text(f"❌ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected parse error")
        await status.edit_text(f"Непредвиденная ошибка: {exc}")
        return

    _store_resume(context, resume_data)
    await status.edit_text(VACANCY_PROMPT)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    text = (message.text or "").strip()
    state = context.user_data.get(STATE_KEY)

    if state == STATE_AWAIT_RESUME:
        await _handle_resume_link(update, context, text)
        return

    if state == STATE_AWAIT_VACANCY:
        await _handle_vacancy(update, context, text)
        return

    if state == STATE_AWAIT_COVER:
        await _handle_cover(update, context, text)
        return

    await message.reply_text("Наберите /portfolio или /vacancy, чтобы начать.")


async def _handle_resume_link(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    message = update.message
    if not looks_like_resume_reference(text):
        await message.reply_text(
            "Это не похоже на ссылку на резюме. Пришлите ссылку из rxresu.me или PDF-файл."
        )
        return

    client: RxResumeClient = context.bot_data["rxresume"]
    status = await message.reply_text("⏳ Загружаю резюме по ссылке…")
    try:
        resume_data = await client.fetch_resume_by_reference(text)
    except RxResumeError as exc:
        await status.edit_text(f"❌ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected fetch error")
        await status.edit_text(f"Непредвиденная ошибка: {exc}")
        return

    _store_resume(context, resume_data)
    await status.edit_text(VACANCY_PROMPT)


async def _handle_vacancy(
    update: Update, context: ContextTypes.DEFAULT_TYPE, vacancy: str
) -> None:
    message = update.message
    if len(vacancy) < MIN_VACANCY_LEN:
        await message.reply_text(
            "Текст вакансии слишком короткий. Вставьте полное описание вакансии."
        )
        return

    resume_data = context.user_data.get(RESUME_KEY)
    if not resume_data:
        _reset(context)
        await message.reply_text("Резюме потерялось. Начните заново: /portfolio.")
        return

    status = await message.reply_text("🛠 Адаптирую резюме под вакансию…")
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)

    adapter: ResumeAdapter = context.bot_data["adapter"]
    client: RxResumeClient = context.bot_data["rxresume"]
    try:
        adapted, change_notes = await asyncio.to_thread(
            adapter.adapt, resume_data, vacancy
        )
        await status.edit_text("📤 Загружаю новое резюме в rxresu.me…")
        resume = await client.import_resume(adapted, title=_adapted_title(resume_data))
    except AdaptationError as exc:
        await status.edit_text(f"❌ {exc}")
        return
    except RxResumeError as exc:
        await status.edit_text(f"❌ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected adaptation error")
        await status.edit_text(f"Непредвиденная ошибка: {exc}")
        return

    _reset(context)
    notes = ""
    if change_notes:
        bullets = "\n".join(f"• {note}" for note in change_notes[:8])
        notes = f"\n\nЧто изменилось:\n{bullets}"
    await status.edit_text(
        "✅ Готово! Адаптированное резюме создано в rxresu.me.\n\n"
        f"«{resume.title}»\n"
        f"🖊 Редактор: {resume.builder_url}\n"
        f"📁 Все резюме: {resume.dashboard_url}"
        f"{notes}\n\n"
        "Ещё одна вакансия? Отправьте /portfolio.",
        disable_web_page_preview=True,
    )


async def _handle_cover(
    update: Update, context: ContextTypes.DEFAULT_TYPE, vacancy: str
) -> None:
    message = update.message
    if len(vacancy) < MIN_VACANCY_LEN:
        await message.reply_text(
            "Текст вакансии слишком короткий. Вставьте полное описание вакансии."
        )
        return

    status = await message.reply_text("✍️ Пишу сопроводительное письмо…")
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)

    adapter: ResumeAdapter = context.bot_data["adapter"]
    try:
        letter = await asyncio.to_thread(adapter.generate_cover_letter, vacancy)
    except AdaptationError as exc:
        await status.edit_text(f"❌ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected cover letter error")
        await status.edit_text(f"Непредвиденная ошибка: {exc}")
        return

    _reset(context)
    await status.delete()
    # Long letters can exceed one Telegram message; send in ~4000-char chunks.
    for chunk in _split_message(letter, 4000):
        await message.reply_text(chunk)
    await message.reply_text("Готово. Ещё одно письмо? — /vacancy. Резюме под вакансию — /portfolio.")


def _split_message(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


def _reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(STATE_KEY, None)
    context.user_data.pop(RESUME_KEY, None)


def _store_resume(context: ContextTypes.DEFAULT_TYPE, resume_data: dict) -> None:
    context.user_data[RESUME_KEY] = resume_data
    context.user_data[STATE_KEY] = STATE_AWAIT_VACANCY


def _adapted_title(resume_data: dict) -> str:
    basics = resume_data.get("basics") if isinstance(resume_data, dict) else None
    name = ""
    if isinstance(basics, dict):
        name = str(basics.get("name") or "").strip()
    return f"{name} — под вакансию".strip(" —") if name else "Резюме под вакансию"


def build_application(settings: Settings) -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не задан. Получите токен у @BotFather и добавьте в .env."
        )

    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["rxresume"] = RxResumeClient(settings)
    application.bot_data["adapter"] = ResumeAdapter(settings)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("portfolio", portfolio))
    application.add_handler(CommandHandler("vacancy", vacancy_cmd))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return application


def main() -> None:
    settings = get_settings()
    application = build_application(settings)
    logger.info("Bot started. Waiting for updates…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
