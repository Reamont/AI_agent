import copy
import csv
import json
import math
import re
import io
from pathlib import Path
from .store import Problem, load, transaction, safe_path, now, digest, canonical, atomic, bump, outcome, unwrap, read_json
from .ingest import invalidate, superseded, predecessors
from .validation import obj, text, strings, number, config_errors, workflow_errors, budget_errors

TYPES = {"fact", "hypothesis", "inference", "forecast", "unknown"}
STATUSES = {"current", "needs_review", "refuted", "withdrawn"}


def check_reference(root, s, ref):
    obj(ref, "reference")
    for key in ("source_id", "locator", "quote"):
        text(ref.get(key), "reference." + key)
    source = s["sources"].get(ref.get("source_id"))
    if not source:
        raise Problem("Источник утверждения не найден")
    primary = {k: source[k] for k in ("path", "sha256", "extracted", "extracted_sha256")}
    representations = [primary] + source.get("representations", [])
    matched = False
    for representation in representations:
        if ref.get("representation_sha256") and ref["representation_sha256"] != representation["sha256"]:
            continue
        checked_source(root, representation)
        extracted = json.loads(safe_path(root, representation["extracted"]).read_text())
        if digest(canonical(extracted)) != representation["extracted_sha256"]:
            raise Problem("Изменился хеш извлечённого материала")
        if any(c["locator"] == ref["locator"] and ref["quote"] in c["text"] for c in extracted["chunks"]):
            matched = True
    if not matched:
        raise Problem("Локатор или цитата не совпадают с сохранённым представлением источника")


def checked_source(root, source):
    data = safe_path(root, source["path"]).read_bytes()
    if digest(data) != source["sha256"]:
        raise Problem("Изменился хеш фактически прочитанного источника")
    return data


def claim_stale(s, c):
    return (any(superseded(s, r["source_id"]) for r in c["references"]) or
            any(s["claims"][cid]["status"] != "current" for cid in c.get("depends_on", []) + c.get("counterevidence", [])))


def add_claim(root, c, expected_revision=None):
    obj(c, "claim")
    c = copy.deepcopy(c)
    with transaction(root, "claim", "Сохранить проверяемое утверждение", [c.get("id")], expected_revision) as s:
        required = ["id", "text", "type", "scope", "period", "confidence", "limitations", "review_if"]
        if any(k not in c or c[k] is None for k in required):
            raise Problem("У утверждения не заполнены обязательные поля")
        for key in ("id", "text", "type", "scope", "period", "review_if"):
            text(c[key], key)
        strings(c["limitations"], "limitations")
        if c["type"] not in TYPES or c["id"] in s["claims"]:
            raise Problem("Некорректный тип или повтор ID")
        if not isinstance(c["confidence"], dict) or not c["confidence"].get("reason"):
            raise Problem("Нужна уверенность с объяснением")
        c.setdefault("references", [])
        c.setdefault("depends_on", [])
        c.setdefault("counterevidence", [])
        strings(c["depends_on"], "depends_on")
        strings(c["counterevidence"], "counterevidence")
        if not isinstance(c["references"], list):
            raise Problem("references должен быть списком")
        if c["type"] == "fact" and not c["references"]:
            raise Problem("Факт требует первоисточник и точную цитату")
        if c["type"] == "inference" and (not c["depends_on"] or not c.get("method")):
            raise Problem("Производный вывод требует исходные утверждения и метод")
        for ref in c["references"]:
            check_reference(root, s, ref)
        for cid in c["depends_on"] + c["counterevidence"]:
            if cid not in s["claims"]:
                raise Problem("Зависимость утверждения не найдена")
        c.update(status="current", created_at=now(), version=1, history=[])
        if claim_stale(s, c):
            c["status"] = "needs_review"
        s["claims"][c["id"]] = c
    return c


def revise(root, cid, status, reason, text=None):
    if status not in STATUSES or not reason.strip():
        raise Problem("Нужен корректный статус и причина")
    with transaction(root, "revise", "Исправить утверждение и найти последствия", [cid]) as s:
        if cid not in s["claims"]:
            raise Problem("Утверждение не найдено")
        c = s["claims"][cid]
        bump(c, reason)
        c["status"] = status
        if text:
            c["text"] = text
            # Переписанный факт должен заново пройти проверку источника агентом.
            if status == "current":
                c["status"] = "needs_review"
        if c["status"] == "current" and claim_stale(s, c):
            raise Problem("Нельзя подтвердить утверждение с устаревшим основанием/источником")
        for ref in c["references"]:
            check_reference(root, s, ref)
        result = invalidate(s, claim_ids=[cid], skip_roots=True)
    return result


def record_check(root, s, collection, record):
    obj(record, collection)
    text(record.get("id"), "id")
    strings(record.get("basis"), "basis", nonempty=True)
    if any(c not in s["claims"] for c in record["basis"]):
        raise Problem("Нужны существующие основания")
    if collection == "decisions":
        for field in ("status", "decision", "selected_option", "decision_maker", "owner", "deadline", "review_if"):
            text(record.get(field), field)
        for field in ("alternatives", "assumptions", "metrics"):
            strings(record.get(field), field, nonempty=True)
        if record["selected_option"] not in record["alternatives"]:
            raise Problem("Выбранный вариант отсутствует среди альтернатив")
        if not isinstance(record.get("actions"), list) or not record["actions"] or any(not isinstance(a, dict) for a in record["actions"]):
            raise Problem("actions: требуется непустой список объектов")
        if record["status"] not in {"proposed", "simulated", "confirmed", "rejected", "needs_review"}:
            raise Problem("Недопустимый статус решения")
        if record["status"] == "confirmed":
            confirmation = obj(record.get("human_confirmation"), "human_confirmation")
            path = safe_path(root, text(confirmation.get("artifact"), "confirmation.artifact"))
            if digest(path.read_bytes()) != confirmation.get("sha256"):
                raise Problem("Хеш подтверждения человека не совпал")
            approval = read_json(path)
            if not isinstance(approval, dict) or approval.get("approved") is not True or any(approval.get(k) != record[k] for k in ("selected_option", "decision_maker")) or approval.get("decision_id") != record["id"]:
                raise Problem("Артефакт подтверждения не соответствует решению")
            if record["decision_maker"] == "не назначен":
                raise Problem("Не указан принимающий решение")
    else:
        for field in ("message", "capability", "limitation", "allowed_wording"):
            text(record.get(field), field)
        if type(record.get("available")) is not bool:
            raise Problem("available: требуется boolean")
        if record.get("status", "current") not in STATUSES:
            raise Problem("Недопустимый статус обещания")
        if record["available"] and any(s["claims"][c]["type"] != "fact" for c in record["basis"]):
            raise Problem("Доступность обещания нельзя подтверждать гипотезой")
        if not record["available"]:
            text(record.get("future_label"), "future_label")


def add_record(root, collection, record, expected_revision=None):
    obj(record, collection)
    record = copy.deepcopy(record)
    with transaction(root, collection, "Сохранить решение или обещание", [record.get("id")], expected_revision) as s:
        if not record.get("id") or record["id"] in s[collection]:
            raise Problem("Отсутствует или повторяется ID")
        record.setdefault("status", "current")
        record_check(root, s, collection, record)
        if any(s["claims"][c]["status"] != "current" for c in record["basis"]):
            record["status"] = "needs_review"
        record.update(created_at=now(), history=[], version=1)
        s[collection][record["id"]] = record
    return record


def update_record(root, collection, update, reason, expected_revision=None):
    obj(update, collection)
    text(reason, "Причина обновления")
    with transaction(root, "update_" + collection, reason, [update.get("id")], expected_revision) as s:
        old = s[collection].get(update.get("id"))
        if not old:
            raise Problem("Обновляемая запись не найдена")
        if set(update) & {"version", "history", "created_at"}:
            raise Problem("Версии, историю и дату создания изменяет инструмент")
        record = {**copy.deepcopy(old), **update}
        record_check(root, s, collection, record)
        stale = any(s["claims"][c]["status"] != "current" for c in record["basis"])
        if record["status"] in ("current", "proposed", "confirmed", "simulated"):
            if stale:
                raise Problem("Нельзя завершить пересмотр с неактуальными основаниями")
            if old["status"] == "needs_review" and not record.get("review_note"):
                raise Problem("Для завершения пересмотра нужен review_note")
        bump(record, reason)
        # История должна содержать фактическую старую запись, а не уже изменённые поля.
        record["history"][-1]["before"] = {k: copy.deepcopy(v) for k, v in old.items() if k != "history"}
        s[collection][record["id"]] = record
        if collection == "promises" and s.get("strategy") and record["id"] in s["strategy"]["promise_ids"]:
            bump(s["strategy"], "Изменилось связанное обещание")
            s["strategy"]["status"] = "needs_review"
    return record


def strategy_stale(st, s):
    return (any(s["claims"][cid]["status"] != "current" for cid in st["basis"]) or
            any(s["promises"][pid]["status"] != "current" for pid in st["promise_ids"]))


def set_strategy(root, strategy, expected_revision=None):
    with transaction(root, "strategy", "Сохранить две согласованные стратегии", expected_revision=expected_revision) as s:
        errors = strategy_errors(strategy, s)
        if errors:
            raise Problem("; ".join(errors))
        old = s.get("strategy")
        record = copy.deepcopy(strategy)
        record["version"] = old.get("version", 1) if old else 1
        record["history"] = copy.deepcopy(old.get("history", [])) if old else []
        if old:
            bump(record, "Новая редакция стратегии")
            record["history"][-1]["before"] = {k: copy.deepcopy(v) for k, v in old.items() if k != "history"}
        needs_review = strategy_stale(record, s) or (old and old["status"] == "needs_review" and not record.get("review_note"))
        record.update(status="needs_review" if needs_review else "proposed", saved_at=now())
        s["strategy"] = record
    return record


def strategy_errors(st, s):
    errors = []
    if not isinstance(st, dict):
        return ["Стратегия отсутствует"]
    options = st.get("options", [])
    if not isinstance(options, list) or any(not isinstance(o, dict) for o in options):
        return ["options: требуется список объектов"]
    if any(not isinstance(o.get("kind"), str) for o in options):
        return ["kind: требуется строка"]
    if not {"status_quo", "improve", "pivot", "close"} <= {o.get("kind") for o in options}:
        errors.append("Нужны четыре разных типа вариантов")
    fields = ["id", "audience", "job", "value", "difference", "changes", "economics", "communication", "cost", "timing", "dependencies", "risks", "reversibility", "objection", "falsifier", "viability", "test"]
    for o in options:
        if any(not isinstance(o.get(f), str) or not o[f].strip() for f in fields):
            errors.append(f"Вариант {o.get('id')} неполон")
    for section, fields in {
        "product": ["segment", "job", "context", "alternatives", "direction", "difference", "non_goals", "boundaries", "capabilities", "economics", "assumptions", "sequence"],
        "communication": ["audience", "situation", "barrier", "positioning", "message", "proof", "channels", "cta", "limits", "comprehension_test"],
        "experiment": ["id", "hypothesis", "change", "metric", "baseline", "control", "unit", "sample", "duration", "business_effect", "success", "failure", "inconclusive", "guardrails", "owner", "action"]
    }.items():
        if not isinstance(st.get(section), dict) or any(not isinstance(st[section].get(f), str) or not st[section][f].strip() for f in fields):
            errors.append(f"Неполный раздел {section}")
    if any(not isinstance(st.get(f), str) or not st[f].strip() for f in ("comparison", "sensitivity", "recommendation")):
        errors.append("Нет сравнения, чувствительности или рекомендации")
    if not isinstance(st.get("basis"), list) or not st["basis"] or any(not isinstance(cid, str) or cid not in s["claims"] for cid in st["basis"]):
        errors.append("У стратегии нет существующих оснований")
    if not isinstance(st.get("promise_ids"), list) or not st["promise_ids"] or any(not isinstance(pid, str) or pid not in s["promises"] for pid in st["promise_ids"]):
        errors.append("Не найдены проверяемые обещания")
    return errors


def analyze(root, sid):
    with transaction(root, "analyze", "Проверить хеш, качество и расчёт", [sid]) as s:
        source = s["sources"].get(sid)
        if not source or not source["path"].endswith(".csv"):
            raise Problem("Для расчёта нужен импортированный CSV")
        data = checked_source(root, source)
        if superseded(s, sid):
            raise Problem("Источник заменён: выберите его актуальную версию")
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        required = {"period", "cohort", "eligible", "retained"}
        if not rows or not required <= rows[0].keys():
            raise Problem("Нужны period, cohort, eligible, retained и непустые данные")
        errors, groups, seen = [], {}, set()
        for i, row in enumerate(rows, 2):
            if any(row.get(k) is None or not str(row[k]).strip() for k in required):
                errors.append(f"row:{i}: пропуски")
                continue
            key = (row["period"], row["cohort"])
            if key in seen:
                errors.append(f"row:{i}: дубликат period/cohort")
            seen.add(key)
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", row["period"]):
                errors.append(f"row:{i}: несогласованный период (нужен YYYY-MM)")
            try:
                n, k = float(row["eligible"]), float(row["retained"])
                if not all(math.isfinite(x) and x.is_integer() for x in (n, k)) or not 0 <= k <= n or n <= 0:
                    raise ValueError()
            except ValueError:
                errors.append(f"row:{i}: неверный знаменатель/числитель")
                continue
            g = groups.setdefault(row["period"], {"eligible": 0, "retained": 0, "cohorts": []})
            g["eligible"] += int(n)
            g["retained"] += int(k)
            g["cohorts"].append(row["cohort"])
        for period, g in groups.items():
            g["rate"] = g["retained"] / g["eligible"]
        cohort_sets = {tuple(sorted(g["cohorts"])) for g in groups.values()}
        if len(cohort_sets) > 1:
            errors.append("Состав когорт различается; сравнение требует стандартизации")
        result = {"source_id": sid, "source_sha256": digest(data), "method": "sum(retained)/sum(eligible) по периоду",
                  "groups": groups, "quality_errors": errors, "valid": not errors,
                  "limits": "Ассоциация, не причинность; определение метрики и окно наблюдения проверяет агент", "at": now()}
        atomic(Path(root) / f"evidence/analysis-{sid}.json", result)
        if errors:
            question = "Исправить качество данных: " + "; ".join(errors)
            if question not in s["workflow"]["open_questions"]:
                s["workflow"]["open_questions"].append(question)
        outcome(s, "invalid" if errors else "done", "Качество данных не прошло проверку" if errors else "Хеш и качество данных проверены", result_valid=not errors)
        return result


def budget(root, amount=None, minutes=0):
    if amount is not None:
        number(amount, "Стоимость")
    number(minutes, "Время")
    with transaction(root, "budget", "Проверить и зарезервировать лимит", cost=amount) as s:
        b, cfg = s["budget"], s["config"]
        errors = config_errors(cfg) + budget_errors(b)
        if errors:
            raise Problem("; ".join(errors))
        reasons = []
        if amount is None:
            reasons.append("Стоимость неизвестна; действие остановлено")
            b["unknown_cost_attempts"] += 1
        elif b["spent"] + amount > cfg.get("money_limit", 0):
            reasons.append("Денежный лимит исчерпан")
        if b["elapsed_minutes"] + b.get("reserved_minutes", 0) + minutes > cfg["time_budget_minutes"]:
            reasons.append("Лимит времени исчерпан")
        if reasons:
            s["workflow"]["stage"] = "budget_blocked"
            s["workflow"]["next_action"] = "Сузить вопрос, заменить метод или согласовать лимит с человеком"
        else:
            b["spent"] += amount
            b["reserved_minutes"] = b.get("reserved_minutes", 0) + minutes
        outcome(s, "blocked" if reasons else "done", "; ".join(reasons) if reasons else "Лимит зарезервирован; внешний вызов не выполнен", requested_minutes=minutes, actual_cost=0)
        return {"allowed": not reasons, "reasons": reasons, "budget": b}


def account_time(root, minutes, description, reference, entry_id):
    number(minutes, "Фактическое время", positive=True)
    for value in (description, reference, entry_id):
        text(value, "Учёт времени")
    with transaction(root, "account_time", description, [reference]) as s:
        b = s["budget"]
        entries = b.setdefault("time_entries", [])
        if any(e["id"] == entry_id for e in entries):
            raise Problem("Время с этим ID уже учтено")
        entries.append({"id": entry_id, "at": now(), "minutes": minutes, "description": description, "reference": reference})
        b["elapsed_minutes"] += minutes
        b["reserved_minutes"] = max(0, b.get("reserved_minutes", 0) - minutes)
        over = b["elapsed_minutes"] > s["config"]["time_budget_minutes"]
        if over:
            s["workflow"].update(stage="budget_blocked", next_action="Фактический лимит времени превышен; согласовать дальнейшую работу")
        outcome(s, "blocked" if over else "done", "Фактическое время записано; это не оценка денежных расходов", actual_minutes=minutes)
    return {"budget": b, "over_limit": over}


def history_check(root, s):
    errors, versions = [], []
    folder = Path(root) / "state/history"
    expected = {f"{r:06d}.json" for r in range(s["revision"])}
    actual = {p.name for p in folder.glob("*.json")}
    for name in sorted(expected - actual):
        errors.append("Отсутствует исторический снимок " + name)
    for path in sorted(folder.glob("*.json")):
        try:
            old = unwrap(path)
            if path.stem != f"{old['revision']:06d}" or old["revision"] >= s["revision"]:
                raise Problem("Номер исторического снимка не соответствует состоянию")
            issues = config_errors(old["config"]) + workflow_errors(old["workflow"]) + budget_errors(old["budget"])
            if issues:
                raise Problem("; ".join(issues))
            unavailable = []
            for sid, source in old["sources"].items():
                for key, hash_key in (("path", "sha256"), ("extracted", "extracted_sha256")):
                    try:
                        raw = safe_path(root, source[key]).read_bytes()
                        if digest(raw) != source[hash_key]:
                            unavailable.append(sid + ":" + key + ":hash")
                    except (OSError, KeyError, Problem):
                        unavailable.append(sid + ":" + key + ":missing")
            versions.append({"revision": old["revision"], "metadata_valid": True, "artifacts_restorable": not unavailable, "unavailable": unavailable})
        except (Problem, ValueError, KeyError, TypeError) as exc:
            errors.append(f"history/{path.name}: {exc}")
    cp = Path(root) / "state/checkpoint.json"
    if cp.exists():
        try:
            old = unwrap(cp)
            if old["revision"] > s["revision"]:
                raise Problem("Checkpoint из будущей ревизии")
        except (Problem, ValueError) as exc:
            errors.append("checkpoint: " + str(exc))
    return errors, versions


def validate(root, require_strategy=False):
    try:
        s = load(root)
    except (Problem, ValueError) as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": [], "revision": None, "history": []}
    errors = config_errors(s["config"]) + workflow_errors(s["workflow"]) + budget_errors(s["budget"])
    warnings = []
    for sid, source in s["sources"].items():
        try:
            checked_source(root, source)
            extracted = json.loads(safe_path(root, source["extracted"]).read_text())
            if digest(canonical(extracted)) != source["extracted_sha256"]:
                errors.append(f"{sid}: изменился хеш извлечённого материала")
            if extracted.get("injection_flags"):
                warnings.append(f"{sid}: подозрительные инструкции изолированы как данные")
            for rep in source.get("representations", []):
                for key, hash_key in (("path", "sha256"), ("extracted", "extracted_sha256")):
                    if digest(safe_path(root, rep[key]).read_bytes()) != rep[hash_key]:
                        errors.append(f"{sid}: повреждено представление {rep[key]}")
            if any(old not in s["sources"] or old == sid for old in predecessors(source)):
                errors.append(f"{sid}: некорректная связь замены")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{sid}: {exc}")
    for cid, c in s["claims"].items():
        try:
            for ref in c["references"]:
                check_reference(root, s, ref)
            if any(dep not in s["claims"] for dep in c["depends_on"] + c.get("counterevidence", [])):
                errors.append(f"{cid}: потерянная зависимость")
            elif c["status"] == "current" and claim_stale(s, c):
                errors.append(f"{cid}: актуальное утверждение опирается на заменённый источник или устаревшую связь")
        except (Problem, KeyError, TypeError, OSError) as exc:
            errors.append(f"{cid}: {exc}")
    for collection in ("decisions", "promises"):
        for rid, r in s[collection].items():
            try:
                record_check(root, s, collection, r)
            except (Problem, OSError, KeyError, TypeError) as exc:
                errors.append(f"{rid}: {exc}")
            if any(cid not in s["claims"] for cid in r["basis"]):
                errors.append(f"{rid}: потерянное основание")
            if r["status"] == "needs_review":
                warnings.append(f"{rid}: требует пересмотра")
            elif r["status"] not in ("rejected", "withdrawn", "refuted") and any(s["claims"].get(cid, {}).get("status") != "current" for cid in r["basis"]):
                errors.append(f"{rid}: актуальная запись имеет неактуальное основание")
    if require_strategy:
        errors.extend(strategy_errors(s["strategy"], s))
    st = s.get("strategy")
    if st and not strategy_errors(st, s):
        if st["status"] == "needs_review":
            warnings.append("strategy: требует пересмотра")
        elif strategy_stale(st, s):
            errors.append("strategy: неактуальные основания или обещания без needs_review")
    history_errors, versions = history_check(root, s)
    errors.extend(history_errors)
    if any(not v["artifacts_restorable"] for v in versions):
        warnings.append("Не все исторические версии восстановимы с доступными материалами; см. history")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "revision": s["revision"],
            "sources": len(s["sources"]), "claims": len(s["claims"]),
            "history": versions,
            "scope": "Структура, цитаты, хеши и ссылки; не экспертная оценка истинности и качества стратегии"}


def search(root, query=None, linked=None):
    s = load(root)
    results = []
    for cid, c in s["claims"].items():
        if (query and query.casefold() in (cid + ' ' + c["text"]).casefold()) or (linked and (linked in c["depends_on"] + c.get("counterevidence", []) or any(r["source_id"] == linked for r in c["references"]))):
            results.append({"kind": "claim", **c})
    if query:
        for sid, src in s["sources"].items():
            for chunk in json.loads(safe_path(root, src["extracted"]).read_text())["chunks"]:
                if query.casefold() in chunk["text"].casefold():
                    results.append({"kind": "source", "source_id": sid, **chunk})
    for collection in ("decisions", "promises"):
        for r in s[collection].values():
            searchable = {k: v for k, v in r.items() if k != "history"}
            if (query and query.casefold() in json.dumps(searchable, ensure_ascii=False).casefold()) or (linked and linked in r["basis"]):
                results.append({"kind": collection, **r})
    return results


def export(root):
    s = load(root)
    result = validate(root)
    if not result["valid"]:
        raise Problem("Экспорт остановлен: нарушена целостность")
    status_names = {"current":"актуально", "needs_review":"требует пересмотра", "refuted":"опровергнуто", "withdrawn":"отозвано", "proposed":"предложено", "simulated":"учебная симуляция", "confirmed":"подтверждено", "rejected":"отклонено"}
    type_names = {"fact":"факт источника", "hypothesis":"гипотеза", "inference":"аналитический вывод", "forecast":"прогноз", "unknown":"неизвестное"}
    stage_names = {"paused":"остановлено с контрольной точкой", "review_required":"нужен пересмотр", "research_plan":"план исследования", "brief":"постановка задачи", "budget_blocked":"бюджетная остановка"}
    lines = [f"# {s['config']['name']}", "", "Этап: " + stage_names.get(s["workflow"]["stage"], s["workflow"]["stage"]),
             "Следующее действие: " + s["workflow"]["next_action"], "", "## Утверждения"]
    for c in s["claims"].values():
        lines.append(f"- **{c['id']}** ({type_names[c['type']]}; {status_names[c['status']]}): {c['text']}")
    lines += ["", "## Решения и обещания"]
    for collection in ("decisions", "promises"):
        for r in s[collection].values():
            lines.append(f"- **{r['id']}**: {status_names[r['status']]}; основания: {', '.join(r['basis'])}")
            if collection == "decisions":
                lines.append(f"  Выбор: {r['decision']}; вариант {r['selected_option']}. Принимает решение: {r['decision_maker']}; владелец исполнения: {r['owner']}.")
    lines += ["", "## Открытые вопросы", *["- " + q for q in s["workflow"]["open_questions"]]]
    path = Path(root) / "outputs/memory.md"
    path.write_text("\n".join(lines) + "\n")
    atomic(Path(root) / "outputs/project-export.json", s)
    return {"output": str(path), "revision": s["revision"]}
