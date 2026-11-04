# Исправления по ревью (версия 0.2.0)

Вход ревью: review-input.md. Исходный commit: e9f368f. История и прежние результаты
не подменяются: исправлены текущие записи и добавлена новая трасса. Статусы ниже
относятся к конкретным свидетельствам, а не к готовности полного конкурсного пакета.

| № | Исправление / граница | Свидетельство |
|---|---|---|
| 1 | XLSX: номер строки берётся из enumerate, пустые строки пропускаются | test_r01_sparse_xlsx_c3 |
| 2 | CSV читается один раз в lock; проверяется хеш именно этих байтов до расчёта | test_r02_tampered_csv_no_result_overwrite |
| 3 | Связь замены обрабатывается и при дедупликации; повтор связи идемпотентен | test_r03_dedup_still_links_replacement_and_invalidates |
| 4 | Факт по заменённому источнику получает needs_review; ложный current не проходит validate | test_r04_replaced_source_cannot_support_current_fact |
| 5 | Контрсвидетельства участвуют в транзитивных зависимостях | test_r05_counterevidence_invalidates_and_versions |
| 6 | Повторное сохранение не очищает needs_review со старыми основаниями | test_r06_resaving_stale_strategy_does_not_clear_review |
| 7 | Пересмотр обещания пересматривает связанную стратегию | test_r07_strategy_depends_on_promise_not_only_direct_basis |
| 8 | impact включает стратегию; validate показывает предупреждение | test_r08_impact_and_validate_show_strategy |
| 9 | Обязательные поля/типы/конечные бюджеты; JSON NaN/Infinity отклоняются | test_r09_invalid_config_and_nonfinite_limits; validation.py |
| 10 | Строгая структура workflow и допустимые pending-статусы | test_r10_progress_wrong_types_are_rejected |
| 11 | Некорректные структуры/документы возвращают JSON exit 2, без traceback/сырых PDF warnings | test_r11_malformed_json_shapes_and_documents_return_json_errors |
| 12 | decision/promise --update --reason; версии/история; review_note и проверка основания при завершении пересмотра | test_r12_decision_lifecycle_and_confirmation_artifact; test_r12_promise_review_requires_current_basis_and_review_note |
| 13 | Требуются decision, selected_option, decision_maker отдельно от owner | test_r13_decision_requires_actual_choice_and_decision_maker |
| 14 | Одна bump-процедура для прямых и каскадных изменений; прямой revise не получает двойную версию | test_r05_counterevidence_invalidates_and_versions; актуальные C-DECLINE/C-CAUSE нормализованы явной миграцией |
| 15 | Проверяются все envelope/ревизии истории; восстановимость материалов отделена от целостности метаданных | test_r15_corrupt_history_and_unavailable_artifacts_distinct; validate.history |
| 16 | Проверка стратегии выполняется внутри lock; поддерживается expected_revision | test_r16_strategy_validation_uses_locked_state |
| 17 | Поиск по ID и текстовым полям решений/обещаний | test_r17_search_decision_id_and_promise_content |
| 18 | transaction_status отдельно от done/blocked/invalid/error; cost — факт, requested_cost — запрос | test_r18_rejection_and_invalid_analysis_not_logged_as_success |
| 19 | reserved_minutes отдельно от elapsed_minutes; account-time с уникальным ID и основанием | test_r19_account_actual_time_separately_from_reservation; TIME-ORIGINAL-DEMO = 18.4594 мин календарного времени с паузами |
| 20 | Stable ID первоисточника отдельно от identity_sha256 и representations[].sha256; дедуп по представлениям | test_r20_legacy_stable_id_deduplicates_by_representation; metadata текущего источника демо |
| 21 | Генератор требует пустую папку до первого изменения | test_r21_fixture_generator_preserves_existing_csv |
| 22 | pack валидирует каждое состояние проекта до ZIP; целостность архива и scope показаны отдельно | test_r22_pack_refuses_corrupt_state |
| 23 | Первая история названа отложенной интерпретацией; новый capability-update импортирован действительно после resume | evals/llm-traces/continuation.jsonl; inputs/capability-update-after-resume.md |
| 24 | Возражение к статус-кво теперь описывает риск сохранения нерешённого барьера | outputs/options.md → O-KEEP |
| 25 | Пауза и закрытие разделены; названы необратимые миграция/удаление/утрата доверия | outputs/options.md → O-CLOSE |
| 26 | Четыре разных, ещё не проверенных условия жизнеспособности | outputs/strategy.json → options |
| 27 | Диагностика, прототип и причинный пилот разделены; для каждого отдельные взаимоисключающие исходы | outputs/experiment.md; strategy.experiment_stages |
| 28 | C-COMM зарегистрирована как непроверенная гипотеза; функция не выдаётся за доказательство барьера | outputs/communication.md; claim C-COMM |
| 29 | Частично: сохранены точные входы, текущие ответы LLM, argv, stdout/stderr и хеши двух прогонов | evals/llm-traces/*.jsonl; это self-recorded текущая сессия, не независимый новый чат и не provider transcript |
| 30 | Матрица разбита по проверяемым возможностям с конкретными тестами/артефактами и пределами | requirements-matrix.md |
| 31 | Markdown результатов генерируется с русскими подписями и статусами; JSON сохраняет английские ключи | tools/render_outputs.py; engine.export |
| 32 | Заголовки PDF keepWithNext; добавлены действующие ссылки на конкретную версию файлов GitHub | tools/report.py; submission/report-check.json |
| 33 | Частично: новый текущий прогон есть; независимого нового чата и полной записи его работы нет; публикация/доступ жюри остаются незавершёнными | submission/README.md, video-check.json; GitHub API при проверке дал Forbidden, видимость не менялась |

Здесь «тест» означает проверку инструментов. Ни один unit-тест не подтверждает
обобщаемое качество LLM, спрос, реальное согласие человека или независимый новый чат.
