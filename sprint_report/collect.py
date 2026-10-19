"""Сбор снимка команды из Jira — один JSON, из которого отчёт считается без сети.

Что забирает (только GET):
  /rest/api/2/field, /rest/api/2/status        поля Story Points, «Ссылка на эпик», целевая дата эпика; категории статусов
  /rest/agile/1.0/board/{id}/sprint            активный спринт доски
  /rest/agile/1.0/sprint/{id}/issue            задачи спринта с историей (expand=changelog) и, вторым проходом, комментариями
  /rest/api/2/search                           эпики задач спринта и весь их объём (для прогресса эпиков и сроков)

Формат снимка — README, раздел «Снимок».
"""
import datetime as dt
import re

from . import buckets
from .jira import JiraError

SCHEMA = 1
SP_NAMES = ("story points", "story point estimate")
EPIC_NAMES = ("epic link", "ссылка на эпик")
DUE_NAMES = ("target end", "целевая дата окончания")
EPIC_TYPES = ("epic", "эпик")
_TZ = re.compile(r"([+-]\d{2})(\d{2})$")


def parse(ts):
    """ISO-время Jira («+0300» без двоеточия, «Z») → aware datetime."""
    text = str(ts).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    m = _TZ.search(text)
    if m and ":" not in text[m.start():]:
        text = text[:m.start()] + m.group(1) + ":" + m.group(2)
    return dt.datetime.fromisoformat(text)


class Collector:
    def __init__(self, jira, team, tz, now=None):
        self.jira, self.team, self.tz = jira, team, tz
        self.now = now or dt.datetime.now(tz)
        self.overrides = team.get("status_buckets") or {}
        self.include_subtasks = bool(team.get("subtasks", True))

    # ---------- справочники

    def local(self, ts):
        """Время Jira → «ГГГГ-ММ-ДДTЧЧ:ММ» в часовом поясе отчёта."""
        return parse(ts).astimezone(self.tz).isoformat()[:16] if ts else None

    def fields(self):
        """Поля по имени, если в конфиге не заданы явно: id Story Points, «Ссылки на эпик», целевой даты эпика."""
        want = {"sp": self.team.get("sp_field", "auto"), "epic": self.team.get("epic_link_field", "auto"),
                "due": self.team.get("epic_due_field", "auto")}
        if any(v == "auto" for v in want.values()):
            names = {f["name"].strip().lower(): f["id"] for f in self.jira.get("/rest/api/2/field")}
            pick = lambda variants: next((names[n] for n in variants if n in names), None)   # noqa: E731
            for k, variants in (("sp", SP_NAMES), ("epic", EPIC_NAMES), ("due", DUE_NAMES)):
                if want[k] == "auto":
                    want[k] = pick(variants)
        if not want["due"]:
            want["due"] = "duedate"
        return want

    def status_buckets(self):
        """Все статусы инстанса → колонка отчёта (по категории, имени и правилам команды)."""
        out = {}
        for s in self.jira.get("/rest/api/2/status"):
            cat = (s.get("statusCategory") or {}).get("key")
            out[s["name"]] = buckets.classify(s["name"], cat, self.overrides)
        return out

    def active_sprint(self):
        board = self.team["board"]
        sprints = [s for s in self.jira.values(f"/rest/agile/1.0/board/{board}/sprint", state="active")
                   if s.get("originBoardId") in (None, board)]
        if not sprints:
            raise JiraError(f"у доски {board} нет активного спринта")
        return max(sprints, key=lambda s: s.get("startDate") or "")

    # ---------- задачи спринта

    def issue(self, raw, comments, sprint, smap, f):
        fl = raw["fields"]
        itype = fl.get("issuetype") or {}
        hist, entered, left = [], None, None
        for h in sorted((raw.get("changelog") or {}).get("histories", []), key=lambda h: h["created"]):
            for it in h.get("items", []):
                field = str(it.get("field", "")).lower()
                if field == "status":
                    hist.append({"at": self.local(h["created"]), "from": it.get("fromString"), "to": it.get("toString"),
                                 "by": (h.get("author") or {}).get("displayName")})
                elif field == "sprint":
                    was = sprint["name"] in (it.get("fromString") or "")
                    now_in = sprint["name"] in (it.get("toString") or "")
                    if now_in and not was:
                        entered = self.local(h["created"])
                    if was and not now_in:
                        left = self.local(h["created"])
        parent = fl.get("parent") or {}
        parent_type = ((parent.get("fields") or {}).get("issuetype") or {}).get("name", "")
        epic = fl.get(f["epic"]) if f["epic"] else None
        if not epic and parent and parent_type.strip().lower() in EPIC_TYPES:
            epic = parent.get("key")   # Jira Cloud: эпик — родитель задачи
        sp = fl.get(f["sp"]) if f["sp"] else None
        status = fl["status"]["name"]
        cat = (fl["status"].get("statusCategory") or {}).get("key")
        return {
            "key": raw["key"], "title": (fl.get("summary") or "").strip(), "type": itype.get("name", ""),
            "subtask": bool(itype.get("subtask")), "status": status,
            "bucket": smap.get(status) or buckets.classify(status, cat, self.overrides),
            "assignee": (fl.get("assignee") or {}).get("displayName") or "",
            "sp": sp if isinstance(sp, (int, float)) else 0, "epic": epic if isinstance(epic, str) else None,
            "created": self.local(fl["created"]), "entered": entered, "left": left, "history": hist,
            "comments": [{"at": self.local(c["created"]), "by": (c.get("author") or {}).get("displayName"),
                          "body": (c.get("body") or "")[:400]} for c in comments.get(raw["key"], [])][-5:],
        }

    # ---------- эпики

    def epics(self, issues, smap, f):
        keys = sorted({i["epic"] for i in issues if i["epic"]})
        if not keys:
            return []
        due = f["due"]
        heads = self.jira.issues("/rest/api/2/search", jql=f"key in ({','.join(keys)})", fields=f"summary,status,{due}")
        if f["epic"] and f["epic"].startswith("customfield_"):
            jql = f"cf[{f['epic'].split('_', 1)[1]}] in ({','.join(keys)})"
            link = f["epic"]
        else:
            jql, link = f"parent in ({','.join(keys)})", "parent"
        limit = int(self.team.get("epic_scope_max", 2000))
        kids = self.jira.issues("/rest/api/2/search", jql=jql,
                                fields=f"summary,status,created,resolutiondate,assignee,issuetype,{link}")[:limit]
        in_sprint = {i["key"] for i in issues}
        cat_of = {"done": "done", "indeterminate": "work", "new": "todo"}
        by_epic = {k: [] for k in keys}
        for k in kids:
            fl = k["fields"]
            ref = fl.get(link)
            ref = ref.get("key") if isinstance(ref, dict) else ref
            if ref not in by_epic or (fl.get("issuetype") or {}).get("subtask"):
                continue
            cat = cat_of.get((fl["status"].get("statusCategory") or {}).get("key"), "todo")
            by_epic[ref].append({
                "key": k["key"], "status": fl["status"]["name"], "category": cat,
                "bucket": smap.get(fl["status"]["name"], "done" if cat == "done" else "progress" if cat == "work" else "open"),
                "assignee": (fl.get("assignee") or {}).get("displayName") or "",
                "created": (self.local(fl.get("created")) or "")[:10],
                "doneAt": (self.local(fl.get("resolutiondate")) or "")[:10] or None if cat == "done" else None,
                "inSprint": k["key"] in in_sprint})
        out = []
        for h in heads:
            fl = h["fields"]
            d = fl.get(due)
            out.append({"key": h["key"], "title": (fl.get("summary") or "").strip(),
                        "due": str(d)[:10] if d else None, "children": by_epic.get(h["key"], [])})
        return out

    # ---------- снимок

    def collect(self):
        f = self.fields()
        smap = self.status_buckets()
        sprint = self.active_sprint()
        fields = "summary,status,issuetype,created,assignee,parent"
        fields += "".join("," + x for x in (f["sp"], f["epic"]) if x)
        raw = self.jira.issues(f"/rest/agile/1.0/sprint/{sprint['id']}/issue", fields=fields, expand="changelog")
        # второй проход: в ответе с changelog комментариев нет
        comments = {i["key"]: ((i["fields"].get("comment") or {}).get("comments") or [])
                    for i in self.jira.issues(f"/rest/agile/1.0/sprint/{sprint['id']}/issue", fields="comment")}
        issues = [self.issue(r, comments, sprint, smap, f) for r in raw]
        if not self.include_subtasks:
            issues = [i for i in issues if not i["subtask"]]
        unit = "SP" if f["sp"] and self.team.get("unit", "sp") == "sp" else "задач"
        return {
            "schema": SCHEMA, "team": {"slug": self.team["slug"], "name": self.team.get("name", self.team["slug"].upper())},
            "jira": self.jira.base, "board": self.team["board"], "collectedAt": self.now.isoformat(timespec="seconds"),
            "unit": unit, "statusBuckets": smap,
            "sprint": {"id": sprint["id"], "name": sprint["name"],
                       "start": (self.local(sprint.get("startDate")) or "")[:10],
                       "end": (self.local(sprint.get("endDate")) or "")[:10]},
            "issues": issues, "epics": self.epics(issues, smap, f),
        }
