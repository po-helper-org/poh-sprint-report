"""Снимок PO-Sprint-observe → снимок отчёта: задачи спринта, история, эпики, HTML для экрана."""
import datetime as dt
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from sprint_report import __main__ as cli
from sprint_report import metrics, observe

TEAM = {
    "slug": "alpha", "team": "Альфа", "sprintName": "Альфа 26.41", "jiraBase": "https://jira.example.com/",
    "boardId": 7, "_meta": {"collectedAt": "2026-10-15T09:30:00+03:00"},
    "statusMap": {"Открыто": "open", "В работе": "progress", "В ожидании": "blocked", "Закрыт": "done"},
    "burndown": {"start": "2026-10-06", "end": "2026-10-17", "items": [
        {"key": "A-1", "entered": "2026-10-06", "left": None, "subtask": False, "title": "Оплата"},
        {"key": "A-2", "entered": "2026-10-08", "left": None, "subtask": False, "title": "Каталог"},
        {"key": "A-3", "entered": "2026-10-06", "left": None, "subtask": True, "title": "Подзадача"},
    ]},
    "epics": [
        {"epicKey": "E-1", "epicTitle": "Платежи", "epicDue": "2026-10-30",
         "scope": [{"key": "A-1", "status": "В ожидании", "category": "В работе", "assignee": "Зайцев Пётр",
                    "created": "2026-10-01", "doneAt": None, "type": "История"},
                   {"key": "A-9", "status": "Закрыт", "category": "Выполнено", "assignee": "Котов Иван",
                    "created": "2026-09-01", "doneAt": "2026-09-20", "type": "История"}],
         "stories": [{"key": "A-1", "title": "Оплата в один клик", "status": "В ожидании", "assignee": "Зайцев Пётр",
                      "events": [{"at": "2026-10-01T10:00", "kind": "created", "by": "Котов Иван"},
                                 {"at": "2026-10-07T11:00", "kind": "status", "from": "Открыто", "to": "В работе", "by": "Зайцев Пётр"},
                                 {"at": "2026-10-09T12:00", "kind": "status", "from": "В работе", "to": "В ожидании", "by": "Зайцев Пётр"},
                                 {"at": "2026-10-09T12:01", "kind": "comment", "by": "Зайцев Пётр", "body": "Ждём доступ"}]}]},
        {"epicKey": None, "epicTitle": "Без эпика", "scope": [],
         "stories": [{"key": "A-2", "title": "Каталог", "status": "Открыто", "assignee": "", "events": []}]},
    ],
}


class ObserveSnapshot(unittest.TestCase):
    def test_sprint_and_issues(self):
        s = observe.team_snapshot(TEAM)
        self.assertEqual(s["team"], {"slug": "alpha", "name": "Альфа"})
        self.assertEqual(s["sprint"]["start"], "2026-10-06")
        self.assertEqual(s["jira"], "https://jira.example.com")
        self.assertEqual([i["key"] for i in s["issues"]], ["A-1", "A-2"])       # подзадачи не берём
        a1 = s["issues"][0]
        self.assertEqual((a1["bucket"], a1["epic"], a1["created"], a1["entered"]),
                         ("blocked", "E-1", "2026-10-01T10:00", "2026-10-06T00:00"))
        self.assertEqual([h["to"] for h in a1["history"]], ["В работе", "В ожидании"])
        self.assertEqual(a1["comments"][0]["body"], "Ждём доступ")

    def test_epics(self):
        e = observe.team_snapshot(TEAM)["epics"]
        self.assertEqual([x["key"] for x in e], ["E-1"])                           # «Без эпика» — не эпик
        kids = {k["key"]: k for k in e[0]["children"]}
        self.assertEqual((kids["A-1"]["category"], kids["A-1"]["inSprint"]), ("work", True))
        self.assertEqual((kids["A-9"]["category"], kids["A-9"]["doneAt"]), ("done", "2026-09-20"))

    def test_blocker_reaches_model(self):
        model, _ = metrics.build(observe.snapshots([TEAM]), dt.date(2026, 10, 15))
        self.assertEqual([b["key"] for b in model["blockers"]], ["A-1"])
        self.assertEqual(model["blockers"][0]["reason"], "Ждём доступ")

    def test_team_filter_and_no_sprint(self):
        self.assertEqual(observe.snapshots([TEAM], "beta"), [])
        self.assertEqual(observe.snapshots([{**TEAM, "burndown": {}}]), [])

    def test_cli_prints_web_html(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.json"
            p.write_text(json.dumps([TEAM], ensure_ascii=False), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["observe", "--data", str(p), "--team", "alpha", "--day", "2026-10-15"]), 0)
            html = out.getvalue()
            self.assertIn('<style media="screen">', html)
            self.assertIn("Альфа", html)
            self.assertNotIn("<script", html)                                    # встраивание под CSP без inline-скриптов
            self.assertEqual(cli.main(["observe", "--data", str(p), "--team", "beta"]), 2)


if __name__ == "__main__":
    unittest.main()
