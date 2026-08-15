from __future__ import annotations

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
from app.services.rxresume import RxResumeClient, RxResumeError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

AWAITING_KEY = "awaiting_portfolio"

START_TEXT = (
    "👋 Привет! Я собираю резюме на Reactive Resume из вашего портфолио.\n\n"
    "1. Отправьте команду /portfolio\n"
    "2. Пришлите PDF-файл портфолио/резюме\n"
    "3. Я распознаю его и создам резюме в rxresu.me\n\n"
    "Отменить — /cancel."
)

PORTFOLIO_PROMPT = (
    "📄 Пришлите PDF-файл вашего портфолио одним сообщением.\n"
    "Я отправлю его в rxresu.me, распознаю содержимое и создам резюме."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AWAITING_KEY, None)
    await update.message.reply_text(START_TEXT)


async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[AWAITING_KEY] = True
    await update.message.reply_text(PORTFOLIO_PROMPT)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AWAITING_KEY, None)
    await update.message.reply_text("Ок, отменил. Наберите /portfolio, когда будете готовы.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    document = message.document

    if not context.user_data.get(AWAITING_KEY):
        await message.reply_text(
            "Сначала наберите /portfolio, затем пришлите PDF-файл."
        )
        return

    settings: Settings = context.bot_data["settings"]

    filename = document.file_name or "portfolio.pdf"
    is_pdf = (document.mime_type == "application/pdf") or filename.lower().endswith(".pdf")
    if not is_pdf:
        await message.reply_text("Нужен файл в формате PDF. Пришлите PDF ещё раз.")
        return

    if document.file_size and document.file_size > settings.max_pdf_size_bytes:
        await message.reply_text(
            f"Файл больше {settings.max_pdf_size_mb} МБ. Уменьшите размер PDF."
        )
        return

    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    status = await message.reply_text("⏳ Загружаю и распознаю портфолио… это займёт до минуты.")

    try:
        tg_file = await context.bot.get_file(document.file_id)
        pdf_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to download telegram file")
        await status.edit_text(f"Не удалось скачать файл из Telegram: {exc}")
        return

    client: RxResumeClient = context.bot_data["rxresume"]
    try:
        resume = await client.create_from_pdf(filename, pdf_bytes)
    except RxResumeError as exc:
        await status.edit_text(f"❌ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected error while creating resume")
        await status.edit_text(f"Непредвиденная ошибка: {exc}")
        return

    context.user_data.pop(AWAITING_KEY, None)
    await status.edit_text(
        "✅ Готово! Резюме создано в rxresu.me.\n\n"
        f"«{resume.title}»\n"
        f"🖊 Редактор: {resume.builder_url}\n"
        f"📁 Все резюме: {resume.dashboard_url}\n\n"
        "Отправьте /portfolio, чтобы обработать ещё одно.",
        disable_web_page_preview=True,
    )


async def handle_stray_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get(AWAITING_KEY):
        await update.message.reply_text("Жду PDF-файл. Пришлите документ (не текст).")
    else:
        await update.message.reply_text("Наберите /portfolio, чтобы начать.")


def build_application(settings: Settings) -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не задан. Получите токен у @BotFather и добавьте в .env."
        )

    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["rxresume"] = RxResumeClient(settings)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("portfolio", portfolio))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stray_text)
    )
    return application


def main() -> None:
    settings = get_settings()
    application = build_application(settings)
    logger.info("Bot started. Waiting for updates…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
