# Evalyn — Архитектура

## Обзор

Evalyn — AI-ассистент для проверки студенческих работ (в первую очередь IT-дисциплины). Преподаватель настраивает агентов, просматривает их выводы и принимает/отклоняет каждый пункт перед отправкой фидбека студентам. Ключевой принцип — **human-in-the-loop**: окончательное решение всегда за преподавателем.

**MVP:** Telegram-бот (polling) + Telegram Mini App для учительского интерфейса.

**Стек:** Python 3.12 · aiogram 3.x · FastAPI · OpenRouter API (openai-compatible) · PostgreSQL (asyncpg + SQLAlchemy async) · Alembic · React 18 + TypeScript + Vite · Docker

---

## Структура проекта

```
evalyn/
├── bot/
│   ├── handlers/
│   │   ├── admin.py        # /admin, /admin_add_teacher, /admin_remove_teacher, /admin_list_teachers
│   │   ├── teacher/
│   │   │   ├── courses.py      # создать курс, список, студенты, код приглашения
│   │   │   └── assignments.py  # список заданий, создать задание (FSM), просмотр
│   │   ├── student/
│   │   │   ├── courses.py      # вступить по коду, список курсов
│   │   │   └── assignments.py  # просмотр задания, сдача работы (FSM)
│   │   └── common/
│   │       ├── start.py    # /start, регистрация (FSM)
│   │       ├── help.py     # /help (роль-зависимый)
│   │       └── profile.py  # /profile — карточка + смена имени (FSM)
│   ├── middlewares/        # AuthMiddleware: db_user + uow_factory в handler data
│   ├── keyboards/          # фабрики inline/reply клавиатур + WebApp-кнопки
│   └── states/
│       ├── registration.py # RegistrationStates, ProfileStates
│       ├── course.py       # CourseCreateStates, JoinCourseStates
│       ├── assignment.py   # AssignmentCreateStates
│       └── submission.py   # SubmissionStates
├── api/                    # FastAPI — бэкенд для Mini App
│   ├── routers/
│   │   ├── courses.py
│   │   ├── assignments.py
│   │   ├── agents.py
│   │   ├── reviews.py
│   │   └── analytics.py
│   ├── deps.py             # валидация Telegram initData, зависимости
│   └── app.py              # FastAPI instance + StaticFiles (frontend/dist)
├── frontend/               # Telegram Mini App (React + Vite + TypeScript)
│   ├── src/
│   │   ├── pages/          # AgentBuilder, Submissions, ReviewDetail, Analytics
│   │   └── components/
│   ├── dist/               # собранные статические файлы (git-ignored)
│   └── package.json
├── agents/
│   ├── base.py             # BaseAgent: system_prompt + run()
│   ├── templates/          # CodeReviewer, StyleChecker, LogicChecker
│   ├── runner.py           # параллельный / последовательный запуск агентов
│   ├── llm_client.py       # OpenRouter клиент (openai-compatible)
│   ├── prompt_builder.py   # сборка контекста с XML-изоляцией + RAG-фрагменты
│   ├── output_schema.py    # Pydantic-модель структурированного вывода
│   └── rag/
│       ├── embedder.py     # генерация эмбеддингов через OpenRouter
│       ├── retriever.py    # поиск по pgvector (база знаний + история ошибок)
│       ├── indexer.py      # индексация: документы, сабмиты, ReviewItem
│       └── plagiarism.py   # косинусное сходство между сабмитами одного задания
├── services/
│   ├── course_service.py
│   ├── submission_service.py
│   ├── grading_service.py  # принять / отклонить / изменить пункты
│   └── analytics_service.py
├── db/
│   ├── models/             # SQLAlchemy ORM модели
│   ├── repositories/       # слой доступа к данным
│   └── migrations/         # Alembic
├── core/
│   ├── config.py           # pydantic-settings (.env)
│   ├── models_registry.py  # список доступных OpenRouter моделей
│   └── security.py         # anti-injection + валидация Telegram initData
└── main.py                 # точка входа: asyncio — polling + uvicorn параллельно
```

---

## Авторизация и роли

**Принципы:**
- Авторизация — через Telegram identity (`telegram_id`). Пароли не нужны.
- Глобальной роли нет. Роль определяется контекстом курса: создал курс → `owner` в нём, вступил по коду → `student` в нём. Один человек может одновременно вести свои курсы и учиться в чужих.
- Создавать курсы могут только пользователи из **whitelist** (управляется администратором бота).

**Регистрация:**
При первом `/start` бот запрашивает отображаемое имя (ФИО или как хочет пользователь). Telegram-имя подставляется как подсказка, но пользователь вводит своё — именно это имя видит преподаватель в списке работ. Сменить имя можно в любой момент через `/profile`.

**Whitelist:**
Администратор (владелец бота, `ADMIN_IDS` в `.env`) добавляет преподавателей командой `/admin add_teacher @username` или по `telegram_id`. При попытке создать курс бот проверяет наличие в whitelist — если нет, отказывает с пояснением.

**Администраторы** (`ADMIN_IDS` в `.env`) неявно считаются в whitelist — получают все права преподавателя без ручного добавления.

**Навигация — динамическое главное меню:**
```
[Если в whitelist или admin]  → ➕ Создать курс
                              → 🎓 Открыть панель (Mini App)
[Если есть owner-курсы]      → 🎓 Мои курсы (преподаватель)
[Если есть student-курсы]    → 📚 Мои курсы (студент)
                              → 🔑 Вступить в курс по коду  (всегда)
                              → 👤 Мой профиль              (всегда)
```

**Slash-команды (дублируют кнопки меню):**
```
/new_course      — создать курс          /my_courses      — мои курсы (преп.)
/join_course     — вступить по коду      /student_courses — мои курсы (студент)
```

---

## Доменные модели

| Сущность | Ключевые поля |
|----------|---------------|
| `User` | telegram_id, name, username\|null, created_at |
| `TeacherWhitelist` | id, telegram_id\|null, username\|null, added_by, notes |
| `Course` | id, creator_id, name, invite_code (8 hex, unique), created_at |
| `CourseRole` | (user_id, course_id) PK, role (owner\|student), joined_at |
| `Assignment` | id, course_id, title, description, criteria\|null, deadline\|null, created_at |
| `Submission` | id, (assignment_id, student_id) unique, content_text\|null, file_id\|null, status (pending\|reviewed), submitted_at |
| `Agent` | id, owner_id, course_id, name, template_type\|null, system_prompt, model, temperature |
| `Review` | id, submission_id, agent_id, raw_output, status (pending\|running\|done\|failed) |
| `ReviewItem` | id, review_id, category, severity, title, description, location, suggestion, teacher_decision (accepted\|rejected\|edited), edited_text |
| `ChatMessage` | id, review_id, role (user\|assistant), content |
| `FinalFeedback` | id, submission_id, content, sent_at |
| `KnowledgeDoc` | id, course_id, title, content_text, file_id\|null, embedding vector(1536) |
| `SubmissionEmbedding` | submission_id, embedding vector(1536) |

`Enrollment` удалена — заменена `CourseRole` с полем `role`.

**Совладельцы курса:** у одного курса может быть несколько `owner` — преподаватель, ассистент, со-автор. `Course.creator_id` хранит только того, кто создал курс (для аудита). Все права доступа определяются через `CourseRole`. Добавить нового owner может любой существующий owner курса.

---

## Флоу преподавателя

Сложные операции (конструктор агентов, детальный просмотр работ, аналитика) — в Mini App.
Уведомления и быстрые действия — в боте.

```
/start → «Введите ваше имя (его увидят студенты/преподаватели):»
       → [пользователь вводит имя] → зарегистрирован → Главное меню
/profile → карточка профиля (имя, роль, список курсов) + кнопка смены имени

Главное меню (динамическое):
  ➕ Создать курс / /new_course   (только если в whitelist или admin)
  🎓 Открыть панель               (только если в whitelist или admin) → Mini App
  🎓 Мои курсы (преп.) /my_courses (если есть owner-курсы)
    → inline-список курсов → [📋 Задания] [👥 Студенты] [🔑 Код]
    → 📋 Задания: список + [➕ Создать задание]
       Создать задание (FSM): название → описание → критерии → дедлайн
    → 👥 Студенты: пронумерованный список с именами и @username
  📚 Мои курсы (студент) /student_courses (если есть student-курсы)
  🔑 Вступить в курс по коду /join_course
```

**В Mini App (не реализован):**
```
Главная → Курсы → Курс
  🗂 Задания
    → Создать задание (название, условие, критерии, дедлайн)
    → Открыть задание
        → Список сданных работ
        → Открыть работу
            → Просмотр с подсветкой кода
            → Запустить анализ (выбрать агентов, режим)
            → Просмотр пунктов → ✅ Принять / ❌ Отклонить / ✏️ Изменить
            → Отправить фидбек студенту
  🤖 Агенты
    → Конструктор: шаблон + системный промпт + модель + правила
  📊 Аналитика
    → Топ ошибок, распределение оценок, прогресс студентов
```

## Флоу студента

Полностью через бот — Mini App не нужен.

```
/start → «Введите ваше имя (его увидит преподаватель):»
       → [студент вводит ФИО] → зарегистрирован
/profile → карточка + кнопка смены имени

  🔑 Вступить в курс / /join_course → ввести invite-код → CourseRole(student) создаётся
  📚 Мои курсы / /student_courses
    → inline-список курсов
    → Открыть курс → список заданий с иконками:
        📄 не сдано  ⏳ на проверке  ✅ проверено
    → Открыть задание → карточка:
        название, дедлайн, описание, критерии (если заданы)
        статус + превью текущей работы (если сдана)
        [📤 Сдать работу] / [🔄 Обновить работу]
        [← Назад к заданиям]
    → Сдача: текст / document / photo
        повторная сдача перезаписывает предыдущую (status → pending)
    → [Посмотреть фидбек] — когда преподаватель отправил (не реализовано)
```

---

## Система агентов

### Структурированный вывод

```python
# agents/output_schema.py
class ReviewItemOutput(BaseModel):
    category: str                        # code_style, logic, tests, docs...
    severity: Literal["error", "warning", "suggestion"]
    title: str
    description: str
    location: str | None                 # "строка 42", "функция foo()"
    suggestion: str | None

class AgentOutput(BaseModel):
    overall_score: float                 # 0–10
    summary: str
    items: list[ReviewItemOutput]
    strengths: list[str]
```

### OpenRouter — единый шлюз для моделей

```python
# agents/llm_client.py
from openai import AsyncOpenAI
from core.config import settings

_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
)

async def chat(model: str, messages: list, **kwargs) -> str:
    resp = await _client.chat.completions.create(
        model=model, messages=messages, **kwargs
    )
    return resp.choices[0].message.content
```

**Доступные модели** (хранятся в `core/models_registry.py`, отображаются в Mini App при создании агента):

| ID (OpenRouter) | Отображаемое имя | Тип |
|-----------------|-----------------|-----|
| `anthropic/claude-sonnet-4-5` | Claude Sonnet — мощный | powerful |
| `anthropic/claude-haiku-4-5` | Claude Haiku — быстрый | fast |
| `openai/gpt-4o` | GPT-4o | powerful |
| `openai/gpt-4o-mini` | GPT-4o Mini | fast |
| `google/gemini-2.0-flash` | Gemini Flash | fast |
| `meta-llama/llama-3.3-70b-instruct` | Llama 3.3 70B | free |

### Промпт-изоляция (защита от injection)

Студенческий контент всегда обёрнут в XML-теги — модель не воспринимает его как инструкции:

```python
# agents/prompt_builder.py
def build_context(assignment, submission) -> str:
    return f"""
<assignment>
{sanitize(assignment.description)}
</assignment>

<criteria>
{sanitize(assignment.criteria)}
</criteria>

<student_submission>
{sanitize(submission.content_text)}
</student_submission>

Проанализируй работу студента по критериям задания. Верни JSON по схеме.
"""
```

### Мульти-агентный запуск

**Параллельно** — агенты анализируют одну работу независимо, результаты показываются рядом. Быстро, выводы не зависят друг от друга.

**Последовательно (pipeline)** — Агент 1 анализирует → результат добавляется в контекст Агента 2 → ... Полезно, когда следующий агент должен опираться на выводы предыдущего.

Преподаватель выбирает режим при запуске анализа в Mini App.

### Встроенные шаблоны агентов

| Шаблон | Специализация | Рекомендуемая модель |
|--------|--------------|---------------------|
| CodeReviewer | Логика, структура, edge cases | claude-sonnet / gpt-4o |
| StyleChecker | Именование, форматирование, docstrings | claude-haiku / gpt-4o-mini |
| LogicChecker | Алгоритмическая корректность, сложность | claude-sonnet / gpt-4o |
| Custom | Преподаватель пишет системный промпт вручную | выбор учителя |

---

## RAG-модуль

RAG решает три задачи, которые не покрываются чистым LLM-вызовом.

### 1. База знаний курса

Преподаватель загружает в курс учебные материалы: стандарты кода, методички, примеры хороших/плохих работ. При проверке `retriever.py` ищет топ-K релевантных фрагментов и добавляет их в контекст агента:

```python
# agents/prompt_builder.py (фрагмент)
async def build_context(assignment, submission, retriever) -> str:
    docs = await retriever.search(
        query=submission.content_text,
        course_id=assignment.course_id,
        top_k=4,
    )
    knowledge_block = "\n".join(f"- {d.title}: {d.excerpt}" for d in docs)

    return f"""
<assignment>{sanitize(assignment.description)}</assignment>
<criteria>{sanitize(assignment.criteria)}</criteria>
<course_knowledge>
{knowledge_block}
</course_knowledge>
<student_submission>{sanitize(submission.content_text)}</student_submission>
"""
```

Фидбек становится привязан к конкретному курсу: агент цитирует методичку, а не даёт общие советы.

### 2. Антиплагиат

При каждой новой сдаче `indexer.py` сохраняет эмбеддинг сабмита в `SubmissionEmbedding`. `plagiarism.py` делает nearest-neighbor поиск по всем сдачам того же задания:

```python
# agents/rag/plagiarism.py
async def check(submission_id, assignment_id, threshold=0.85) -> list[PlagiarismHit]:
    embedding = await get_embedding(submission_id)
    hits = await db.execute("""
        SELECT s.id, s.student_id,
               1 - (se.embedding <=> :emb) AS similarity
        FROM submission_embeddings se
        JOIN submissions s ON s.id = se.submission_id
        WHERE s.assignment_id = :aid
          AND s.id != :sid
          AND 1 - (se.embedding <=> :emb) > :threshold
        ORDER BY similarity DESC
    """, emb=embedding, aid=assignment_id, sid=submission_id, threshold=threshold)
    return hits
```

Если есть совпадения — в Review добавляется пункт с флагом `plagiarism_suspected`, преподаватель видит предупреждение и процент сходства.

### 3. Детектор системных пробелов

После завершения проверки задания (все или большинство работ проверены) `analytics_service.py` кластеризует принятые `ReviewItem` по `category`. Если одна категория встречается у ≥ 40% студентов — бот отправляет преподавателю инсайт:

> ⚠️ **Задание №3:** 8 из 12 студентов допустили ошибки по теме `exception_handling`. Возможно, стоит разобрать этот момент на следующем занятии.

Порог и минимальное число студентов — настраиваемые параметры курса.

### Векторная БД

Используем **pgvector** — расширение для PostgreSQL. Никакого отдельного сервиса: одна БД для реляционных данных и векторов.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
-- в таблицах KnowledgeDoc и SubmissionEmbedding:
embedding vector(1536)
-- индекс для быстрого поиска:
CREATE INDEX ON submission_embeddings USING ivfflat (embedding vector_cosine_ops);
```

Эмбеддинги генерируются через OpenRouter (`text-embedding-3-small` от OpenAI или аналог).

### Порядок реализации RAG

RAG добавляется **после базового MVP** (после шага 9). Порядок:
1. Подключить pgvector, добавить модели `KnowledgeDoc` и `SubmissionEmbedding`
2. `embedder.py` — генерация эмбеддингов
3. `indexer.py` — индексация сабмитов при сдаче работы
4. `plagiarism.py` — проверка при новом сабмите
5. `retriever.py` — поиск по базе знаний
6. UI в Mini App: загрузка документов в курс
7. `analytics_service.py` — детектор системных пробелов

---

## Telegram Mini App

**Авторизация** — через Telegram `initData` (подпись проверяется на бэкенде):

```python
# core/security.py
import hmac, hashlib, urllib.parse

def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    parsed = dict(urllib.parse.parse_qsl(init_data))
    received_hash = parsed.pop("hash", "")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise ValueError("Invalid initData")
    return parsed
```

FastAPI dependency в `api/deps.py` читает `X-Telegram-Init-Data` заголовок и возвращает текущего пользователя.

**Стек фронтенда:** React 18 + TypeScript + Vite + `@twa-dev/sdk` + TailwindCSS

---

## Инфраструктура (Docker)

```
Dockerfile                   # multi-stage: frontend build → python runtime
docker-compose.yml           # db + migrate + app
docker-compose.override.yml  # локальная разработка (volume mounts, авто-перезагрузка)
.env.example                 # шаблон переменных окружения
```

### Сервисы

| Сервис | Image | Назначение |
|--------|-------|-----------|
| `db` | postgres:16-alpine | PostgreSQL |
| `migrate` | ./Dockerfile | one-shot: `alembic upgrade head` |
| `app` | ./Dockerfile | bot (polling) + FastAPI (uvicorn) в одном процессе |

**`main.py` — два asyncio-таска:**
```python
async def main():
    await asyncio.gather(
        start_bot(),   # aiogram polling
        start_api(),   # uvicorn FastAPI + StaticFiles(frontend/dist)
    )
```

**Dockerfile (multi-stage):**
```dockerfile
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json .
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim AS py-builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=py-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=frontend-builder /frontend/dist ./frontend/dist
COPY . .
CMD ["python", "-m", "main"]
```

### Ключевые переменные окружения

```
BOT_TOKEN=
OPENROUTER_API_KEY=
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/evalyn
WEBAPP_URL=https://yourdomain.com      # HTTPS обязателен для Telegram Mini App
```

Файлы локально не хранятся — сохраняется только Telegram `file_id`, контент скачивается по запросу.
Деплой — `docker compose up -d` на VPS с HTTPS (nginx + Let's Encrypt) или Railway/Render.

---

## Порядок реализации (MVP)

1. ✅ Скаффолдинг: структура, `requirements.txt`, Docker, `core/config.py`
2. ✅ DB: SQLAlchemy модели + Alembic (миграции 0001–0003)
3. ✅ Bot: `/start`, `/profile` (карточка + смена имени), `/help` (роль-зависимый), `/admin_*` для whitelist
4. ✅ Bot: курсы — создание, вступление по коду, список, просмотр студентов
5. ✅ Bot: задания — создание (FSM: название / описание / критерии / дедлайн), список, просмотр
6. ✅ Bot (student): сдача работы — текст / файл, повторная сдача, статусы
7. Agent: `llm_client.py` (OpenRouter) + CodeReviewer шаблон + запуск анализа
8. Bot (teacher): human-in-the-loop — просмотр пунктов, accept/reject/edit
9. Bot (teacher): отправка финального фидбека студенту
10. API: FastAPI app + `deps.py` + роутеры (courses, assignments, agents, reviews)
11. Frontend: React Mini App scaffold + Vite + `@twa-dev/sdk` + базовые страницы
12. Frontend: конструктор агентов (шаблон + промпт + модель из OpenRouter)
13. Frontend: просмотр работ + human-in-the-loop
14. Frontend: аналитика
15. Bot: чат с агентом о конкретной работе
16. Bot/Agent: параллельный / последовательный мульти-агентный режим

---

## Стратегия тестирования

- `pytest` + `pytest-asyncio` для сервисного слоя (тестовая БД SQLite in-memory)
- Интеграционный путь: создать курс → записать студента → сдать работу → запустить агента → проверить `ReviewItem` в БД
- Ручное тестирование через Telegram (локальный polling с тестовым токеном бота)
- Проверка anti-injection: отправить `Ignore previous instructions` в теле работы — убедиться, что граница промпта не нарушается
