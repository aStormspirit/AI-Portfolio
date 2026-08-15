# AI Resume Editor

MVP-сервис: загружаете PDF-резюме и текст вакансии — LangChain адаптирует содержание под вакансию и отдаёт новый PDF.

## Стек

- FastAPI + Jinja2 + HTMX
- LangChain + OpenAI (structured output)
- PyMuPDF (извлечение текста)
- WeasyPrint (HTML → PDF)

## Быстрый старт

### 1. Системные зависимости (WeasyPrint)

**Ubuntu / Debian:**

```bash
sudo apt-get update
sudo apt-get install -y \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libgdk-pixbuf-2.0-0 \
  libffi-dev \
  shared-mime-info \
  fonts-dejavu-core
```

**Fedora:**

```bash
sudo dnf install pango gdk-pixbuf2 libffi-devel
```

### 2. Python-окружение

```bash
cd AI-Portfolio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Конфигурация

```bash
cp .env.example .env
```

Заполните `.env`:

| Переменная | Описание | По умолчанию |
|---|---|---|
| `OPENAI_API_KEY` | API-ключ OpenAI или OpenRouter | — (обязательно) |
| `OPENAI_BASE_URL` | Базовый URL API (для OpenRouter: `https://openrouter.ai/api/v1`) | авто для `sk-or-…` |
| `LLM_MODEL` | Модель | `gpt-4o-mini` (для OpenRouter: `openai/gpt-4o-mini`) |
| `MAX_PDF_SIZE_MB` | Лимит размера PDF | `5` |

### 4. Запуск

**Docker Compose (рекомендуется):**

```bash
cp .env.example .env   # указать OPENAI_API_KEY
make up
```

Откройте http://127.0.0.1:8000

**Локально без Docker:**

```bash
make install
make run
```

## Make-команды

| Команда | Описание |
|---|---|
| `make up` | Собрать и запустить через Docker Compose |
| `make down` | Остановить контейнеры |
| `make logs` | Логи приложения |
| `make rebuild` | Пересобрать образ без кэша |
| `make shell` | Shell внутри контейнера |
| `make install` | Локальный venv + зависимости |
| `make run` | Локальный uvicorn |
| `make clean` | Остановить и очистить `uploads/` / `outputs/` |

## Docker

```bash
docker compose up --build -d
# или
make up
```

Остановка: `make down` / `docker compose down`

## Как это работает

1. Из PDF извлекается текст (PyMuPDF).
2. LLM приводит резюме к структурированной схеме.
3. LLM анализирует вакансию (навыки, ключевые слова, приоритеты).
4. LLM переписывает резюме под вакансию **без выдумывания фактов**.
5. HTML-шаблон рендерится в PDF (WeasyPrint).

Исходная вёрстка PDF не клонируется — на выходе единый профессиональный шаблон.

## API

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/` | Форма загрузки |
| `POST` | `/adapt` | Адаптация (HTMX multipart) |
| `GET` | `/download/{job_id}` | Скачать сгенерированный PDF |
| `GET` | `/health` | Healthcheck |

Сгенерированные файлы хранятся локально в `outputs/` около 1 часа.
