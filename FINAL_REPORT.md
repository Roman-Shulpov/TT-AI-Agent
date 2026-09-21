# Итоговый отчёт по заданию

## 1. Реализовано

Рабочий устанавливаемый Python-проект, видимый Chromium, CLI для произвольной задачи,
OpenAI Responses native tools, строгая валидация, универсальные browser primitives, runtime IDs,
ограниченная память, цитаты с источниками, Actor + final Verifier, recovery/backoff, loop detection,
MAX_STEPS, ask_user/finish, confirmations, persistent session, privacy-conscious logging и tests.
Core не содержит workflows или селекторов demo-сайтов.

Простой путь данных: модель **предлагает** JSON → Python проверяет → Playwright выполняет →
новая страница возвращается модели. Перед окончательным успехом verifier отдельно смотрит evidence.

Реальная автономная LLM-демонстрация остаётся внешней проверкой: ключа не было.

## 2. Структура файлов

```text
F:\AI Agent ТЗ\
├── .env.example
├── .gitattributes
├── .gitignore
├── pyproject.toml
├── requirements.lock
├── MANIFEST.in
├── README.md
├── IMPLEMENTATION_PLAN.md
├── TEST_REPORT.md
├── FINAL_REPORT.md
├── INTERVIEW_GUIDE.md
├── PROJECT_DEFENSE.md
├── DEMO_SCRIPT.md
├── MCP_STUDY.md
├── browser_agent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── agent.py
│   ├── browser.py
│   ├── observation.py
│   ├── extract.js
│   ├── context.py
│   ├── llm.py
│   ├── prompts.py
│   ├── tools.py
│   ├── safety.py
│   ├── loop_detection.py
│   └── logging_utils.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_context_safety.py
    ├── test_browser.py
    ├── test_provider.py
    ├── test_agent.py
    ├── test_public.py
    ├── test_live.py
    └── fixtures/
        ├── catalog.html
        ├── form.html
        └── frame.html
```

Локальные `.git`, `.venv`, `.browser-profile`, `logs`, `artifacts`, `build`, `dist` — служебные
каталоги; они не входят в исходный Git-архив. Wheel/sdist и архив исходников лежат в `dist`.

## 3. Установка

В данной папке окружение уже установлено. На другой машине:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m playwright install chromium
```

Для точных проверенных версий сначала установите `requirements.lock`, затем `-e . --no-deps`.

## 4. Настройка .env

Скопируйте `.env.example` в `.env` и в редакторе задайте `LLM_API_KEY`. Сохраните
`LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4.1-mini`, `HEADLESS=false`. `LLM_BASE_URL` оставьте пустым
для OpenAI. Секреты не показывайте на видео и не добавляйте в Git.

## 5. Точная команда запуска

```powershell
Set-Location 'F:\AI Agent ТЗ'
.\.venv\Scripts\python.exe -m browser_agent
```

Без ключа: `python -m browser_agent --check`. Для ручного login: `--login --start-url URL`.

## 6. Model/provider

OpenAI SDK + Responses API, default `gpt-4.1-mini`. Модель заменяется через `.env`.
Сторонний endpoint должен поддерживать Responses и strict function tools. Совместимость
произвольного OpenAI-compatible провайдера не обещается.

## 7. Как запустить tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

Для live API: задайте `RUN_LIVE_TESTS=1` и запустите `tests/test_live.py`. Для public smoke:
`RUN_PUBLIC_TESTS=1`, `tests/test_public.py`. Подробные команды и ожидания — в README.

## 8. Реальные результаты

38 passed, 3 skipped в основном наборе; 2 public tests отдельно passed; 1 agent integration
test отдельно прошёл в видимом Chromium. Установка, pip check, lint, compile и сборка успешны.
Wheel отдельно установлен, packaged extractor импортирован вне корня. [Детальный отчёт](TEST_REPORT.md).

## 9. Demo prompt

> Открой https://demo.playwright.dev/todomvc/. Добавь три задачи: «Прочитать README»,
> «Запустить тесты», «Записать демонстрацию». Отметь «Прочитать README» выполненной.
> Покажи только активные задачи. Сообщи, какие две задачи остались и сколько их.

Тайминг записи и второй UI — в DEMO_SCRIPT.md. Это инструкция будущего live-прогона,
не утверждение о выполненной моделью задаче.

## 10. Ограничения

Главное: live LLM пока не проверена из-за отсутствующего ключа. Нет автоматического CAPTCHA,
vision/canvas, закрытого shadow DOM, uploads/downloads, вложенного scroll и domain sandbox.
Safety эвристическая, verifier может ошибаться, память ограничена. MCP server не добавлен:
приоритет — стабильность core до live-проверки. Объяснение MCP и учебное упражнение есть.

## 11. Что читать первым

PROJECT_DEFENSE.md → README Architecture → `agent.py` → `models.py` → `llm.py`
→ `browser.py`/`observation.py` → INTERVIEW_GUIDE.md. В справочнике все 80 запрошенных тем,
с простым объяснением, примером, ответом и follow-up. Перед записью прочитайте TEST_REPORT.

## 12–13. Пять вероятных вопросов и ответы

1. **Где автономность?** LLM выбирает следующее действие по свежему observation, а не task-specific workflow.
2. **Как JSON становится кликом?** Schema validation → safety/confirmation → mapping ID → Playwright.
3. **Что если DOM изменился?** Pinned node и подпись проверяются; при stale — ошибка и новое наблюдение.
4. **Как ограничивается память?** Recent, сокращённые receipts и цитаты имеют лимиты, общий JSON — budget.
5. **Как проверяется успех?** `finish` запускает отдельный verifier на свежем evidence; отказ возвращает feedback.

## 14. Что понимать перед отправкой

Разницу между решением модели и execution, между валидным JSON и правильным действием,
между успешным click и выполненным goal. Понимать цену DOM-first и ограниченной памяти,
условия остановки и ограничения safety. Не выдавать mock/integration за live LLM benchmark.

После добавления ключа выполните live test, оба natural-language сценария и запишите настоящее
видео. Если появится ошибка, исправляйте общую причину, а не добавляйте ветку под demo-сайт.
Только после этого можно честно сказать работодателю, что live autonomous demo проверено.
