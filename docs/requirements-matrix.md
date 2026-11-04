# Матрица требований 0.2.0

Спецификация: specification.md. Разбор всех 33 замечаний: review-fixes.md.
Статус «проверено инструментом» не означает экспертное качество стратегии.

| Требование | Статус | Реализация | Конкретная проверка / ограничение |
|---|---|---|---|
| Русский рабочий язык | реализовано | README, AGENTS, render_outputs, export | product/communication/experiment/options/memory.md; английские ID/JSON допустимы |
| Сохранение существующей работы | проверено инструментом | атомарные транзакции, history, Git | test_failed_transaction_no_partial_commit; старые снимки не переписаны |
| Минимальная архитектура | реализовано | одна LLM среды + Python CLI | architecture.md; не автономная платформа |
| Конфиг, ограничения, бюджет | проверено инструментом | validation.py + init | test_r09_invalid_config_and_nonfinite_limits; null/NaN/Infinity/строки/boolean отклоняются |
| Offline быстрый старт | проверено инструментом | requirements.lock, doctor | evals/clean-install.json: чистая папка и venv; установка wheels отдельно |
| Live-доступ к открытым сайтам | проверено на выбранном источнике | fetch, allowlist, TLS, timeout | реально получен CPython; другие домены не считаются проверенными |
| Объявленные зависимости/доступы | документировано | README, pyproject, lock | нет скрытых MCP/платных API; тариф подписки неизвестен |
| Один источник инструкций и адаптер Cursor | реализовано, GUI не проверен | AGENTS.md, .cursor/rules | другой GUI не тестировался |
| Методические знания отдельно от материалов | реализовано | knowledge/, inputs/sources/evidence | методы не считаются фактами о продукте |
| Постановка вопроса решения | текущий LLM-прогон, самооценка | demo/brief, research-plan | нет реального интервью руководителя |
| План от опровергающих вопросов | текущий LLM-прогон, самооценка | outputs/research-plan.md | нет независимой экспертной оценки |
| Markdown/TXT | проверено инструментом | extract | test_duplicate_import, тест injection; реальные fixture-файлы |
| CSV | проверено инструментом | extract/analyze | test_retention_weighted_and_quality; старый хеш test_r02 |
| DOCX | проверено инструментом | paragraphs/tables | test_formats_real_docx_xlsx_html; реальный DOCX в demo |
| XLSX, в том числе пустые начальные ячейки | проверено инструментом | enumerate rows, ranges | test_r01_sparse_xlsx_c3; формулы не вычисляются |
| PDF с текстовым слоем | проверено инструментом | pypdf | test_pdf_real_text_and_scanned_pdf; second/inputs/library.pdf |
| Скан/OCR/защищённый PDF | ограничено | понятная ошибка/предупреждение | OCR не реализован, не заявлен |
| Статический HTML | проверено инструментом | HTMLParser | test_formats_real_docx_xlsx_html, second/help.html; JS не исполняется |
| URL/дата/хеш/локатор/цитата | проверено инструментом | registry + check_reference | test_fake_locator_and_quote_rejected; original_response_sha256 отдельно от хеша представления |
| Дедупликация и замена независимы | проверено инструментом | representations + link_replacement | test_r03, test_r20; группы независимости оценивает агент |
| Качество данных/знаменатель/период | проверено инструментом | analyze | test_retention_weighted_and_quality; плохой CSV ожидаемо invalid |
| Причинность и контрсвидетельства | частично | инструкции, типы, граф | test_r05 проверяет граф; причинный вывод не автоматизирован |
| 4 стратегически разных варианта | самооценка текущей LLM | outputs/options.md | статус-кво/улучшение/сегмент/закрытие; смысл не доказывается unit-тестом |
| Сильные возражения, обратимость, жизнеспособность | исправлено, эксперт не проверял | O-KEEP/O-CLOSE и отдельные условия | review-fixes №24–26 |
| Продуктовая стратегия | текущий синтез, needs_review | outputs/product.md | источник возможностей обновлён, D30 всё ещё не доказан |
| Коммуникационный барьер — гипотеза | реализовано | C-COMM, communication.md | нет наблюдений реальных пользователей |
| Соответствие обещаний возможностям | проверено инструментом + самооценка текста | P-CURRENT v3, C-AVAILABLE-V2 | test_available_promise_cannot_use_hypothesis; текущий trace |
| Эксперименты без противоречивых исходов | исправлено, не проведено | experiment_stages | отдельно диагностика/прототип/пилот; реального baseline/MDE пока нет |
| Полный выбор в решении | проверено инструментом | decision, selected_option, decision_maker, owner | test_r13; demo D-03 proposed, не confirmed |
| Жизненный цикл решения | проверено на синтетическом артефакте | decision --update --reason | test_r12_decision_lifecycle_and_confirmation_artifact; не реальное согласие человека |
| Жизненный цикл обещания | проверено инструментом | promise --update + review_note | test_r12_promise_review_requires_current_basis_and_review_note; P-CURRENT v3 |
| Пересмотр по основаниям/контрсвидетельствам | проверено инструментом | invalidate | test_r05, test_transitive_impact_and_history |
| Пересмотр через обещания стратегии | проверено инструментом | promise_ids → strategy | test_r07; не только прямые basis |
| Нельзя тихо снять needs_review | проверено инструментом | set_strategy inside lock | test_r06, test_r16; explicit review_note при актуальных основаниях |
| Видимость стратегии в impact/validate | проверено инструментом | CLI impact, warnings | test_r08 |
| Версии прямых/каскадных изменений | проверено инструментом | bump | test_r05; миграция старых текущих версий отдельной транзакцией |
| Поиск по словам, ID и связям памяти | проверено инструментом | search | test_r17; embeddings/семантика не реализованы |
| Checkpoint/resume без истории чата | проверен новый процесс; новый чат не проверен | файловая база | test_new_process_resume_and_portability; llm-traces текущей сессии |
| Целостность истории и её восстановимость | проверено инструментом | history_check | test_r15; после минимизации не все старые веб-байты доступны, это warnings/history |
| Workflow и конфликты | проверено инструментом | validation, lock/CAS | test_r10, test_stale_revision_and_lock; неизвестный внешний эффект не повторять |
| Контракт ошибок | проверено инструментом | JSON stderr, exit 2 | test_r11; документные исключения и PDF warnings нормализованы |
| Бюджет неизвестной стоимости | проверено инструментом | budget | test_budget_unknown_money_time; это явный guard, не перехват всех tools среды |
| Журнал исхода и фактической цены | проверено инструментом | outcome/transaction_status/cost/requested_cost | test_r18; старые записи сохраняются как legacy, не переписаны |
| Фактическое и резервируемое время | проверено инструментом | account-time, reserved_minutes | test_r19; календарный интервал demo18.4594 мин с паузами, не точный труд LLM |
| Недоверенные инструкции источника | проверен CLI и один текущий LLM-прогон | trust + flags + инструкции | test_prompt_injection_is_data_not_execution; нет гарантии любой LLM против любых инъекций |
| Secret/PII audit | эвристически проверено | audit + исключения | test_secret_exclusion_detection_archive_and_paths; картинки/видео вручную |
| Защита от SSRF/redirect | ограниченно проверено | HTTPS allowlist, DNS, proxy | test_ssrf_domain_and_redirect_rules; DNS rebinding-границы в architecture.md |
| Фикстуры не перезаписывают файлы | проверено инструментом | require empty folder | test_r21 |
| Упаковка пригодного состояния | проверено инструментом | pack → validate каждого проекта → ZIP hashes | test_r22; verified не означает готовность конкурсной сдачи |
| Первый импорт «новых данных» в исходном demo | уточнено | logs/research.md | это отложенная интерпретация, исходные события сохранены |
| Новый источник действительно после resume | текущий реальный прогон сохранён | capability-update-after-resume | llm-traces/continuation.jsonl: точные input/argv/output/hash; не новый независимый чат |
| Вторая задача и иной следующий шаг | текущий реальный прогон сохранён | second PDF/HTML → гайд прав | llm-traces/second-task.jsonl; unit-test проверяет только хранение next_action |
| Все 13 дополнительных возможностей оценены | документировано | extensions.md | частичные/нереализованные функции явно отмечены |
| Baseline | не измерено | evals/baseline.md | независимый обычный чат/аналитик не запускался; ускорение не заявлено |
| PDF, реальные скриншоты и ссылки версий | реализовано и визуально проверяется | tools/report.py | keepWithNext и GitHub commit links; report-check.json |
| Обязательное видео нового чата | не готово | video-script.md, video-check.json | техническая запись CLI отдельно не заменяет сквозной новый чат |
| Ссылки/доступ жюри | не проверено независимо | submission/README.md | GitHub API Forbidden; видимость не менялась; разрешённый видеохостинг не подключён |
| Финальная отправка капитаном | не выполнено агентом | submission/README.md | задача капитана |

Четыре критерия конкурса и пределы самооценки — quality.md. Никакие баллы жюри не обещаны.
