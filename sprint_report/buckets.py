"""Раскладка статусов Jira по колонкам отчёта.

Колонки: open (не начато), progress (в работе), review (ревью), testing (отладка), blocked (в блоке), done (готово).
Основа — категория статуса Jira (new / indeterminate / done), уточнение — по имени статуса,
последнее слово — за командой: status_buckets в конфиге («у нас "Ожидает релиза" — это ревью»).
"""
import re

BUCKETS = ("open", "progress", "review", "testing", "blocked", "done")
ACTIVE = ("progress", "review", "testing")

# имя статуса → колонка; порядок важен: блок проверяется раньше ревью и отладки
_BY_NAME = [
    ("blocked", r"блок|block|on hold|hold|ожидани|ждём|ждем|wait|paused|пауз"),
    ("testing", r"тест|test|отладк|qa\b|приёмк|приемк|verif"),
    ("review", r"ревью|review|провер|code review|утвержд|approv"),
]
_CATEGORY = {"new": "open", "indeterminate": "progress", "done": "done"}


def classify(name, category, overrides=None):
    """Колонка статуса: правило команды → категория «готово» → имя → категория Jira."""
    overrides = {k.lower(): v for k, v in (overrides or {}).items()}
    key = str(name or "").strip().lower()
    if key in overrides:
        if overrides[key] not in BUCKETS:
            raise ValueError(f"status_buckets: «{name}» → «{overrides[key]}», допустимо: {', '.join(BUCKETS)}")
        return overrides[key]
    base = _CATEGORY.get(category, "open")
    if base == "done":
        return "done"
    for bucket, rx in _BY_NAME:
        if re.search(rx, key):
            return bucket
    return base
