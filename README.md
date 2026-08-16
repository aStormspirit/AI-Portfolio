# Resume → Vacancy → Reactive Resume Telegram Bot

Телеграм-бот: отправляете `/portfolio`, присылаете резюме (ссылку из
[Reactive Resume](https://rxresu.me) или PDF), затем текст вакансии — бот
адаптирует резюме под вакансию через LLM и загружает **новое** резюме в ваш
аккаунт rxresu.me.

## Как это работает

1. Пользователь вызывает `/portfolio`.
2. Присылает резюме:
   - **ссылку из rxresu.me** (`https://rxresu.me/username/slug` или ссылку из
     редактора) → бот читает данные через `GET /resumes/{username}/{slug}` или
     `GET /resumes/{id}`;
   - **или PDF-файл** → бот распознаёт его через `POST /ai/parse-pdf`.
3. Присылает текст вакансии.
4. LLM переписывает раздел «О себе», буллеты опыта и порядок навыков под
   вакансию (без выдумывания фактов).
5. `POST /resumes/import` — адаптированное резюме создаётся новым в аккаунте.
6. Бот отвечает ссылкой на редактор резюме и списком изменений.

Документация API: <https://docs.rxresu.me/api-reference/ai/parse-a-pdf-file-into-resume-data>

## Команды бота

| Команда | Описание |
|---|---|
| `/start`, `/help` | Приветствие и инструкция |
| `/portfolio` | Адаптация резюме: бот ждёт ссылку на резюме или PDF, затем вакансию |
| `/message` | Сгенерировать сопроводительное письмо по тексту вакансии |
| `/cancel` | Сбросить текущий диалог |

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
| `OPENAI_API_KEY` | Ключ OpenAI/OpenRouter для адаптации | — (обязательно) |
| `RXRESUME_BASE_URL` | Базовый URL API | `https://rxresu.me/api/openapi` |
| `RXRESUME_AI_PROVIDER_ID` | ID AI-провайдера для парсинга PDF | пусто (по умолчанию) |
| `OPENAI_BASE_URL` | Базовый URL LLM (для OpenRouter) | авто для `sk-or-…` |
| `LLM_MODEL` | Модель LLM | `gpt-4o-mini` |
| `COVER_LETTER_TEMPERATURE` | Temperature для `/message` | `0.55` |
| `COVER_LETTER_MAX_TOKENS` | Max tokens для `/message` | `900` |
| `COVER_LETTER_GOLDEN_LIMIT` | Сколько golden-примеров в few-shot | `3` |
| `MAX_PDF_SIZE_MB` | Лимит размера PDF | `15` |

> Для self-hosted инстанса укажите `RXRESUME_BASE_URL=https://<ваш-хост>/api/openapi`.

## Запуск

**Docker Compose (рекомендуется):**

```bash
cp .env.example .env   # заполнить TELEGRAM_BOT_TOKEN, RXRESUME_API_KEY, OPENAI_API_KEY
make up
make logs
```

**Локально без Docker:**

```bash
make install
make run
```

## Локальный тест `/message`

Письмо строится только по тексту вакансии (личные факты — через плейсхолдеры
в квадратных скобках).

```bash
make install
make test            # юнит-тесты без LLM
make test-message    # живой вызов LLM на tests/fixtures/sample_vacancy.txt
make test-golden     # проверка golden-писем (стиль), опционально --generate
```

### Golden set

Эталонные **письма** (без вакансий) лежат в [`tests/fixtures/golden/`](tests/fixtures/golden/)
как `*.txt`. Первая строка может быть заголовком: `# Название примера`.

Они подмешиваются в промпт `/message` как few-shot (только текст писем).

Добавить пример:

```bash
# tests/fixtures/golden/04-my-example.txt
# заголовок с # в первой строке, далее текст письма
make test
```

Параметры прогона:

```bash
.venv/bin/python -m scripts.test_message \
  --vacancy path/to/vacancy.txt \
  --temperature 0.4 \
  --out letter.txt
```

Подкручивайте `COVER_LETTER_TEMPERATURE`, `COVER_LETTER_MAX_TOKENS` и промпт в
[`app/services/adapt.py`](app/services/adapt.py) (`COVER_LETTER_SYSTEM`), затем снова
`make test-message`.

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
- Качество распознавания PDF зависит от AI-провайдера, настроенного в rxresu.me.
- Ссылка на резюме должна быть публичной либо принадлежать аккаунту `RXRESUME_API_KEY`.
- Адаптация переписывает только текст (о себе, буллеты опыта, порядок навыков) и
  не выдумывает компании, даты и метрики. Новое резюме создаётся в аккаунте
  `RXRESUME_API_KEY`.
