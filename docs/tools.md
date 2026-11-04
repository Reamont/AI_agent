# Контракты CLI

Общий префикс: `python -m strategist -p <папка>`. Вход — пути/JSON, выход — JSON
UTF-8. Ошибка — stderr JSON и exit 2; error в журнале, если база читается. `--help`
есть у каждой команды. Все команды локальные, кроме fetch.

| Команда | Вход → выход | Проверка / fallback |
|---|---|---|
| doctor | зависимости → версии, valid | сеть/модель не симулирует |
| init --config FILE | JSON → пустой проект | непустая папка защищена |
| status / resume | база → workflow, бюджет, next_action | resume проверяет ссылки/хеши; при повреждении стоп |
| ingest PATH | документ → SRC ID, локаторы, warnings | --origin, --rights, --supersedes ID, --expected-revision N; байтовая дедупликация |
| fetch URL --rights LICENSE | разрешённый HTTPS → источник | 20s, 12MB, redirect+DNS; --contains сохраняет минимальный фрагмент с исходным локатором; ошибка без выдуманного текста |
| claim FILE | JSON → утверждение | факт требует существующую точную цитату |
| decision FILE / promise FILE | JSON → запись | основания существуют; будущее явно помечено |
| strategy FILE | JSON → две стратегии и эксперимент | обязательные поля и связи, не экспертная оценка |
| analyze SRC-ID | CSV → группы/quality_errors | weighted retention, YYYY-MM, пропуски/дубликаты/границы |
| search QUERY / search --linked ID | подстрока/прямые связи → записи | не embeddings и не семантика |
| revise ID --status STATUS --reason TEXT | новая версия → transitive impact | прошлое сохраняется; --text требует повторной проверки |
| impact | база → все needs_review | ручная команда; scheduler отсутствует |
| progress FILE | поля workflow → новое состояние | только известные поля workflow |
| checkpoint --next TEXT | база → контрольная точка | сохраняет все поля и бюджет |
| validate [--strategy] | база → errors/warnings | хеши/цитаты/ссылки; warnings не равны провалу структуры |
| budget --amount N --minutes N | оценка → allowed/reasons | резервирует известный лимит до действия; неизвестная цена стоп |
| export | база → outputs/memory.md + project-export.json | исходная база остаётся основной |
| audit | каталог -p → находки без значений | эвристика секретов/ПДн, не DLP-гарантия |
| pack --root DIR --out OUTSIDE.zip | разрешённые файлы → zip+манифест | исключения, audit, SHA256 и testzip; не публикация |

Минимальный claim (заменить SRC на реальный ID из ingest):

```json
{
  "id": "C-01", "text": "Проверяемая формулировка", "type": "fact",
  "scope": "Конкретный документ, не весь рынок", "period": "2026-01",
  "confidence": {"level": "ограниченная", "reason": "Точная цитата, выборка неизвестна"},
  "limitations": ["Нужна сверка применимости"], "review_if": "Новый документ",
  "references": [{"source_id": "SRC-ID", "locator": "paragraph:1", "quote": "точная цитата"}],
  "depends_on": [], "counterevidence": []
}
```

Типы: fact/hypothesis/inference/forecast/unknown. Inference требует depends_on и method.
Статусы: current/needs_review/refuted/withdrawn. Даты/версии/history добавляет инструмент.
Counterevidence — существующие ID, альтернативные трактовки поясняются в журнале.
Решение: id/decision/selected_option/decision_maker/status/owner/basis/alternatives/
assumptions/actions/metrics/deadline/review_if. selected_option входит в alternatives;
decision_maker принимает решение, owner отвечает за исполнение. Статусы:
proposed/simulated/confirmed/rejected/needs_review. Для confirmed требуется
human_confirmation = {artifact, sha256}: JSON-артефакт внутри проекта с approved=true,
decision_id, selected_option и decision_maker, соответствующими записи. Это проверка
согласованности файла, не доказательство реальной личности или согласия; агент не
создаёт фиктивное человеческое подтверждение.
Обещание: id/basis/message/capability/available/limitation/allowed_wording;
если available=false, обязателен future_label. Контракт стратегии — фактический
пример `projects/demo/outputs/strategy.json` и валидатор engine.py.

Progress JSON содержит stage, completed[], open_questions[], pending[], human_decisions[],
errors[], next_action. Агент указывает содержательную проверку в logs/research.md,
не подменяет её технической фиксацией транзакции. Локальные транзакции не являются
оплаченными вызовами LLM. Budget — явный guard, не перехват всех возможных инструментов
среды; ведущий агент обязан вызвать его до внешнего расхода.

## Уточнения 0.2.0

- `decision FILE --update --reason TEXT` и `promise FILE --update --reason TEXT`
  принимают частичное обновление с тем же id, сохраняют прежнюю запись в history и
  повышают version. Нельзя вручную подменить version/history/created_at. Для снятия
  needs_review нужны актуальные basis и явный review_note. Подтверждение человека
  всё равно требуется отдельно. `--expected-revision N` доступен также claim,
  decision/promise, strategy и progress; проверка стратегии идёт под lock.
- `impact` включает strategy. `validate` проверяет envelope всех снимков и checkpoint,
  возвращает history с metadata_valid и artifacts_restorable. Утраченные исторические
  веб-байты после осознанной минимизации — предупреждение о восстановимости;
  повреждённый JSON истории — ошибка целостности. Это разные статусы.
- Обязательные поля config: name, currency, money_limit (≥0), time_budget_minutes (>0),
  allowed_domains (список hostname). Строки, bool, NaN/Infinity вместо чисел запрещены.
  JSON читает только стандартные конечные значения. max_source_bytes, если задан,
  — целое 1..128 MB. Обязательны все поля workflow; pending.status допускает
  not_started/in_progress/done/error/unknown/blocked, next_action — непустая строка.
- Источник имеет устойчивый ID/identity_sha256 первоисточника; sha256 относится к
  сохранённым байтам представления. representations хранит хеши/пути вариантов.
  Локальный импорт ищет совпадение хеша представления, даже если ID получен от полного
  веб-ответа. --supersedes выполняется и на cache hit; циклы и замена собой запрещены.
- events.transaction_status=committed означает фиксацию записи, status отдельно
  done/blocked/invalid/error. cost — фактический отдельный платёж (для этих CLI 0),
  requested_cost — запрос/резерв, result_valid — качество результата. Старые события
  до 0.2.0 сохраняются как legacy; их статус не переименован задним числом.
- budget резервирует деньги в spent (обратная совместимость имени) и плановое время
  в reserved_minutes. elapsed_minutes — фактически учтённое время. Например:
  `account-time --minutes 2.5 --description "Наблюдаемый интервал" --reference logs/timer.json --id TIME-01`.
  ID не повторяется, reference описывает основание измерения. Точный труд LLM и
  стоимость подписки неизвестны, автоматическая сумма tool_elapsed_seconds их не заменяет.
- pack проверяет активные состояния проектов, затем целостность ZIP; verified и
  archive_integrity относятся к архиву, project_validation — к состояниям.
  Ни один из них не означает готовность видео/доступа жюри или качество стратегии.
