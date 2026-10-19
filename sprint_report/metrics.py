"""Снимок команды → данные отчёта: модель дня (блоки, задачи в работе, готово за день, обещания)
и метрики спринта (сгорание, люди, эпики, сроки, поток, пульс, кандидаты на снятие).

Окно «за день»: прошлый рабочий день 00:00 → день отчёта 10:30. Дни «без движения» — рабочие.
Сгорание: объём — задачи, вошедшие в спринт к концу дня и не вышедшие из него; закрыто — вошедшие в «готово»
к концу дня (переоткрытие сбрасывает). В SP — по текущей оценке задачи, без подзадач; иначе — числом задач.
"""
import datetime as dt
import re

ACTIVE = ("progress", "review", "testing")
STALE_DAYS = 3
PULSE_DAYS = 10
ROLES = ("SA", "BE", "FE", "QA", "DEVOPS", "OPS", "DS")


# ---------- общее

def at(s):
    return dt.datetime.fromisoformat(str(s)[:16])


def prev_workday(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def workdays_between(a, b):
    """Рабочих дней после даты a до даты b включительно (сегодняшняя смена статуса — 0 дней)."""
    n, d = 0, a.date()
    while d < b.date():
        d += dt.timedelta(days=1)
        n += d.weekday() < 5
    return n


def clean(s):
    """Jira wiki → простой текст: картинки, ссылки, упоминания, разметка."""
    s = re.sub(r"![^!\s]+!", "🖼", s or "")
    s = re.sub(r"\[~?([^|\]]+)\|[^\]]+\]", r"\1", s)
    s = re.sub(r"\[~([^\]]+)\]", r"@\1", s)
    s = re.sub(r"\{(code|noformat|quote|color)[^}]*\}", "", s)
    s = re.sub(r"(^|\s)[*_]([^*_\n]+)[*_]", r"\1\2", s)
    return re.sub(r"\n{3,}", "\n\n", s.replace("\r", "")).strip()


def clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def short(name):
    p = str(name or "").split()
    return f"{p[0]} {p[1][0]}." if len(p) > 1 else (name or "")


def initials(name):
    p = str(name or "").split()
    return (p[0][0] + (p[1][0] if len(p) > 1 else "")).upper() if p else ""


def role(titles):
    """Роль по префиксу задач человека [SA]/[BE]/[FE]…"""
    seen = {}
    for t in titles:
        m = re.match(r"\s*\[([A-Za-z]+)\]", t)
        if m and m.group(1).upper() in ROLES:
            seen[m.group(1).upper()] = seen.get(m.group(1).upper(), 0) + 1
    return max(seen, key=seen.get) if seen else ""


class Snapshot:
    """Обёртка снимка: колонка статуса, время входа в «готово», статус на момент времени."""

    def __init__(self, snap):
        self.s = snap
        self.smap = {k.lower(): v for k, v in snap["statusBuckets"].items()}
        self.issues = snap["issues"]
        self.ref = at(snap["collectedAt"])          # момент снимка (локальное время отчёта)

    def bucket(self, status):
        return self.smap.get(str(status or "").lower(), "open")

    def done_at(self, i):
        """Когда задача вошла в «готово» в последний раз; переоткрытие сбрасывает. Не готова — None."""
        when = None
        for h in i["history"]:
            if self.bucket(h["to"]) == "done" and self.bucket(h["from"]) != "done":
                when = h["at"]
            elif self.bucket(h["to"]) != "done":
                when = None
        if i["bucket"] == "done" and when is None and not i["history"]:
            when = i["created"]
        return when if i["bucket"] == "done" else None

    def status_at(self, i, moment):
        """Колонка задачи на момент времени — по истории переходов."""
        past = [h for h in i["history"] if h["at"] <= moment]
        if past:
            return self.bucket(past[-1]["to"])
        return self.bucket(i["history"][0]["from"]) if i["history"] else i["bucket"]

    def since(self, i):
        """С какого момента задача в текущем статусе."""
        return at(i["history"][-1]["at"]) if i["history"] else at(i["created"])


# ---------- модель дня

def day_model(S, day, promises=()):
    team = S.s["team"]["name"]
    start = dt.datetime.combine(prev_workday(day), dt.time(0, 0))
    end = dt.datetime.combine(day, dt.time(10, 30))
    blockers, tasks, done = [], [], []
    for i in S.issues:
        if not i["assignee"] and i["bucket"] not in ("blocked",) + ACTIVE:
            continue
        days = workdays_between(S.since(i), end)
        who = short(i["assignee"]) if i["assignee"] else ""
        if i["bucket"] == "blocked":
            last = (i["comments"] or [None])[-1]
            blockers.append({"key": i["key"], "title": clip(i["title"], 90), "status": i["status"], "who": who, "team": team,
                             "days": days, "reason": clip(clean(last["body"]) if last else "", 160)})
        elif i["bucket"] in ACTIVE:
            tasks.append({"key": i["key"], "title": clip(i["title"], 90), "status": i["status"], "days": days,
                          "who": who, "team": team, "bucket": i["bucket"]})
        else:
            d_at = S.done_at(i)
            if d_at and start <= at(d_at) < end:
                done.append({"key": i["key"], "title": clip(i["title"], 90), "who": who, "team": team, "at": d_at})
    blockers.sort(key=lambda b: -b["days"])
    tasks.sort(key=lambda t: (t["who"], -(t["days"] or 0)))
    prom = [{"id": p.get("id") or f"P{n}", "side": p.get("side", "them"), "who": p.get("who", ""),
             "what": clip(p.get("what"), 110), "due": p.get("due"),
             "late": bool(p.get("due") and p["due"] < day.isoformat())}
            for n, p in enumerate(promises, 1) if not p.get("done")]
    prom.sort(key=lambda c: (c["due"] or "9999", c["id"]))
    return {"day": day.isoformat(), "meta": [{"team": team, "collectedAt": S.s["collectedAt"][:16],
                                               "sprint": S.s["sprint"]["name"], "jira": S.s["jira"]}],
            "blockers": blockers, "tasks": tasks, "promises": prom, "done": done}


# ---------- метрики спринта

def burndown(S, day):
    """По дням спринта до дня отчёта: объём, закрыто, осталось."""
    sp = S.s["unit"] == "SP"
    start, end = dt.date.fromisoformat(S.s["sprint"]["start"]), dt.date.fromisoformat(S.s["sprint"]["end"])
    rows = []
    for i in S.issues:
        if i["subtask"]:
            continue
        entered = i["entered"] or max(S.s["sprint"]["start"] + "T00:00", i["created"])
        rows.append((entered, i["left"], S.done_at(i), (i["sp"] or 0) if sp else 1))
    out, d = [], start
    while d <= min(end, day):
        eod = f"{d.isoformat()}T23:59"
        scope = closed = 0
        for entered, left, d_at, v in rows:
            if entered > eod or (left and left <= eod):
                continue
            scope += v
            closed += v if d_at and d_at <= eod else 0
        out.append({"date": d.isoformat(), "scope": round(scope, 1), "closed": round(closed, 1),
                    "remaining": round(scope - closed, 1)})
        d += dt.timedelta(days=1)
    return out


def people(S):
    by = {}
    for i in S.issues:
        if not i["assignee"]:
            continue
        p = by.setdefault(i["assignee"], {"split": {"done": 0, "work": 0, "blocked": 0, "open": 0}, "titles": []})
        b = i["bucket"]
        p["split"]["done" if b == "done" else "blocked" if b == "blocked" else "open" if b == "open" else "work"] += 1
        p["titles"].append(i["title"])
    return [{"name": n, "short": short(n), "initials": initials(n), "split": p["split"], "role": role(p["titles"])}
            for n, p in sorted(by.items())]


def epics(S):
    """Прогресс эпиков задач спринта: готово, в работе, в блоке; изменение за 1, 3 и 14 дней; истории спринта."""
    ref = S.ref.date()
    out = []
    for e in S.s["epics"]:
        xs = [x for x in e["children"] if (x.get("created") or "") <= ref.isoformat()]
        if not xs:
            continue
        done_by = lambda cut: sum(1 for x in xs if x["doneAt"] and x["doneAt"] <= cut)   # noqa: E731
        cats = {k: sum(1 for x in xs if x["category"] == k) for k in ("done", "work", "todo")}
        sprint = [x for x in xs if x["inSprint"]]
        row = {"key": e["key"], "title": clip(re.sub(r"^(\s*(\[[^\]]+\]|\d{2}Q\d)\s*)+", "", e["title"]), 90),
               "total": len(xs), "done": done_by(ref.isoformat()), "work": cats["work"], "cats": cats,
               "pct": round(done_by(ref.isoformat()) / len(xs) * 100),
               "sprint": {k: sum(1 for x in sprint if x["category"] == k) for k in ("done", "work", "todo")},
               "blocked": sum(1 for x in xs if x["bucket"] == "blocked" and x["category"] != "done")}
        for label, back in (("d1", 1), ("d3", 3), ("d14", 14)):
            cut = (ref - dt.timedelta(days=back)).isoformat()
            before = sum(1 for x in xs if x["doneAt"] and x["doneAt"] <= cut and (x.get("created") or "") <= cut)
            total_before = sum(1 for x in xs if (x.get("created") or "") <= cut) or len(xs)
            row[label] = row["pct"] - round(before / total_before * 100)
            row[label + "n"] = row["done"] - before
        out.append(row)
    return out


def roadmap(S):
    out = []
    for e in S.s["epics"]:
        xs = e["children"]
        owners = {}
        for x in xs:
            if x["assignee"] and x["category"] != "done":
                owners[x["assignee"]] = owners.get(x["assignee"], 0) + 1
        out.append({"key": e["key"], "title": clip(re.sub(r"^(\s*(\[[^\]]+\]|\d{2}Q\d)\s*)+", "", e["title"]), 90),
                    "due": e["due"], "cats": {k: sum(1 for x in xs if x["category"] == k) for k in ("done", "work", "todo")},
                    "insprint": sum(1 for x in xs if x["inSprint"]),
                    "owner": short(max(owners, key=owners.get)) if owners else ""})
    return out


FLOW = {"work": "progress", "review": "review", "testing": "testing", "done": "done"}


def flow(S):
    """Переходы за сутки и за 2–3 сутки до снимка: {вид: [за сутки, за 2–3 сутки]}. Задача — один раз на вид,
    по последнему переходу; «work» — из «не начато» в работу."""
    out = {k: [0, 0] for k in FLOW}
    for i in S.issues:
        last = {}
        for h in i["history"]:
            fb, tb = S.bucket(h["from"]), S.bucket(h["to"])
            for kind, target in FLOW.items():
                hit = (fb == "open" and tb == target) if kind == "work" else (tb == target and fb != target)
                if hit:
                    last[kind] = max(last.get(kind, ""), h["at"])
        for kind, when in last.items():
            age = S.ref - at(when)
            if dt.timedelta(0) <= age <= dt.timedelta(hours=24):
                out[kind][0] += 1
            elif dt.timedelta(hours=24) < age <= dt.timedelta(hours=72):
                out[kind][1] += 1
    return out


def pulse(S, n=PULSE_DAYS):
    """По рабочим дням до снимка: закрыто задач за день и задач в работе / ревью / отладке / блоке на конец дня."""
    days, x = [], S.ref.date()
    while len(days) < n:
        if x.weekday() < 5:
            days.insert(0, x)
        x -= dt.timedelta(days=1)
    items = [i for i in S.issues if not i["subtask"]]
    done, wip = [], []
    for day in days:
        eod = f"{day.isoformat()}T23:59"
        done.append(sum(1 for i in items if (S.done_at(i) or "")[:10] == day.isoformat()))
        wip.append(sum(1 for i in items if S.status_at(i, eod) in ACTIVE + ("blocked",)))
    return {"days": [d.isoformat() for d in days], "done": done, "wip": wip}


def sprint_ops(S, day):
    top = [i for i in S.issues if not i["subtask"]]
    opened = [i for i in top if i["bucket"] == "open"]
    return {
        "team": S.s["team"]["name"], "slug": S.s["team"]["slug"], "sprint": S.s["sprint"]["name"],
        "start": S.s["sprint"]["start"], "end": S.s["sprint"]["end"], "unit": S.s["unit"],
        "burn": burndown(S, day), "people": people(S), "epics": epics(S), "roadmap": roadmap(S),
        "flow": flow(S), "pulse": pulse(S),
        "not_started": len(opened),
        "not_started_items": sorted([{"key": i["key"], "title": clip(i["title"], 100), "sp": i["sp"] or 0,
                                      "who": short(i["assignee"])} for i in opened], key=lambda x: -x["sp"])[:40],
        "open_items": [{"key": i["key"], "sp": i["sp"] or 0} for i in top if i["bucket"] != "done"],
    }


def build(snapshots, day, promises=None):
    """Снимки команд → (model, ops) для render. promises — {slug: [обещания]}, необязательно."""
    model = {"day": day.isoformat(), "meta": [], "blockers": [], "tasks": [], "promises": [], "done": []}
    ops = {"day": day.isoformat(), "teams": []}
    for snap in snapshots:
        S = Snapshot(snap)
        m = day_model(S, day, (promises or {}).get(snap["team"]["slug"], ()))
        for k in ("meta", "blockers", "tasks", "promises", "done"):
            model[k] += m[k]
        ops["teams"].append(sprint_ops(S, day))
    return model, ops
