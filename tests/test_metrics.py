"""Метрики и отрисовка на демо-снимке: инварианты сгорания, блоки, пульс, эпики, HTML без падений."""
import datetime as dt
import unittest

from sprint_report import buckets, deliver, demo, metrics, render
from sprint_report.metrics import Snapshot

DAY = dt.date(2026, 10, 15)


class BucketsTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(buckets.classify("В ожидании", "indeterminate"), "blocked")
        self.assertEqual(buckets.classify("Code review", "indeterminate"), "review")
        self.assertEqual(buckets.classify("Тестирование", "indeterminate"), "testing")
        self.assertEqual(buckets.classify("Done", "done"), "done")
        self.assertEqual(buckets.classify("Backlog", "new"), "open")
        self.assertEqual(buckets.classify("Ожидает релиза", "indeterminate", {"Ожидает релиза": "review"}), "review")
        with self.assertRaises(ValueError):
            buckets.classify("X", "new", {"X": "nope"})


class MetricsTest(unittest.TestCase):
    def setUp(self):
        self.snap = demo.snapshot(DAY)
        self.model, self.ops = metrics.build([self.snap], DAY, demo.promises(DAY))
        self.t = self.ops["teams"][0]

    def test_burndown_invariants(self):
        burn = self.t["burn"]
        self.assertEqual(burn[0]["date"], self.snap["sprint"]["start"])
        self.assertLessEqual(burn[-1]["date"], DAY.isoformat())
        for b in burn:
            self.assertAlmostEqual(b["remaining"], b["scope"] - b["closed"])
            self.assertGreaterEqual(b["remaining"], 0)
        self.assertTrue(all(a["closed"] <= b["closed"] for a, b in zip(burn, burn[1:])))

    def test_blockers_are_blocked_bucket(self):
        keys = {i["key"] for i in self.snap["issues"] if i["bucket"] == "blocked"}
        self.assertEqual({b["key"] for b in self.model["blockers"]}, keys)
        self.assertEqual(max(b["days"] for b in self.model["blockers"]), 12)
        self.assertTrue(all(b["reason"] for b in self.model["blockers"]))

    def test_pulse_and_flow(self):
        p = self.t["pulse"]
        self.assertEqual(len(p["days"]), metrics.PULSE_DAYS)
        self.assertEqual(len(p["done"]), len(p["wip"]))
        self.assertEqual(set(self.t["flow"]), {"work", "review", "testing", "done"})

    def test_epics(self):
        for e in self.t["epics"]:
            self.assertTrue(0 <= e["pct"] <= 100)
            self.assertEqual(sum(e["cats"].values()), e["total"])
            self.assertGreaterEqual(e["d14n"], e["d3n"])

    def test_done_at_reopen(self):
        S = Snapshot(self.snap)
        i = {"bucket": "done", "created": "2026-10-01T10:00", "history": [
            {"at": "2026-10-05T10:00", "from": "В работе", "to": "Готово"},
            {"at": "2026-10-06T10:00", "from": "Готово", "to": "В работе"},
            {"at": "2026-10-08T10:00", "from": "В работе", "to": "Готово"}]}
        self.assertEqual(S.done_at(i), "2026-10-08T10:00")
        self.assertIsNone(S.done_at(dict(i, bucket="progress")))

    def test_render_and_caption(self):
        page = render.render(self.model, self.ops, "Альфа")
        for part in ("Прогноз спринта", "Успеем к", "Снять блоки", "Сроки и обещания", "Эпики в спринте", "Стоит дольше всего"):
            self.assertIn(part, page)
        text = deliver.caption(self.model, self.ops, DAY)
        self.assertIn("Альфа:", text)
        self.assertIn("Заблокировано: D10+ 1", text)

    def test_demo_is_deterministic(self):
        self.assertEqual(demo.snapshot(DAY), demo.snapshot(DAY))


if __name__ == "__main__":
    unittest.main()
