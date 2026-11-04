# Стратег Фабрики проектов

Агент для руководителя цифрового продукта: от неоднозначного запроса к проверяемой
продуктовой и коммуникационной стратегии, затем к сохранению и пересмотру решения.
Работает в Cursor, Codex или другой LLM-среде с доступом к файлам и терминалу.
Исполнитель исследования — **LLM среды**; Python CLI отвечает за данные, расчёты
и память. Это не автономная платформа и не готовый SaaS.

Версия: **0.1.0**. [Пакет сдачи](submission/README.md) · [Демо](projects/demo/README.md) ·
[Матрица требований](docs/requirements-matrix.md) · [Ограничения](docs/architecture.md).

## Быстрый старт

Требуется Python **3.12+** (проверено 3.12.14), pip, 25 MB для runtime и место для
материалов. Linux проверен; macOS/Windows с Python не проверены. Для установки
нужны pypi.org и files.pythonhosted.org либо локальный wheelhouse.
Все runtime/build версии закреплены в requirements.lock; платных API, ключей,
обязательных MCP и фоновых сервисов нет. Отдельный веб-сервер не требуется.

**Команды терминала** из корня этого репозитория:

```bash
python3 -m venv .venv
# Linux/macOS; Windows: .venv\Scripts\activate
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m strategist doctor
python -m unittest discover -s tests -v
python -m strategist -p projects/demo validate --strategy
python -m strategist -p projects/demo resume
```

Прочитай [итог пересмотра](projects/demo/outputs/revision.md). Готовые документы —
сохранённый учебный прогон, не новое исследование. Данные продукта синтетические;
внешний методический источник реально загружен по HTTPS, URL/дата/хеш сохранены.
Официального брифа МегаФона нет; доступ к закрытым системам не заявлен.

**Обычное сообщение агенту** после открытия папки (это не терминал и не slash-команда):

> Прочитай AGENTS.md. Восстанови projects/demo из файлов. Проверь impact и объясни,
> почему после C-UPDATE прежняя рекомендация требует пересмотра. Продолжи с точного
> следующего действия, не выдумывая зрелую D30 когорту.

Cursor-адаптер `.cursor/rules/strategist.mdc` ссылается на AGENTS.md. В другой среде
явно попроси прочитать AGENTS.md; специальной встроенной команды здесь не создано.
Инструменты/подписка LLM предоставляются твоей средой; их тариф оплачивается отдельно
и неизвестен этому проекту. Для чтения готового демо LLM не нужна; для нового синтеза нужна.

## Новый проект и остановка

Скопируй config.example.json в свой файл вне приватных данных, задай вопрос/получателя,
срок либо null, домены, разрешённые материалы, ограничения и лимиты. Не помещай секреты
в конфиг. `init` откажется перезаписывать непустую папку.

```bash
python -m strategist -p projects/my-product init --config config.example.json
python -m strategist -p projects/my-product ingest /path/to/allowed-brief.docx
python -m strategist -p projects/my-product status
# Остановиться после записи выводов и workflow:
python -m strategist -p projects/my-product checkpoint --next "Проверить определение D30"
# В новом чате/процессе:
python -m strategist -p projects/my-product resume
```

Затем обычным текстом агенту: «Поставь вопрос решения по материалам проекта,
предложи минимальную опровергающую проверку; сохраняй шаги и источники».
Список контрактов и примеры JSON — [docs/tools.md](docs/tools.md).

## Два режима

**Без сети и ключей после установки:** импорт MD/TXT/PDF/DOCX/CSV/XLSX/локального HTML,
арифметика retention, проверка источников, версии, impact, checkpoint/resume, поиск
слов и связей, экспорт и архив. Все тесты unittest выполняются без сети. Подписка
LLM нужна только если просишь новую интерпретацию/стратегию. Офлайн-установка требует
заранее подготовленных wheels; pip впервые использует сеть.

**Живое исследование:** LLM среды, реально доступный веб-поиск среды (если есть),
CLI fetch для статических разрешённых HTTPS-страниц. Поисковый сервис в проект не
встроен. Разрешённые домены проекта и сети среды — разные ограничения; нужны оба.
Пример из сохранённого демо:

```bash
python -m strategist -p projects/demo fetch \
  https://raw.githubusercontent.com/python/cpython/3.12/Doc/library/statistics.rst \
  --rights PSF-2.0 --contains 'Fast, floating-point arithmetic mean'
```

`--rights` — заявленное проверенное основание копирования, не автоматическая проверка
лицензии. По умолчанию полный снимок сайта не сохраняется без этого выбора. Для других
материалов права и маршрут передачи проверяет ведущий агент. Новые платные действия
и внешняя обработка запрещены до разрешения. Неизвестная стоимость блокирует бюджетную
проверку: `python -m strategist -p projects/demo budget` завершится кодом 2.

## Проверки, экспорт и сдача

```bash
python -m strategist -p projects/demo impact
python -m strategist -p projects/second resume
python -m strategist -p projects/demo export
python -m strategist -p . audit
python -m strategist pack --root . --out /tmp/strategist-0.1.0.zip
```

Код возврата 0 — успешный инструмент; 2 — ошибка, невалидные данные или остановка
бюджета. Успешная структурная валидация не означает истинность стратегии. Спорные
основания видны в предупреждениях. Пакет не публикуется автоматически; загрузку
и доступ жюри настраивает владелец. [Реестр сдачи](submission/README.md) перечисляет
отсутствующие видео/публикацию и статус PDF. Не называй весь пакет готовым до их завершения.

Для пересоздания отчёта нужны отдельные зависимости `requirements-report.txt`,
шрифт DejaVu Sans, системный Chromium либо браузер Playwright. Это необязательные
зависимости рабочего агента. Команда и параметры: `python tools/report.py --help`.
