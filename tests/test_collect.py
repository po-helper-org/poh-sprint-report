"""Сборщик на подменной Jira: поля, статусы, спринт, история, вход в спринт, эпики."""
import datetime as dt
import unittest

from sprint_report.collect import Collector

MSK = dt.timezone(dt.timedelta(hours=3))


def issue(key, status, cat, *, sp=None, epic=None, who=None, hist=(), sprint_change=None, subtask=False):
    histories = [{"created": at, "author": {"displayName": "Робот"},
                  "items": [{"field": "status", "fromString": a, "toString": b}]} for at, a, b in hist]
    if sprint_change:
        histories.append({"created": sprint_change, "author": {"displayName": "Робот"},
                          "items": [{"field": "Sprint", "fromString": "", "toString": "Альфа 1"}]})
    return {"key": key, "fields": {
        "summary": f"Задача {key}", "status": {"name": status, "statusCategory": {"key": cat}},
        "issuetype": {"name": "Подзадача" if subtask else "Задача", "subtask": subtask},
        "created": "2026-10-01T10:00:00.000+0300", "assignee": {"displayName": who} if who else None,
        "customfield_1": sp, "customfield_2": epic}, "changelog": {"histories": histories}}


class FakeJira:
    base = "https://jira.example.com"
    requests = 0

    def __init__(self):
        self.calls = []

    def get(self, path, **params):
        self.calls.append(path)
        if path == "/rest/api/2/field":
            return [{"id": "customfield_1", "name": "Story Points"}, {"id": "customfield_2", "name": "Epic Link"},
                    {"id": "customfield_3", "name": "Target end"}]
        if path == "/rest/api/2/status":
            return [{"name": n, "statusCategory": {"key": c}} for n, c in
                    (("Открыто", "new"), ("В работе", "indeterminate"), ("Код-ревью", "indeterminate"),
                     ("В ожидании", "indeterminate"), ("Готово", "done"), ("Ждёт релиза", "indeterminate"))]
        raise AssertionError(path)

    def values(self, path, **params):
        return [{"id": 5, "name": "Альфа 1", "state": "active", "originBoardId": 7,
                 "startDate": "2026-10-05T09:00:00.000+03:00", "endDate": "2026-10-18T20:00:00.000+03:00"}]

    def issues(self, path, **params):
        if path.endswith("/issue") and params.get("fields") == "comment":
            return [{"key": "A-2", "fields": {"comment": {"comments": [
                {"created": "2026-10-09T12:00:00.000+0300", "author": {"displayName": "Петров Илья"}, "body": "Ждём доступы"}]}}}]
        if path.endswith("/issue"):
            return [
                issue("A-1", "Готово", "done", sp=3, epic="A-100", who="Петров Илья",
                      hist=[("2026-10-06T10:00:00.000+0300", "Открыто", "В работе"),
                            ("2026-10-08T15:00:00.000+0300", "В работе", "Готово")]),
                issue("A-2", "В ожидании", "indeterminate", sp=5, epic="A-100", who="Петров Илья",
                      hist=[("2026-10-07T10:00:00.000+0300", "В работе", "В ожидании")],
                      sprint_change="2026-10-07T09:00:00.000+0300"),
                issue("A-3", "Ждёт релиза", "indeterminate", sp=2),
                issue("A-4", "Открыто", "new", subtask=True),
            ]
        if "key in" in params.get("jql", ""):
            return [{"key": "A-100", "fields": {"summary": "[26Q4] Оплата", "customfield_3": "2026-10-20"}}]
        if "cf[2]" in params.get("jql", ""):
            return [{"key": k, "fields": {"status": {"name": s, "statusCategory": {"key": c}}, "created": "2026-09-01T10:00:00.000+0300",
                                          "resolutiondate": r, "assignee": None, "issuetype": {"subtask": False}, "customfield_2": "A-100"}}
                    for k, s, c, r in (("A-1", "Готово", "done", "2026-10-08T15:00:00.000+0300"),
                                       ("A-2", "В ожидании", "indeterminate", None), ("A-9", "Открыто", "new", None))]
        raise AssertionError((path, params))


class CollectTest(unittest.TestCase):
    def setUp(self):
        team = {"slug": "alpha", "name": "Альфа", "board": 7, "status_buckets": {"Ждёт релиза": "review"}}
        self.snap = Collector(FakeJira(), team, MSK, now=dt.datetime(2026, 10, 9, 8, 30, tzinfo=MSK)).collect()
        self.by = {i["key"]: i for i in self.snap["issues"]}

    def test_sprint_and_unit(self):
        self.assertEqual(self.snap["sprint"], {"id": 5, "name": "Альфа 1", "start": "2026-10-05", "end": "2026-10-18"})
        self.assertEqual(self.snap["unit"], "SP")

    def test_buckets_with_team_rule(self):
        self.assertEqual(self.by["A-2"]["bucket"], "blocked")
        self.assertEqual(self.by["A-3"]["bucket"], "review")        # правило команды сильнее категории
        self.assertEqual(self.snap["statusBuckets"]["Готово"], "done")

    def test_history_comments_sprint_entry(self):
        self.assertEqual(self.by["A-1"]["history"][-1], {"at": "2026-10-08T15:00", "from": "В работе", "to": "Готово", "by": "Робот"})
        self.assertEqual(self.by["A-2"]["entered"], "2026-10-07T09:00")
        self.assertEqual(self.by["A-2"]["comments"][0]["body"], "Ждём доступы")
        self.assertTrue(self.by["A-4"]["subtask"])

    def test_epics(self):
        (e,) = self.snap["epics"]
        self.assertEqual((e["key"], e["due"]), ("A-100", "2026-10-20"))
        kids = {k["key"]: k for k in e["children"]}
        self.assertEqual(kids["A-1"]["doneAt"], "2026-10-08")
        self.assertTrue(kids["A-2"]["inSprint"])
        self.assertFalse(kids["A-9"]["inSprint"])
        self.assertEqual(kids["A-2"]["bucket"], "blocked")


if __name__ == "__main__":
    unittest.main()
