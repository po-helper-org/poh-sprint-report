"""Снимок PO-Sprint-observe (sprint-report.data.json runner'а actual-sprint) → снимок этого отчёта.

Так дейлик строится на тех же данных, что отчёт техлида и бизнес-колода: без своего похода в Jira,
сразу после «Актуализировать». Вход — список команд observe: slug, team, sprintName, jiraBase, boardId,
statusMap, burndown{start,end,items[{key,entered,left,subtask}]}, epics[{epicKey,epicTitle,epicDue,
scope[…], stories[{key,title,status,assignee,events[{at,kind,from,to,by,body}]}]}], _meta.collectedAt.

Упрощения: оценки в SP в снимке observe нет — сгорание числом задач; подзадачи не берутся;
«вошла в спринт» — дата без времени (00:00).
"""
import re

from . import buckets

SCHEMA = 1
CATEGORY = {"done": "done", "open": "todo"}          # остальные колонки — «в работе»


def _ts(value):
    """Дата или время observe → «ГГГГ-ММ-ДДTЧЧ:ММ» (как у сборщика этого отчёта)."""
    if not value:
        return None
    s = str(value)
    return s[:16] if len(s) > 10 else s[:10] + "T00:00"


def team_snapshot(t):
    """Одна команда observe → снимок отчёта (schema 1)."""
    smap = dict(t.get("statusMap") or {})

    def bucket(status, category=None):
        return smap.get(status) or buckets.classify(status, category)

    bd = t.get("burndown") or {}
    stories, scope = {}, {}
    for e in t.get("epics") or []:
        for s in e.get("stories") or []:
            stories[s["key"]] = (s, e.get("epicKey"))
        for x in e.get("scope") or []:
            scope[x["key"]] = x
    issues = []
    for it in bd.get("items") or []:
        if it.get("subtask"):
            continue
        s, epic = stories.get(it["key"], ({}, None))
        x = scope.get(it["key"], {})
        events = sorted(s.get("events") or [], key=lambda v: v.get("at") or "")
        status = s.get("status") or x.get("status") or ""
        created = next((v["at"] for v in events if v.get("kind") == "created"), None) or x.get("created") or it.get("entered")
        issues.append({
            "key": it["key"], "title": (s.get("title") or it.get("title") or x.get("title") or "").strip(),
            "type": x.get("type", ""), "subtask": False, "status": status, "bucket": bucket(status, x.get("category")),
            "assignee": s.get("assignee") or x.get("assignee") or "",
            "sp": x.get("sp") if isinstance(x.get("sp"), (int, float)) else 0, "epic": epic,
            "created": _ts(created), "entered": _ts(it.get("entered")), "left": _ts(it.get("left")),
            "history": [{"at": _ts(v["at"]), "from": v.get("from"), "to": v.get("to"), "by": v.get("by")}
                        for v in events if v.get("kind") == "status"],
            "comments": [{"at": _ts(v["at"]), "by": v.get("by"), "body": (v.get("body") or "")[:400]}
                         for v in events if v.get("kind") == "comment"][-5:],
        })
    in_sprint = {i["key"] for i in issues}
    epics = []
    for e in t.get("epics") or []:
        if not e.get("epicKey"):
            continue
        children = []
        for x in e.get("scope") or []:
            b = bucket(x.get("status"), x.get("category"))
            children.append({"key": x["key"], "status": x.get("status"), "category": CATEGORY.get(b, "work"),
                             "bucket": b, "assignee": x.get("assignee") or "", "created": (x.get("created") or "")[:10],
                             "doneAt": ((x.get("doneAt") or "")[:10] or None) if b == "done" else None,
                             "inSprint": x["key"] in in_sprint})
        epics.append({"key": e["epicKey"], "title": (e.get("epicTitle") or "").strip(),
                      "due": (e.get("epicDue") or "")[:10] or None, "children": children})
    meta = t.get("_meta") or {}
    return {
        "schema": SCHEMA, "team": {"slug": t["slug"], "name": t.get("team") or t["slug"].upper()},
        "jira": (t.get("jiraBase") or "").rstrip("/"), "board": t.get("boardId"),
        "collectedAt": meta.get("collectedAt") or "", "unit": "задач", "statusBuckets": smap,
        "sprint": {"id": None, "name": t.get("sprintName") or bd.get("sprintName") or "",
                   "start": (bd.get("start") or "")[:10], "end": (bd.get("end") or "")[:10]},
        "issues": issues, "epics": epics,
    }


def snapshots(data, team=None):
    """Все команды observe (или одна по slug) → снимки; команды без спринта пропускаются."""
    out = []
    for t in data or []:
        if team and t.get("slug") != team:
            continue
        bd = t.get("burndown") or {}
        if bd.get("start") and bd.get("end") and (t.get("_meta") or {}).get("collectedAt"):
            out.append(team_snapshot(t))
    return out


# Вид для экрана: листы A4 по центру на сером, высота — по содержимому (печать не меняется).
# Скриптов нет: страница встраивается под CSP «script-src 'self'», масштаб по ширине задаёт оболочка.
WEB_CSS = """<style media="screen">
html{background:#F2F2F5}body{padding:16px 0 24px}
.page{width:186mm;height:auto;min-height:0;margin:0 auto 16px;padding:12mm;background:#fff;box-sizing:content-box;
border-radius:14px;box-shadow:0 1px 2px rgba(0,0,0,.06)}.page .inner{min-height:0!important}
</style>"""
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)


def web(page):
    """HTML отчёта для печати → тот же отчёт для показа во вкладке «Блокаторы» (без скриптов)."""
    return _SCRIPT.sub("", page).replace("</head>", WEB_CSS + "</head>", 1)
