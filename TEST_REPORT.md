# Отчёт реальных проверок

Дата: 21 сентября 2026. Среда: Windows, Python 3.12.14, Chromium через Playwright 1.63.0.
Провайдер: OpenAI SDK 2.54.0; Pydantic 2.13.5; pytest 9.1.1.
Точные установленные зависимости: `requirements.lock`.

## Что действительно выполнено

| Проверка | Команда / метод | Результат |
|---|---|---|
| Установка | `python -m pip install -e ".[dev]"` | Успешно |
| Chromium | `python -m playwright install chromium` | Установлен |
| CLI/help | `python -m browser_agent --help` | Успешно |
| Видимый браузер без LLM | `python -m browser_agent --check --close-on-finish` | Chromium запущен, observation получен |
| Основной набор | `python -m pytest -q` | **38 passed, 3 skipped** |
| Публичные UI | `RUN_PUBLIC_TESTS=1`, `pytest tests/test_public.py -q` | **2 passed** |
| Цикл в видимом Chromium | `TEST_HEADFUL=1`, тест `test_real_browser_loop_compaction_and_verifier_rejection` | **1 passed** |
| Lint | `ruff check .` | Успешно |
| Форматирование | `ruff format` / финальный `--check` | Соответствует formatter |
| Компиляция Python | `python -m compileall -q browser_agent` | Успешно |
| Совместимость зависимостей | `python -m pip check` | No broken requirements |
| Упаковка | `python -m build` | Созданы wheel и sdist |
| Установка wheel | `pip install --no-deps --target artifacts/wheel-check ...whl` | Успешно |
| Ресурс внутри wheel | Импорт `observation` из установленного wheel вне корня проекта | `extract.js` найден и прочитан |
| Git ignore | Проверены `.env`, browser profile, logs | Исключены |
| Поиск hardcode в core | Домены demo, hh.ru, yandex, burger, spam, /vacancies, data-qa | Совпадений нет |

3 пропуска в обычном наборе — 2 публичных теста, включаемых отдельно, и 1 live LLM test.
Публичные отдельно выполнены. Live остаётся пропущенным из-за отсутствующего ключа.

## Что покрывают тесты

- Строгие аргументы, запрет лишних полей, неверных схем URL/ID/клавиш и неверных типов.
- Ограничение памяти, compaction, сохранение goal, точные цитаты, character budget.
- Loop detection при изменяющихся runtime IDs и отсутствие ложной петли при progress.
- Safety для чувствительных/неизвестных controls, поиска, ссылок и password fields.
- Реальный DOM: hidden/offscreen filtering, маскировка password value, dynamic search/cart.
- Устаревшие IDs, замена узла и изменение смысла кнопки.
- Select, checkbox, прозрачный custom checkbox, открытый shadow DOM, iframe, новые вкладки.
- Отказ подтверждения без side effect, успешное `YES`, изменение формы во время approval.
- Целый agent loop с fixture-specific provider: отклонённый ранний finish, продолжение,
  новые observations, compaction и подтверждённый итог.
- Уточнение пользователя, отсутствие ввода, bounded malformed decisions и dry-run.
- Настоящий официальный SDK с **HTTP mock**: `/v1/responses`, strict tools, запрет параллельных
  вызовов, отказ от хранения ответа, редактирование credential из входа, validation ответа,
  retry после 429, отсутствие retry/leak при 401, отдельная схема verifier.

## Два внешних интерфейса

1. `demo.playwright.dev/todomvc/`: ввод задачи, Enter, появление строки, checkbox, фильтр Completed.
2. `books.toscrape.com`: переход в категорию, открытие карточки товара по данным observation.

Эти проверки используют реальные внешние страницы и общий BrowserController.
Последовательность здесь задана **в тестах**, поэтому это подтверждение browser primitives,
а не доказательство автономного выбора действий LLM. Второй natural-language live scenario
ещё требуется выполнить после настройки ключа.

## Найденные и исправленные проблемы

Первый локальный поиск выявил неправильные кавычки в HTML fixture: обработчик submit не работал.
Фикстура исправлена; core под неё не изменялся. Для browser tests также выбран реалистичный timeout.

TodoMVC выявил прозрачный native checkbox, скрытый старым правилом opacity. Исправлено общее
правило извлечения checkbox/radio с видимой областью взаимодействия. Добавлен окружающий текст
для различения одинаково названных controls. Никакой проверки домена в core не появилось.

## Что не проверено и почему

**API-ключ отсутствует.** Не выполнены: живой вызов OpenAI, доступ выбранной модели в конкретном
аккаунте, качество её решений, стоимость полноценной задачи, автономное выполнение двух
публичных natural-language сценариев и запись видео. SDK HTTP-mock не заменяет эти проверки.

Не заявлены: Linux/macOS runtime проверка, другие модели/провайдеры, реальная почта/платёж,
закрытый shadow DOM, canvas, CAPTCHA обход, универсальная защита prompt injection.
Unit test injection проверяет разделение данных, а не adversarial устойчивость реальной LLM.

## Что запустить после добавления ключа

```powershell
$env:RUN_LIVE_TESTS="1"
.\.venv\Scripts\python.exe -m pytest tests/test_live.py -q
Remove-Item Env:RUN_LIVE_TESTS
.\.venv\Scripts\python.exe -m browser_agent
```

Затем выполните оба natural-language задания из README. Запишите фактический статус, число
шагов, вызовы к человеку, время и ошибки. Только после этого заявляйте готовность live demo.
