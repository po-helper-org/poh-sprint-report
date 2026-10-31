"""«Груминг»: модель экрана из снимка observe — эпики вне спринта, флаги расхождений, итоги, справочники."""
import datetime as dt
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from sprint_report import __main__ as cli
from sprint_report import demo, grooming

DAY = dt.date(2026, 10, 30)


def model(**over):
    team = {**demo.observe_team(DAY), **over}
    return grooming.build(team, DAY)


def story(m, key):
    return next(s for e in m["epics"] for s in e["stories"] if s["key"] == key)


def epic(m, key):
    return next(e for e in m["epics"] if e["key"] == key)


class Model(unittest.TestCase):
    def test_epics_outside_sprint_are_listed(self):
        m = model()
        self.assertTrue(m["hasGroom"])
        self.assertEqual({e["key"] for e in m["epics"]}, {"ALF-100", "ALF-101", "ALF-102", "ALF-103", "ALF-104"})
        self.assertFalse(epic(m, "ALF-103")["inSprint"])
        self.assertEqual(epic(m, "ALF-103")["status"], "Открыто")      # карточка эпика из groom.cards

    def test_without_groom_only_sprint_epics(self):
        m = model(groom=None)
        self.assertFalse(m["hasGroom"])
        self.assertEqual({e["key"] for e in m["epics"]}, {"ALF-100", "ALF-101", "ALF-102"})

    def test_progress_counts_stories_only(self):
        e = epic(model(), "ALF-100")
        self.assertEqual((e["counts"]["total"], e["counts"]["done"], e["counts"]["work"], e["counts"]["blocked"],
                          e["counts"]["open"], e["pct"]), (5, 1, 1, 1, 2, 20))
        self.assertEqual(e["sp"], {"done": 2, "total": 18})

    def test_order_open_epics_first_by_priority(self):
        keys = [e["key"] for e in model()["epics"]]
        self.assertEqual(keys[0], "ALF-100")                              # высокий приоритет, в спринте
        self.assertEqual(keys[-1], "ALF-104")                             # пустой эпик — в хвост
        self.assertLess(keys.index("ALF-101"), keys.index("ALF-103"))     # средний раньше без приоритета

    def test_story_flags(self):
        m = model()
        self.assertIn("sprint_no_owner", story(m, "ALF-502")["flags"])
        self.assertIn("no_assignee", story(m, "ALF-510")["flags"])        # в работе, исполнителя нет
        self.assertIn("blocker_closed", story(m, "ALF-503")["flags"])     # «в ожидании», а блокер закрыт
        self.assertIn("subtasks_done", story(m, "ALF-511")["flags"])      # подзадачи закрыты, история открыта
        self.assertIn("subtasks_open", story(m, "ALF-505")["flags"])      # история закрыта, подзадача нет
        self.assertIn("waits_for", story(m, "ALF-512")["flags"])          # блокер ещё в работе
        self.assertNotIn("blocker_closed", story(m, "ALF-512")["flags"])
        self.assertIn("stale", story(m, "ALF-504")["flags"])
        self.assertEqual(story(m, "ALF-504")["staleDays"], 64)
        self.assertNotIn("stale", story(m, "ALF-501")["flags"])
        self.assertEqual(story(m, "ALF-505")["flags"], ["subtasks_open"])  # закрытое — без «без квартала/оценки»

    def test_quarter_flag_only_when_field_collected(self):
        self.assertIn("no_quarter", story(model(), "ALF-530")["flags"])
        team = demo.observe_team(DAY)
        for e in team["groom"]["epics"] + team["epics"]:
            for i in e["scope"]:
                i.pop("quarter")
        m = grooming.build(team, DAY)
        self.assertNotIn("no_quarter", story(m, "ALF-530")["flags"])      # поля нет в данных — молчим

    def test_epic_flags(self):
        m = model()
        self.assertIn("epic_overdue", epic(m, "ALF-100")["flags"])
        self.assertEqual(epic(m, "ALF-102")["flags"].count("epic_all_done"), 1)
        self.assertNotIn("epic_overdue", epic(m, "ALF-102")["flags"])     # всё закрыто — срок не горит
        self.assertEqual(set(epic(m, "ALF-103")["flags"]), {"epic_no_owner", "epic_no_quarter", "epic_no_priority"})
        self.assertIn("epic_empty", epic(m, "ALF-104")["flags"])
        self.assertGreater(epic(m, "ALF-100")["warn"], 0)

    def test_totals_and_lists(self):
        m = model()
        t = m["totals"]
        self.assertEqual((t["epics"], t["stories"]), (5, 12))
        self.assertEqual(t["open"], 9)
        self.assertEqual(t["inSprint"], 4)
        self.assertGreaterEqual(t["flags"]["no_quarter"], 3)
        self.assertEqual(m["lists"]["priorities"], ["Высокий", "Средний", "Низкий"])
        self.assertEqual(m["lists"]["quarters"], ["2026Q4", "2027Q1"])
        self.assertEqual(m["lists"]["statuses"], ["Открыто", "В работе", "В ожидании", "Готово"])
        self.assertIn("Громов Кирилл", m["lists"]["people"])
        self.assertEqual(m["lists"]["statusBuckets"], {"Открыто": "open", "В работе": "progress", "В ожидании": "blocked", "Готово": "done"})

    def test_quarter_of(self):
        self.assertEqual([grooming.quarter_of(x) for x in ("2026Q4-S3", "Q4 2026", "2026 q1", "спринт 12", None)],
                         ["2026Q4", "2026Q4", "2026Q1", None, None])

    def test_prio_rank(self):
        names = ["Low", "Highest", "Medium", "Высокий", "", "Blocker"]
        self.assertEqual(sorted(names, key=grooming.prio_rank), ["Blocker", "Highest", "Высокий", "Medium", "Low", ""])


class Cli(unittest.TestCase):
    def test_prints_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.json"
            p.write_text(json.dumps([demo.observe_team(DAY)], ensure_ascii=False), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["grooming", "--data", str(p), "--team", "alpha", "--day", DAY.isoformat()]), 0)
            self.assertEqual(json.loads(out.getvalue())["team"]["slug"], "alpha")
            self.assertEqual(cli.main(["grooming", "--data", str(p), "--team", "beta"]), 2)


if __name__ == "__main__":
    unittest.main()
