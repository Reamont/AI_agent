# Навигация по учебному демо

1. [Бриф](brief.md), [план](outputs/research-plan.md), [реестр](outputs/sources.md).
2. [Варианты](outputs/options.md), [продукт](outputs/product.md),
   [коммуникации](outputs/communication.md), [обещания](outputs/promises.md),
   [проверка](outputs/experiment.md).
3. **Сначала прочитать итог:** [пересмотр](outputs/revision.md). Предыдущие стратегии
   — сохранённый вариант до новых данных, их нельзя представлять актуальными.
4. [Журнал](logs/research.md), [impact](logs/revision-impact.json),
   [resume в другом процессе](logs/resume-new-process.json), state/checkpoint.json.

Терминал из корня: `python -m strategist -p projects/demo resume`, затем `impact`.
Обычный текст агенту: «Прочитай AGENTS.md, восстанови demo, проверь C-UPDATE и
объясни следующий шаг». Это чтение сохранённого прогона; новое исследование требует LLM.

После ревью: новая проверяемая трасса текущей LLM-сессии находится в evals/llm-traces/continuation.jsonl от корня. Первоначальный импорт measurement-update до D-01 обозначен как отложенная интерпретация; новый capability-update действительно добавлен после записанного resume.
