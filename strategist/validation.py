"""Контракты входов: не допускают truthy-подмены типов и NaN/Infinity."""
import math
from .store_errors import Problem


def obj(value, label):
    if not isinstance(value, dict):
        raise Problem(f"{label}: требуется JSON-объект")
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise Problem(f"{label}: требуется непустая строка")
    return value


def number(value, label, minimum=0, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum or (positive and value == 0):
        raise Problem(f"{label}: требуется конечное число в допустимом диапазоне")
    return value


def strings(value, label, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise Problem(f"{label}: требуется список строк")
    for item in value:
        text(item, label)
    return value


def config_errors(cfg):
    try:
        obj(cfg, "config")
        for key in ("name", "currency"):
            text(cfg.get(key), key)
        for key in ("goal", "recipient", "decision_maker", "data_policy"):
            if key in cfg:
                text(cfg[key], key)
        number(cfg.get("money_limit"), "money_limit")
        number(cfg.get("time_budget_minutes"), "time_budget_minutes", positive=True)
        strings(cfg.get("allowed_domains"), "allowed_domains")
        import re
        for domain in cfg["allowed_domains"]:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", domain):
                raise Problem("allowed_domains: нужен hostname без схемы/пути/порта")
        if "max_source_bytes" in cfg and (type(cfg["max_source_bytes"]) is not int or not 0 < cfg["max_source_bytes"] <= 128 * 1024 * 1024):
            raise Problem("max_source_bytes: целое число 1..128 MB")
        if "models" in cfg:
            strings(cfg["models"], "models")
        if "external_processing_allowed" in cfg and type(cfg["external_processing_allowed"]) is not bool:
            raise Problem("external_processing_allowed: требуется boolean")
        if cfg.get("deadline") is not None:
            text(cfg["deadline"], "deadline")
    except Problem as exc:
        return [str(exc)]
    return []


PENDING = {"not_started", "in_progress", "done", "error", "unknown", "blocked"}
WORKFLOW = {"stage", "completed", "open_questions", "pending", "human_decisions", "errors", "next_action"}


def workflow_errors(w):
    try:
        obj(w, "workflow")
        if set(w) != WORKFLOW:
            raise Problem("workflow: отсутствуют обязательные или присутствуют неизвестные поля")
        for field in ("stage", "next_action"):
            text(w.get(field), field)
        for field in ("completed", "open_questions"):
            strings(w.get(field), field)
        for field in ("pending", "errors", "human_decisions"):
            if not isinstance(w.get(field), list):
                raise Problem(f"{field}: требуется список объектов")
            for record in w[field]:
                obj(record, field)
                if "status" in record and record["status"] not in PENDING | {"proposed", "simulated", "confirmed", "rejected", "needs_review"}:
                    raise Problem(f"{field}: недопустимый статус")
                if field == "pending":
                    text(record.get("id"), "pending.id")
                    if record.get("status") not in PENDING:
                        raise Problem("pending.status: недопустимый статус")
    except Problem as exc:
        return [str(exc)]
    return []


def budget_errors(b):
    try:
        obj(b, "budget")
        for key in ("spent", "elapsed_minutes", "unknown_cost_attempts"):
            number(b.get(key), "budget." + key)
        for key in ("reserved_minutes",):
            number(b.get(key, 0), "budget." + key)
    except Problem as exc:
        return [str(exc)]
    return []
