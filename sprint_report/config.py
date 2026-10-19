"""Конфиг (JSON) и секреты. Пример со всеми полями — config.example.json, описание — README.

Секрет берётся из переменной окружения (token_env) или файла (token_file): одна строка с токеном
либо строки KEY=VALUE — тогда значение ключа token_env. Сам токен нигде не печатается и не пишется.
"""
import datetime as dt
import json
import os
import re
from pathlib import Path


def load(path):
    cfg = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    cfg["_dir"] = str(Path(path).expanduser().resolve().parent)
    if not cfg.get("teams"):
        raise ValueError("в конфиге нет teams: [{slug, name, board}]")
    for t in cfg["teams"]:
        for k in ("slug", "board"):
            if k not in t:
                raise ValueError(f"команда {t}: нет поля {k}")
    return cfg


def tz(cfg):
    """Часовой пояс отчёта: «+03:00» (по умолчанию — МСК)."""
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", str(cfg.get("timezone", "+03:00")))
    if not m:
        raise ValueError("timezone — в виде «+03:00»")
    sign = 1 if m.group(1) == "+" else -1
    return dt.timezone(sign * dt.timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


def path(cfg, value, default):
    p = Path(os.path.expanduser(value or default))
    return p if p.is_absolute() else Path(cfg.get("_dir", ".")) / p


def read_secret(section, default_env):
    """Токен из окружения или файла; нет — None."""
    name = section.get("token_env") or default_env
    if os.environ.get(name):
        return os.environ[name].strip()
    f = section.get("token_file")
    if not f:
        return None
    text = Path(os.path.expanduser(f)).read_text(encoding="utf-8")
    pairs = dict(l.split("=", 1) for l in text.splitlines() if "=" in l and not l.lstrip().startswith("#"))
    pairs = {k.strip(): v.strip().strip("'\"") for k, v in pairs.items()}
    if pairs:
        for key in (name, "JIRA_TOKEN", "JIRA_PERSONAL_TOKEN", "MATRIX_TOKEN"):
            if pairs.get(key):
                return pairs[key]
        return None
    return text.strip() or None
