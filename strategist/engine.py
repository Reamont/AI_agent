import copy
import csv
import json
import math
import re
from pathlib import Path
from .store import Problem, load, transaction, safe_path, now, digest, canonical, atomic
from .ingest import invalidate

TYPES = {"fact", "hypothesis", "inference", "forecast", "unknown"}
STATUSES = {"current", "needs_review", "refuted", "withdrawn"}


def check_reference(root, s, ref):
    source = s["sources"].get(ref.get("source_id"))
    if not source:
        raise Problem("Источник утверждения не найден")
    extracted = json.loads(safe_path(root, source["extracted"]).read_text())
    if digest(canonical(extracted)) != source["extracted_sha256"]:
        raise Problem("Изменился хеш извлечённого материала")
    matches = [c for c in extracted["chunks"] if c["locator"] == ref.get("locator")]
    if not matches or not ref.get("quote") or ref["quote"] not in matches[0]["text"]:
        raise Problem("Локатор или цитата не совпадают с извлечённым источником")


def add_claim(root, c, expected_revision=None):
    c = copy.deepcopy(c)
    with transaction(root, "claim", "Сохранить проверяемое утверждение", [c.get("id")], expected_revision) as s:
        required = ["id", "text", "type", "scope", "period", "confidence", "limitations", "review_if"]
        if any(k not in c or c[k] is None for k in required):
            raise Problem("У утверждения не заполнены обязательные поля")
        if c["type"] not in TYPES or c["id"] in s["claims"]:
            raise Problem("Некорректный тип или повтор ID")
        if not isinstance(c["confidence"], dict) or not c["confidence"].get("reason"):
            raise Problem("Нужна уверенность с объяснением")
        c.setdefault("references", [])
        c.setdefault("depends_on", [])
        c.setdefault("counterevidence", [])
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
        if any(s["claims"][cid]["status"] != "current" for cid in c["depends_on"]):
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
        c["history"].append({"at": now(), "before": copy.deepcopy({k: v for k, v in c.items() if k != 'history'}), "reason": reason})
        c["status"] = status
        if text:
            c["text"] = text
            # Переписанный факт должен заново пройти проверку источника агентом.
            if status == "current":
                c["status"] = "needs_review"
        c["version"] += 1
        result = invalidate(s, claim_ids=[cid])
        c["status"] = status if not text else c["status"]
    return result


def add_record(root, collection, record):
    record = copy.deepcopy(record)
    with transaction(root, collection, "Сохранить решение или обещание", [record.get("id")]) as s:
        if not record.get("id") or record["id"] in s[collection]:
            raise Problem("Отсутствует или повторяется ID")
        if not record.get("basis") or any(c not in s["claims"] for c in record["basis"]):
            raise Problem("Нужны существующие основания")
        if collection == "decisions":
            for field in ["status", "owner", "alternatives", "assumptions", "actions", "metrics", "deadline", "review_if"]:
                if field not in record:
                    raise Problem(f"У решения отсутствует {field}")
            if record["status"] not in ["proposed", "simulated", "confirmed", "rejected"]:
                raise Problem("Недопустимый статус решения")
            if record["status"] == "confirmed" and not record.get("human_confirmation"):
                raise Problem("Нет ссылки на подтверждение человека")
        else:
            for field in ["message", "capability", "available", "limitation", "allowed_wording"]:
                if field not in record:
                    raise Problem(f"У обещания отсутствует {field}")
            record["status"] = "current"
            if record["available"] and any(s["claims"][c]["type"] != "fact" for c in record["basis"]):
                raise Problem("Доступность обещания нельзя подтверждать гипотезой")
            if not record["available"] and not record.get("future_label"):
                raise Problem("Будущая возможность должна быть явно помечена")
        if any(s["claims"][c]["status"] != "current" for c in record["basis"]):
            record["status"] = "needs_review"
        record.update(created_at=now(), history=[])
        s[collection][record["id"]] = record
    return record


def set_strategy(root, strategy):
    errors = strategy_errors(strategy, load(root))
    if errors:
        raise Problem("; ".join(errors))
    with transaction(root, "strategy", "Сохранить две согласованные стратегии") as s:
        s["strategy"] = {**strategy, "status": "proposed", "saved_at": now()}
    return strategy


def strategy_errors(st, s):
    errors = []
    if not isinstance(st, dict):
        return ["Стратегия отсутствует"]
    options = st.get("options", [])
    if not {"status_quo", "improve", "pivot", "close"} <= {o.get("kind") for o in options}:
        errors.append("Нужны четыре разных типа вариантов")
    fields = ["id", "audience", "job", "value", "difference", "changes", "economics", "communication", "cost", "timing", "dependencies", "risks", "reversibility", "objection", "falsifier", "viability", "test"]
    for o in options:
        if any(not o.get(f) for f in fields):
            errors.append(f"Вариант {o.get('id')} неполон")
    for section, fields in {
        "product": ["segment", "job", "context", "alternatives", "direction", "difference", "non_goals", "boundaries", "capabilities", "economics", "assumptions", "sequence"],
        "communication": ["audience", "situation", "barrier", "positioning", "message", "proof", "channels", "cta", "limits", "comprehension_test"],
        "experiment": ["id", "hypothesis", "change", "metric", "baseline", "control", "unit", "sample", "duration", "business_effect", "success", "failure", "inconclusive", "guardrails", "owner", "action"]
    }.items():
        if any(not st.get(section, {}).get(f) for f in fields):
            errors.append(f"Неполный раздел {section}")
    if not st.get("comparison") or not st.get("sensitivity") or not st.get("recommendation"):
        errors.append("Нет сравнения, чувствительности или рекомендации")
    if not st.get("basis") or any(cid not in s["claims"] for cid in st.get("basis", [])):
        errors.append("У стратегии нет существующих оснований")
    if not st.get("promise_ids") or any(pid not in s["promises"] for pid in st.get("promise_ids", [])):
        errors.append("Не найдены проверяемые обещания")
    return errors


def analyze(root, sid):
    s = load(root)
    source = s["sources"].get(sid)
    if not source or not source["path"].endswith(".csv"):
        raise Problem("Для расчёта нужен импортированный CSV")
    with safe_path(root, source["path"]).open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
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
    result = {"source_id": sid, "source_sha256": source["sha256"], "method": "sum(retained)/sum(eligible) по периоду",
              "groups": groups, "quality_errors": errors, "valid": not errors,
              "limits": "Ассоциация, не причинность; определение метрики и окно наблюдения проверяет агент", "at": now()}
    with transaction(root, "analyze", "Проверить качество и воспроизвести расчёт", [sid]) as state:
        atomic(Path(root) / f"evidence/analysis-{sid}.json", result)
        if errors:
            question = "Исправить качество данных: " + "; ".join(errors)
            if question not in state["workflow"]["open_questions"]:
                state["workflow"]["open_questions"].append(question)
    return result


def budget(root, amount=None, minutes=0):
    if amount is not None and (not math.isfinite(amount) or amount < 0):
        raise Problem("Стоимость должна быть конечной и неотрицательной")
    if not math.isfinite(minutes) or minutes < 0:
        raise Problem("Время должно быть конечным и неотрицательным")
    with transaction(root, "budget", "Проверить и зарезервировать лимит", cost=amount) as s:
        b, cfg = s["budget"], s["config"]
        reasons = []
        if amount is None:
            reasons.append("Стоимость неизвестна; действие остановлено")
            b["unknown_cost_attempts"] += 1
        elif b["spent"] + amount > cfg.get("money_limit", 0):
            reasons.append("Денежный лимит исчерпан")
        if b["elapsed_minutes"] + minutes > cfg.get("time_budget_minutes", 60):
            reasons.append("Лимит времени исчерпан")
        if reasons:
            s["workflow"]["stage"] = "budget_blocked"
            s["workflow"]["next_action"] = "Сузить вопрос, заменить метод или согласовать лимит с человеком"
        else:
            b["spent"] += amount
            b["elapsed_minutes"] += minutes
        return {"allowed": not reasons, "reasons": reasons, "budget": b}


def validate(root, require_strategy=False):
    s = load(root)
    errors, warnings = [], []
    for sid, source in s["sources"].items():
        try:
            if digest(safe_path(root, source["path"]).read_bytes()) != source["sha256"]:
                errors.append(f"{sid}: изменился хеш оригинала")
            extracted = json.loads(safe_path(root, source["extracted"]).read_text())
            if digest(canonical(extracted)) != source["extracted_sha256"]:
                errors.append(f"{sid}: изменился хеш извлечённого материала")
            if extracted.get("injection_flags"):
                warnings.append(f"{sid}: подозрительные инструкции изолированы как данные")
        except (OSError, ValueError) as exc:
            errors.append(f"{sid}: {exc}")
    for cid, c in s["claims"].items():
        try:
            for ref in c["references"]:
                check_reference(root, s, ref)
            if any(dep not in s["claims"] for dep in c["depends_on"]):
                errors.append(f"{cid}: потерянная зависимость")
            if c["status"] == "current" and any(s["claims"][dep]["status"] != "current" for dep in c["depends_on"]):
                errors.append(f"{cid}: актуальный вывод опирается на устаревший")
        except Problem as exc:
            errors.append(f"{cid}: {exc}")
    for collection in ("decisions", "promises"):
        for rid, r in s[collection].items():
            if any(cid not in s["claims"] for cid in r["basis"]):
                errors.append(f"{rid}: потерянное основание")
            if r["status"] == "needs_review":
                warnings.append(f"{rid}: требует пересмотра")
    if require_strategy:
        errors.extend(strategy_errors(s["strategy"], s))
    return {"valid": not errors, "errors": errors, "warnings": warnings, "revision": s["revision"],
            "sources": len(s["sources"]), "claims": len(s["claims"]),
            "scope": "Структура, цитаты, хеши и ссылки; не экспертная оценка истинности и качества стратегии"}


def search(root, query=None, linked=None):
    s = load(root)
    results = []
    for cid, c in s["claims"].items():
        if (query and query.casefold() in c["text"].casefold()) or (linked and (linked in c["depends_on"] or any(r["source_id"] == linked for r in c["references"]))):
            results.append({"kind": "claim", **c})
    if query:
        for sid, src in s["sources"].items():
            for chunk in json.loads(safe_path(root, src["extracted"]).read_text())["chunks"]:
                if query.casefold() in chunk["text"].casefold():
                    results.append({"kind": "source", "source_id": sid, **chunk})
    if linked:
        for collection in ("decisions", "promises"):
            for r in s[collection].values():
                if linked in r["basis"]:
                    results.append({"kind": collection, **r})
    return results


def export(root):
    s = load(root)
    result = validate(root)
    if not result["valid"]:
        raise Problem("Экспорт остановлен: нарушена целостность")
    lines = [f"# {s['config']['name']}", "", "Статус: " + s["workflow"]["stage"],
             "Следующее действие: " + s["workflow"]["next_action"], "", "## Утверждения"]
    for c in s["claims"].values():
        lines.append(f"- **{c['id']}** ({c['type']}; {c['status']}): {c['text']}")
    lines += ["", "## Решения и обещания"]
    for collection in ("decisions", "promises"):
        for r in s[collection].values():
            lines.append(f"- **{r['id']}**: {r['status']}; основания: {', '.join(r['basis'])}")
    lines += ["", "## Открытые вопросы", *["- " + q for q in s["workflow"]["open_questions"]]]
    path = Path(root) / "outputs/memory.md"
    path.write_text("\n".join(lines) + "\n")
    atomic(Path(root) / "outputs/project-export.json", s)
    return {"output": str(path), "revision": s["revision"]}
