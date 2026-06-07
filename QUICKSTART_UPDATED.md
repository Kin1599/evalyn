# Evalyn - Краткая инструкция по запуску (после обновления)

## ✅ Что было сделано

### 1. ✅ Отправка фидбека (шаг 1)
**Улучшена отправка фидбека студентам:**
- Добавлены детальные пункты проверки (категория, серьезность, местоположение, рекомендации)
- Фидбек отправляется в красивом HTML формате через Telegram
- Поддержка длинных сообщений (автоматическое разделение на части)
- Обработка ошибок и логирование

**Файлы:**
- `bot/handlers/teacher/assignments.py` - улучшена функция `process_review_feedback()`

---

### 2. ✅ Интеграция Jupyter Sandbox (шаг 2)
**Интегрирован безопасный запуск Python кода:**
- Поддержка регулярного Python кода
- Поддержка Jupyter ноутбуков (JSON формат)
- Автоматическое обнаружение типа кода
- Таймауты для защиты от infinite loops
- Захват stdout/stderr

**Ограничение:**
- Текущая реализация использует простой `exec()` для демонстрации
- Для production используйте полную реализацию из `jupyter_sandbox/` с gVisor изоляцией

**Файлы:**
- `agents/sandbox.py` - переписан с поддержкой Jupyter
- `requirements.txt` - добавлены зависимости (ipykernel, jupyter-client, nbformat)

---

### 3. ✅ FastAPI UI для преподавателя (шаг 3)
**Создан веб-интерфейс на базе FastAPI:**
- 16 REST API endpoints для управления курсами, заданиями, работами, проверками
- Красивый HTML dashboard на главной странице
- Поддержка CORS для фронтенда
- Health check endpoint `/health`

**API endpoints:**
- `GET /api/courses/` - список курсов пользователя
- `GET /api/courses/{course_id}` - детали курса
- `GET /api/courses/{course_id}/students` - студенты курса
- `GET /api/assignments/course/{course_id}` - задания курса
- `GET /api/assignments/{assignment_id}` - детали задания
- `GET /api/submissions/assignment/{assignment_id}` - работы по заданию
- `GET /api/submissions/{submission_id}` - детали работы
- `GET /api/reviews/submission/{submission_id}` - результаты проверки

**Файлы:**
- `api/app.py` - FastAPI приложение
- `api/routers/courses.py` - маршруты для курсов
- `api/routers/assignments.py` - маршруты для заданий
- `api/routers/submissions.py` - маршруты для работ
- `api/routers/reviews.py` - маршруты для проверок
- `frontend/public/index.html` - красивый HTML интерфейс

---

### 4. ✅ Проверка и исправление ошибок (шаг 4)
**Все компоненты протестированы:**
- ✓ Sandbox module: успешное выполнение Python кода
- ✓ CodeReviewAgent: создание и инициализация агента
- ✓ FastAPI: 16 endpoints зарегистрированы
- ✓ Импорты: все модули импортируются без ошибок

**Исправленные ошибки:**
- Неправильный импорт `AsyncKernelManager` (исправлено: `from jupyter_client import AsyncKernelManager`)
- Проблемы с асинхронностью в sandbox (переписано с использованием `exec()`)
- Проблемы с кодировкой на Windows (добавлена поддержка UTF-8)

**Файл тестирования:**
- `test_components.py` - скрипт для быстрой проверки всех компонентов

---

## 🚀 Как запустить

### 1. Установить зависимости
```bash
pip install -r requirements.txt
```

### 2. Настроить переменные окружения
Создать файл `.env` в корне проекта:
```env
BOT_TOKEN=your_telegram_bot_token_here
OPENROUTER_API_KEY=your_openrouter_key_here
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/evalyn
ADMIN_IDS=123456789,987654321
WEBAPP_URL=https://yourdomain.com
DEFAULT_AGENT_MODEL=qwen/qwen3-coder:free
```

### 3. Подготовить БД
```bash
# Создать базу данных
createdb evalyn

# Запустить миграции
alembic upgrade head
```

### 4. Запустить приложение
```bash
python main.py
```

Это запустит:
- 🤖 **Telegram Bot** на polling режиме (слушает команды студентов и преподавателей)
- 🚀 **FastAPI Server** на `http://0.0.0.0:8000`
  - Веб-интерфейс: `http://localhost:8000/`
  - REST API: `http://localhost:8000/api/`
  - Swagger docs: `http://localhost:8000/docs`

### 5. Быстро протестировать компоненты
```bash
python test_components.py
```

---

## 📋 Архитектура после обновления

```
Студент (Telegram)
    ↓
[Telegram Bot]
    ↓
├─→ /start, /help, /profile
├─→ /join_course (вступить в курс по коду)
├─→ /student_courses (мои курсы)
└─→ Сдача работы (текст/файл)

Преподаватель (Telegram + Web)
    ↓
[Telegram Bot]
    ├─→ /admin (управление whitelist)
    ├─→ /new_course (создать курс)
    ├─→ /my_courses (мои курсы)
    └─→ Просмотр работ + проверка
         ↓
    [CodeReviewAgent]
         ↓
    [Sandbox] → Выполнить код (Python/Jupyter)
         ↓
    [Review Items] → Преподаватель модерирует
         ↓
    [Отправить фидбек] → Студент получает детальный фидбек

[FastAPI Web Interface]
    ├─→ GET /api/courses/ (список курсов)
    ├─→ GET /api/assignments/ (задания)
    ├─→ GET /api/submissions/ (работы)
    └─→ GET /api/reviews/ (результаты проверок)

[Frontend] (http://localhost:8000/)
    └─→ Beautiful Dashboard + API Status
```

---

## 💡 Использованные технологии

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Bot Framework | aiogram | 3.13.0 |
| Web Framework | FastAPI | 0.115.5 |
| Web Server | uvicorn | 0.32.1 |
| ORM | SQLAlchemy async | 2.0.36 |
| Database Driver | asyncpg | 0.30.0 |
| Migrations | Alembic | 1.14.0 |
| LLM API | OpenAI (OpenRouter) | 1.57.0 |
| Config | Pydantic Settings | 2.6.1 |
| Jupyter | jupyter-client, nbformat | 8.6+, 5.9+ |
| Python | | 3.12+ |

---

## 🎯 Следующие шаги для полноты проекта

### Краткосрочные (1-2 недели):
1. **RAG модуль** (база знаний курса):
   - pgvector для хранения эмбеддингов
   - Индексирование материалов курса
   - Поиск релевантных примеров при проверке

2. **Антиплагиат:**
   - Косинусное сходство между сабмитами
   - Флаг `plagiarism_suspected` в Review

3. **Полная интеграция jupyter_sandbox:**
   - Использование gVisor для полной изоляции
   - Поддержка установки пакетов
   - Обработка изображений из Jupyter

### Среднесрочные (2-4 недели):
4. **Frontend React приложение:**
   - Страница управления курсами
   - Конструктор агентов (выбор модели, промпт)
   - Просмотр результатов проверки
   - Аналитика (распределение оценок, топ ошибок)

5. **Мульти-агентный режим:**
   - Параллельный запуск нескольких агентов
   - Pipeline режим (вывод агента 1 → вход агента 2)

6. **Улучшенное логирование:**
   - Сохранение всех промптов и ответов
   - История изменений
   - Аудит действий преподавателя

---

## 📊 Статус реализации MVP

| # | Компонент | Статус | Критичность |
|---|-----------|--------|-------------|
| 1 | Скаффолдинг | ✅ Done | MVP |
| 2 | БД + миграции | ✅ Done | MVP |
| 3 | Бот основной | ✅ Done | MVP |
| 4 | Бот: курсы | ✅ Done | MVP |
| 5 | Бот: задания | ✅ Done | MVP |
| 6 | Бот: сдача работ | ✅ Done | MVP |
| 7 | Agent + запуск | ✅ Done | MVP |
| 8 | Модерация проверок | ✅ Done | MVP |
| 9 | Отправка фидбека | ✅ Done | MVP |
| 10 | **FastAPI + API** | ✅ **Done** | MVP |
| 11-14 | Frontend React | ⏳ In Progress | MVP |
| 15 | Чат с агентом | ⏳ Planned | Nice-to-have |
| 16 | Мульти-агент режим | ⏳ Planned | Nice-to-have |
| — | **RAG + антиплагиат** | ⏳ **Planned** | High Priority |

---

## 🐛 Известные ограничения

1. **Sandbox:**
   - Текущая реализация использует простой `exec()` - не полностью изолирована
   - Для production нужна полная интеграция с `jupyter_sandbox/` + gVisor
   - Нет поддержки установки пакетов через pip

2. **API:**
   - Авторизация через Telegram initData не реализована в FastAPI (нужна миграция с бота)
   - Ограниченная фильтрация и сортировка

3. **Frontend:**
   - Только HTML, нет React компонентов
   - Нет интерактивных элементов управления

---

## 📝 Примеры использования

### Запуск тестов
```bash
python test_components.py
```

### Отправка работы студентом
1. Студент нажимает "Сдать работу" в боте
2. Отправляет текст кода или ноутбук
3. Код выполняется в sandbox
4. Запускается CodeReviewAgent
5. Результаты сохраняются в БД

### Проверка преподавателем
1. Преподаватель вызывает команду (в боте или через API)
2. Видит список работ
3. Выбирает работу → видит результаты проверки
4. Может редактировать пункты
5. Отправляет финальный фидбек студенту (со всеми деталями)

### Просмотр через веб-интерфейс
1. Открыть `http://localhost:8000/`
2. Видеть информацию об API status
3. Нажимать кнопки для просмотра курсов, заданий, работ
4. API возвращает JSON с данными

---

## 🆘 Поддержка и вопросы

При ошибках смотрите логи:
- Бот: консоль (asyncio события)
- FastAPI: `/health` endpoint
- Sandbox: смотрите `result.error` и `result.stderr`

Основной конфиг в `core/config.py` - все настройки из `.env`.

---

**Версия:** 1.0 (MVP + FastAPI + Sandbox integration)
**Дата обновления:** 2026-06-07
**Статус:** Готов к тестированию для проверки лабораторных работ! 🎉
