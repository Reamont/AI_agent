"""Единая атомарная база проекта с CAS, журналом и контрольной суммой."""
import copy
import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone


class Problem(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with tmp.open("wb") as f:
            f.write(canonical(value))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def envelope(value):
    return {"sha256": digest(canonical(value)), "payload": value}


def unwrap(path):
    try:
        e = json.loads(Path(path).read_text())
        if digest(canonical(e["payload"])) != e["sha256"]:
            raise Problem("Контрольная сумма состояния не совпала")
        if e["payload"]["schema_version"] != 1:
            raise Problem("Неподдерживаемая версия схемы")
        return e["payload"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise Problem(f"Состояние недоступно или повреждено: {exc}") from exc


def load(root):
    return unwrap(Path(root) / "state/project.json")


def init(root, config):
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise Problem("Папка не пуста; существующие материалы не перезаписываются")
    if config.get("money_limit", 0) < 0 or config.get("time_budget_minutes", 60) <= 0:
        raise Problem("Некорректный бюджет")
    for folder in ["inputs", "sources", "evidence", "state", "outputs", "decisions", "logs"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    s = {"schema_version": 1, "revision": 0, "created_at": now(), "config": config,
         "sources": {}, "claims": {}, "decisions": {}, "promises": {}, "strategy": None,
         "budget": {"spent": 0, "elapsed_minutes": 0, "unknown_cost_attempts": 0},
         "workflow": {"stage": "brief", "completed": [], "open_questions": ["Какой выбор нужно сделать?"],
                      "pending": [], "human_decisions": [], "errors": [],
                      "next_action": "Уточнить вопрос решения; прочитать предоставленные материалы"},
         "events": []}
    atomic(root / "state/project.json", envelope(s))
    return s


@contextmanager
def transaction(root, action, purpose, inputs=None, expected_revision=None, cost=0):
    root = Path(root)
    lock = root / "state/write.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise Problem("Проект занят: write.lock. Проверьте процесс перед ручным удалением lock") from exc
    try:
        os.close(fd)
        s = load(root)
        if expected_revision is not None and s["revision"] != expected_revision:
            raise Problem("Конфликт версии: перечитайте состояние")
        before = copy.deepcopy(s)
        started = now()
        yield s
        s["revision"] += 1
        s["events"].append({"id": f"EV-{s['revision']:05d}", "at": started,
                            "finished_at": now(), "action": action, "purpose": purpose,
                            "inputs": inputs or [], "tool": "strategist 0.1.0 / Python",
                            "model": None, "cost": cost, "currency": s["config"].get("currency", "RUB"),
                            "status": "error" if action == "error" else "done", "verification": "Ошибка зафиксирована; действие не выполнено" if action == "error" else "Транзакция прошла проверки инструмента",
                            "next_action": s["workflow"]["next_action"]})
        # История до изменения позволяет восстановить прежние основания. Сначала история,
        # затем единственная точка commit; лишний снимок при сбое не означает commit.
        atomic(root / f"state/history/{before['revision']:06d}.json", envelope(before))
        atomic(root / "state/project.json", envelope(s))
    finally:
        lock.unlink(missing_ok=True)


def safe_path(root, relative):
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise Problem("Путь выходит за пределы проекта")
    return target


def checkpoint(root, next_action=None):
    with transaction(root, "checkpoint", "Сохранить точку остановки") as s:
        if next_action:
            s["workflow"]["next_action"] = next_action
        s["workflow"]["stage"] = "paused"
    s = load(root)
    atomic(Path(root) / "state/checkpoint.json", envelope(s))
    return {"revision": s["revision"], "next_action": s["workflow"]["next_action"]}
