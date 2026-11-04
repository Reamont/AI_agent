import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
from . import engine, ingest, package
from .store import Problem, load, init, checkpoint, transaction, unwrap, now, read_json
from .validation import obj, workflow_errors


def parser():
    p = argparse.ArgumentParser(description="Стратег Фабрики проектов: инструменты агента среды")
    p.add_argument("--project", "-p", default="projects/demo", help="Папка проекта")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Проверить Python и зависимости без сети")
    a = sub.add_parser("init", help="Создать проект в пустой папке")
    a.add_argument("--config", default="config.example.json")
    for cmd in ["status", "resume", "export", "impact"]:
        sub.add_parser(cmd)
    a = sub.add_parser("ingest", help="Импортировать документ/таблицу, без исполнения содержимого")
    a.add_argument("path")
    a.add_argument("--origin")
    a.add_argument("--rights", default="provided_for_project")
    a.add_argument("--supersedes")
    a.add_argument("--expected-revision", type=int)
    a = sub.add_parser("fetch", help="Прочитать разрешённую публичную HTTPS-страницу")
    a.add_argument("url")
    a.add_argument("--rights", default="reference_only")
    a.add_argument("--contains", help="Сохранить только фрагменты с этой подстрокой, сохраняя исходные локаторы")
    for cmd in ["claim", "decision", "promise", "strategy", "progress"]:
        a = sub.add_parser(cmd, help="Сохранить JSON-запись по контракту docs/tools.md")
        a.add_argument("file")
        a.add_argument("--expected-revision", type=int)
        if cmd in ("decision", "promise"):
            a.add_argument("--update", action="store_true", help="Обновить запись с сохранением ID и истории")
            a.add_argument("--reason", help="Обязательная причина обновления")
    a = sub.add_parser("analyze", help="Рассчитать удержание по CSV и проверить качество")
    a.add_argument("source_id")
    a = sub.add_parser("revise", help="Изменить статус утверждения и пересмотреть зависимости")
    a.add_argument("claim_id")
    a.add_argument("--status", choices=sorted(engine.STATUSES), required=True)
    a.add_argument("--reason", required=True)
    a.add_argument("--text")
    a = sub.add_parser("search", help="Поиск подстроки или прямых связей; не семантический поиск")
    a.add_argument("query", nargs="?")
    a.add_argument("--linked")
    a = sub.add_parser("checkpoint", help="Сохранить точку остановки")
    a.add_argument("--next")
    a = sub.add_parser("validate", help="Проверить целостность, цитаты и полноту")
    a.add_argument("--strategy", action="store_true")
    a = sub.add_parser("budget", help="Проверить/зарезервировать стоимость до действия")
    a.add_argument("--amount", type=float, help="Неизвестная стоимость блокируется")
    a.add_argument("--minutes", type=float, default=0)
    a = sub.add_parser("account-time", help="Записать фактическое время с основанием, отдельно от резерва")
    a.add_argument("--minutes", type=float, required=True)
    a.add_argument("--description", required=True)
    a.add_argument("--reference", required=True)
    a.add_argument("--id", required=True)
    sub.add_parser("audit", help="Проверить состав пакета на секреты/ПДн (эвристика)")
    a = sub.add_parser("pack", help="Упаковать каталог --root и проверить манифест")
    a.add_argument("--root", default=".")
    a.add_argument("--out", required=True)
    return p


def run(a):
    root, cmd = Path(a.project), a.command
    if cmd == "doctor":
        deps = {}
        for name in ["pypdf", "python-docx", "openpyxl"]:
            try:
                deps[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                deps[name] = "MISSING"
        return {"valid": sys.version_info >= (3, 12) and "MISSING" not in deps.values(),
                "python": sys.version.split()[0], "dependencies": deps, "network": "not tested (offline)",
                "llm": "LLM и её подписка нужны для нового исследования; CLI не вызывает модель"}
    if cmd == "init":
        return init(root, read_json(a.config))
    if cmd == "ingest":
        return ingest.ingest(root, a.path, a.origin, a.rights, a.supersedes, a.expected_revision)
    if cmd == "fetch":
        return ingest.fetch(root, a.url, a.rights, a.contains)
    if cmd == "claim":
        return engine.add_claim(root, read_json(a.file), a.expected_revision)
    if cmd in ("decision", "promise"):
        collection = {"decision": "decisions", "promise": "promises"}[cmd]
        if a.update:
            return engine.update_record(root, collection, read_json(a.file), a.reason, a.expected_revision)
        return engine.add_record(root, collection, read_json(a.file), a.expected_revision)
    if cmd == "strategy":
        return engine.set_strategy(root, read_json(a.file), a.expected_revision)
    if cmd == "progress":
        update = read_json(a.file)
        obj(update, "progress")
        with transaction(root, "progress", "Обновить ход исследования", expected_revision=a.expected_revision) as s:
            if set(update) - set(s["workflow"]):
                raise Problem("Неизвестное поле workflow")
            s["workflow"].update(update)
            errors = workflow_errors(s["workflow"])
            if errors:
                raise Problem("; ".join(errors))
        return load(root)["workflow"]
    if cmd == "analyze":
        return engine.analyze(root, a.source_id)
    if cmd == "revise":
        return engine.revise(root, a.claim_id, a.status, a.reason, a.text)
    if cmd == "search":
        return engine.search(root, a.query, a.linked)
    if cmd == "checkpoint":
        return checkpoint(root, a.next)
    if cmd == "validate":
        return engine.validate(root, a.strategy)
    if cmd == "budget":
        return engine.budget(root, a.amount, a.minutes)
    if cmd == "account-time":
        return engine.account_time(root, a.minutes, a.description, a.reference, a.id)
    if cmd == "export":
        return engine.export(root)
    if cmd == "audit":
        return package.audit(root)
    if cmd == "pack":
        return package.pack(a.root, a.out)
    s = load(root)
    if cmd == "impact":
        return {**{k: [r for r in s[k].values() if r["status"] == "needs_review"] for k in ("claims", "decisions", "promises")},
                "strategy": [s["strategy"]] if s.get("strategy", {}) and s["strategy"]["status"] == "needs_review" else []}
    if cmd == "resume":
        v = engine.validate(root)
        if not v["valid"]:
            raise Problem("Восстановление остановлено: " + "; ".join(v["errors"]))
        cp = root / "state/checkpoint.json"
        return {"revision": s["revision"], "checkpoint_revision": unwrap(cp)["revision"] if cp.exists() else None,
                "workflow": s["workflow"], "budget": s["budget"], "validation": v,
                "note": "Восстановлено из файлов; журнал и первоисточники доступны. Новое исследование не выполнялось."}
    if cmd == "status":
        return {"revision": s["revision"], "workflow": s["workflow"], "budget": s["budget"],
                "counts": {k: len(s[k]) for k in ("sources", "claims", "decisions", "promises")}}
    raise Problem("Неизвестная команда")


def main(argv=None):
    import logging
    # Библиотека может печатать фрагмент повреждённого PDF в warning. Контракт CLI
    # возвращает только безопасную JSON-ошибку; структурные warnings — в результате.
    logger = logging.getLogger("pypdf")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    a = parser().parse_args(argv)
    try:
        result = run(a)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and (result.get("valid") is False or result.get("allowed") is False):
            raise SystemExit(2)
    except Exception as exc:
        # Ошибки входных документов не должны раскрывать конфигурацию сети/секреты.
        msg = str(exc) if isinstance(exc, Problem) else f"Ошибка ввода, документа или инструмента ({type(exc).__name__})"
        if (Path(a.project) / "state/project.json").exists():
            try:
                with transaction(a.project, "error", "Зафиксировать неуспешный вызов", [a.command]) as s:
                    s["workflow"]["errors"].append({"at": now(), "tool": a.command, "message": msg, "status": "error"})
                    s["workflow"]["next_action"] = "Проверить ошибку инструмента; не выдумывать отсутствующий результат"
            except Exception:
                pass
        print(json.dumps({"error": msg, "status": "error"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
