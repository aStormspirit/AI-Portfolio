# Portfolio → Reactive Resume Telegram Bot

Телеграм-бот: отправляете команду `/portfolio`, присылаете PDF-портфолио — бот
распознаёт его через AI-парсер [Reactive Resume](https://rxresu.me) и создаёт
готовое резюме в вашем аккаунте rxresu.me.

## Как это работает

1. Пользователь вызывает `/portfolio` и присылает PDF-файл.
2. Бот скачивает файл и кодирует его в base64.
3. `POST /ai/parse-pdf` — rxresu.me распознаёт PDF в структуру резюме.
4. `POST /resumes/import` — из этих данных создаётся резюме в аккаунте.
5. Бот отвечает ссылкой на редактор резюме.

Документация API: <https://docs.rxresu.me/api-reference/ai/parse-a-pdf-file-into-resume-data>

## Команды бота

| Команда | Описание |
|---|---|
| `/start`, `/help` | Приветствие и инструкция |
| `/portfolio` | Начать: бот ждёт PDF-файл |
| `/cancel` | Отменить ожидание файла |

## Настройка

### 1. Токен бота

Создайте бота у [@BotFather](https://t.me/BotFather) и скопируйте токен.

### 2. API-ключ Reactive Resume

1. Войдите на <https://rxresu.me>.
2. Settings → **API Keys** → *Create a new API key*.
3. Скопируйте ключ сразу — он показывается один раз.
4. (Опционально) Settings → **AI** — подключите AI-провайдера, если хотите
   указать конкретный `RXRESUME_AI_PROVIDER_ID`. Без него используется провайдер
   по умолчанию.

### 3. Переменные окружения

```bash
cp .env.example .env
```

| Переменная | Описание | По умолчанию |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather | — (обязательно) |
| `RXRESUME_API_KEY` | Ключ API rxresu.me (`x-api-key`) | — (обязательно) |
| `RXRESUME_BASE_URL` | Базовый URL API | `https://rxresu.me/api/openapi` |
| `RXRESUME_AI_PROVIDER_ID` | ID AI-провайдера для парсинга | пусто (по умолчанию) |
| `MAX_PDF_SIZE_MB` | Лимит размера PDF | `15` |

> Для self-hosted инстанса укажите `RXRESUME_BASE_URL=https://<ваш-хост>/api/openapi`.

## Запуск

**Docker Compose (рекомендуется):**

```bash
cp .env.example .env   # заполнить TELEGRAM_BOT_TOKEN и RXRESUME_API_KEY
make up
make logs
```

**Локально без Docker:**

```bash
make install
make run
```

## Make-команды

| Команда | Описание |
|---|---|
| `make up` | Собрать и запустить бота через Docker Compose |
| `make down` | Остановить контейнеры |
| `make logs` | Логи бота |
| `make rebuild` | Пересобрать образ без кэша |
| `make run` | Запустить локально в venv |
| `make shell` | Shell внутри контейнера |

## Ограничения

- Telegram Bot API отдаёт файлы до ~20 МБ — крупнее PDF бот скачать не сможет.
- Качество распознавания зависит от AI-провайдера, настроенного в rxresu.me.
- Резюме создаётся в аккаунте, которому принадлежит `RXRESUME_API_KEY`.
