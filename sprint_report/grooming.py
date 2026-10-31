"""«Груминг»: весь объём эпиков команды из снимка PO-Sprint-observe → модель экрана для выравнивания Jira.

Отчёт спринта показывает эпики и истории спринта. Здесь — всё, что у команды в работе: каждый незакрытый эпик
доски (в том числе без задач в спринте), его истории с подзадачами, связями и кварталом исполнения, и подсказки,
где Jira расходится с реальностью (флаги ниже). Вход — команда observe: `epics[].scope` (объём эпиков спринта) и
`groom` (эпики вне спринта, карточки эпиков; сборщик 1.12.0+, `params.groom`). Без `groom` модель строится по
эпикам спринта, `hasGroom: false` — экран предупреждает, что видит не всё.

Только чтение: правки уходят из браузера заметками → ИИ-агент → Jira (poh-sprint-agent), здесь Jira не трогается.
"""
import datetime as dt
import re

from . import buckets

SCHEMA = 1
STALE_DAYS = 30                    # открытая история без правок столько дней — «не трогали»
WORK = ("progress", "review", "testing")
GROUPS = (("blocked", "В блоке"), ("work", "В работе"), ("open", "Открыто"), ("done", "Готово"))

# что подсвечиваем: код → (уровень, подпись). warn — расхождение с реальностью, info — на что взглянуть
FLAGS = {
    "no_assignee":      ("warn", "в работе без исполнителя"),
    "sprint_no_owner":  ("warn", "в спринте без исполнителя"),
    "no_quarter":       ("info", "без квартала"),
    "no_estimate":      ("info", "без оценки"),
    "stale":            ("warn", "давно не трогали"),
    "subtasks_done":    ("warn", "все подзадачи закрыты, история — нет"),
    "subtasks_open":    ("warn", "история закрыта, подзадачи — нет"),
    "blocker_closed":   ("warn", "блокер закрыт, а статус «в блоке»"),
    "blocked_no_link":  ("info", "в блоке без связи-блокера"),
    "waits_for":        ("info", "ждёт другую задачу"),
    "epic_all_done":    ("warn", "все истории закрыты — закрыть эпик?"),
    "epic_empty":       ("info", "в эпике нет историй"),
    "epic_overdue":     ("warn", "срок эпика прошёл"),
    "epic_no_owner":    ("info", "у эпика нет исполнителя"),
    "epic_no_quarter":  ("info", "у эпика нет квартала"),
    "epic_no_priority": ("info", "у эпика нет приоритета"),
}
_PRIO = [r"blocker|блокир", r"critical|критич|highest|наивысш", r"high|высок|major|важн", r"medium|normal|средн|обычн",
         r"low|низк|minor", r"lowest|trivial|наименьш|тривиал"]
DONE_CATEGORIES = ("выполнено", "готово", "done", "complete")
_QUARTER = re.compile(r"(20\d\d)\s*[-_/ ]?\s*Q([1-4])|Q([1-4])\s*[-_/ ]?\s*(20\d\d)", re.I)


def prio_rank(name):
    """Меньше — важнее: Blocker/Critical/Highest → High → Medium → Low → Lowest; без приоритета — в хвост."""
    low = str(name or "").lower()
    if not low:
        return 99
    for n, rx in enumerate(_PRIO):
        if re.search(rx, low):
            return n
    return 50


def quarter_of(text):
    """«Квартал» из любого текста: «2026Q4-S3», «Q4 2026», «2026 Q4» → «2026Q4»; нет — None."""
    m = _QUARTER.search(str(text or ""))
    if not m:
        return None
    year, q = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    return f"{year}Q{q}"


def _date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _bucket(status, category, smap):
    """Колонка статуса: правило команды из statusMap; нет — «готово» по категории Jira, иначе по имени."""
    if status in smap:
        return smap[status]
    if str(category or "").strip().lower() in DONE_CATEGORIES:
        return "done"
    return buckets.classify(status, None)


def _days(day, value):
    d = _date(value)
    return (day - d).days if d else None


def _group(bucket):
    return "done" if bucket == "done" else "blocked" if bucket == "blocked" else "work" if bucket in WORK else "open"


def _story(item, epic_key, day, smap, quarters):
    bucket = _bucket(item.get("status"), item.get("category"), smap)
    group = _group(bucket)
    subs = []
    for s in item.get("subtasks") or []:
        b = _bucket(s.get("status"), s.get("category"), smap)
        subs.append({"key": s["key"], "title": s.get("summary") or s.get("title") or "", "status": s.get("status"),
                     "bucket": b, "done": b == "done", "assignee": s.get("assignee") or ""})
    links = [{"type": ln.get("type") or "", "key": ln.get("key"), "status": ln.get("status")}
             for ln in item.get("links") or [] if ln.get("key")]
    quarter = item.get("quarter") or None
    story = {
        "key": item["key"], "title": (item.get("title") or "").strip(), "type": item.get("type") or "",
        "status": item.get("status") or "", "bucket": bucket, "group": group,
        "priority": item.get("priority") or "", "assignee": item.get("assignee") or "",
        "sprint": item.get("sprint") or "", "inSprint": bool(item.get("inSprint")),
        "quarter": quarter or "", "sp": item.get("sp"), "labels": item.get("labels") or [],
        "created": item.get("created"), "updated": item.get("updated"),
        "staleDays": _days(day, item.get("updated")), "subtasks": subs, "links": links, "epic": epic_key,
    }
    if quarter:
        quarters.add(quarter)
    story["flags"] = _story_flags(story, item, smap)
    return story


def _story_flags(s, item, smap):
    out = []
    open_ = s["group"] != "done"
    if open_ and s["bucket"] in WORK + ("blocked",) and not s["assignee"]:
        out.append("no_assignee")
    elif open_ and s["inSprint"] and not s["assignee"]:
        out.append("sprint_no_owner")
    if open_ and "quarter" in item and not s["quarter"]:
        out.append("no_quarter")
    if open_ and not s["sp"]:
        out.append("no_estimate")
    if open_ and s["staleDays"] is not None and s["staleDays"] >= STALE_DAYS:
        out.append("stale")
    subs = s["subtasks"]
    if subs and open_ and all(x["done"] for x in subs):
        out.append("subtasks_done")
    if subs and not open_ and not all(x["done"] for x in subs):
        out.append("subtasks_open")
    waits = [ln for ln in s["links"] if re.search(r"blocked by|заблокирован|зависит", ln["type"], re.I)]
    live = [ln for ln in waits if ln.get("status") and _bucket(ln["status"], None, smap) != "done"]
    if s["bucket"] == "blocked" and waits and not live:
        out.append("blocker_closed")
    elif s["bucket"] == "blocked" and not waits:
        out.append("blocked_no_link")
    if open_ and live:
        out.append("waits_for")
    return out


def _epic(key, title, card, scope, day, smap, quarters, in_sprint):
    stories = [_story(i, key, day, smap, quarters) for i in scope]
    count = {g: sum(1 for s in stories if s["group"] == g) for g, _ in GROUPS}
    total = len(stories)
    sp_total = sum(s["sp"] or 0 for s in stories)
    sp_done = sum(s["sp"] or 0 for s in stories if s["group"] == "done")
    e = {
        "key": key, "title": title, "status": card.get("status") or "", "priority": card.get("priority") or "",
        "assignee": card.get("assignee") or "", "due": card.get("due"), "quarter": card.get("quarter") or "",
        "labels": card.get("labels") or [], "updated": card.get("updated"), "inSprint": in_sprint,
        "counts": {**count, "total": total}, "pct": round(100 * count["done"] / total) if total else 0,
        "sp": {"done": sp_done, "total": sp_total}, "stories": stories,
    }
    if e["quarter"]:
        quarters.add(e["quarter"])
    flags = []
    if total and count["done"] == total:
        flags.append("epic_all_done")
    if not total:
        flags.append("epic_empty")
    due = _date(e["due"])
    if due and due < day and count["done"] < total:
        flags.append("epic_overdue")
    if "quarter" in card and not e["quarter"]:
        flags.append("epic_no_quarter")
    if not e["assignee"]:
        flags.append("epic_no_owner")
    if not e["priority"]:
        flags.append("epic_no_priority")
    e["flags"] = flags
    e["warn"] = sum(1 for f in flags if FLAGS[f][0] == "warn") + \
        sum(1 for s in stories for f in s["flags"] if FLAGS[f][0] == "warn")
    return e


def build(team, day):
    """Команда observe → модель экрана «Груминг» (JSON): эпики, истории, итоги, справочники для правок."""
    smap = dict(team.get("statusMap") or {})
    groom = team.get("groom")
    cards = (groom or {}).get("cards") or {}
    quarters, epics = set(), []
    sprint_epics = [e for e in team.get("epics") or [] if e.get("epicKey")]
    for src, in_sprint in [(e, True) for e in sprint_epics] + [(e, False) for e in (groom or {}).get("epics") or []]:
        key = src["epicKey"]
        card = {"priority": src.get("epicPriority"), "due": src.get("epicDue"), **(cards.get(key) or {})}
        card["priority"] = card.get("priority") or src.get("epicPriority")
        title = card.get("title") or src.get("epicTitle") or key
        epics.append(_epic(key, title, card, src.get("scope") or [], day, smap, quarters, in_sprint))
    if groom:                                              # закрытый эпик не показываем: он уже не в работе
        epics = [e for e in epics if _bucket(e["status"], cards.get(e["key"], {}).get("category"), smap) != "done"]
    epics.sort(key=lambda e: (not e["counts"]["total"] or e["counts"]["done"] == e["counts"]["total"],
                              prio_rank(e["priority"]), not e["inSprint"], e["key"]))
    stories = [s for e in epics for s in e["stories"]]
    open_ = [s for s in stories if s["group"] != "done"]
    flag_count = {}
    for e in epics:
        for f in e["flags"]:
            flag_count[f] = flag_count.get(f, 0) + 1
        for s in e["stories"]:
            for f in s["flags"]:
                flag_count[f] = flag_count.get(f, 0) + 1
    people = sorted({x for x in [e["assignee"] for e in epics] + [s["assignee"] for s in stories] if x})
    statuses = sorted({s["status"] for s in stories if s["status"]} | {e["status"] for e in epics if e["status"]}
                      | set(smap), key=lambda n: (buckets.BUCKETS.index(_bucket(n, None, smap)), n))
    prios = sorted({x for x in [e["priority"] for e in epics] + [s["priority"] for s in stories] if x}, key=prio_rank)
    meta = team.get("_meta") or {}
    return {
        "schema": SCHEMA, "team": {"slug": team["slug"], "name": team.get("team") or team["slug"].upper()},
        "day": day.isoformat(), "jira": (team.get("jiraBase") or "").rstrip("/"), "sprint": team.get("sprintName") or "",
        "collectedAt": meta.get("collectedAt") or "", "hasGroom": bool(groom),
        "quarterField": (groom or {}).get("quarterField"), "staleDays": STALE_DAYS,
        "groups": [{"id": g, "title": t} for g, t in GROUPS],
        "flags": {k: {"level": lvl, "text": text} for k, (lvl, text) in FLAGS.items()},
        "totals": {"epics": len(epics), "stories": len(stories), "open": len(open_),
                   "inSprint": sum(1 for s in open_ if s["inSprint"]),
                   "withWarn": sum(1 for e in epics if e["warn"]), "flags": flag_count},
        "lists": {"statuses": statuses, "priorities": prios, "people": people, "quarters": sorted(quarters)},
        "epics": epics,
    }
