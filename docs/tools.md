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
Решение: id/status/owner/basis/alternatives/assumptions/actions/metrics/deadline/review_if;
status proposed/simulated/confirmed/rejected. Человек и владельцы не выдумываются.
Обещание: id/basis/message/capability/available/limitation/allowed_wording;
если available=false, обязателен future_label. Контракт стратегии — фактический
пример `projects/demo/outputs/strategy.json` и валидатор engine.py.

Progress JSON содержит stage, completed[], open_questions[], pending[], human_decisions[],
errors[], next_action. Агент указывает содержательную проверку в logs/research.md,
не подменяет её технической фиксацией транзакции. Локальные транзакции не являются
оплаченными вызовами LLM. Budget — явный guard, не перехват всех возможных инструментов
среды; ведущий агент обязан вызвать его до внешнего расхода.
