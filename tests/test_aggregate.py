import unittest
from datetime import datetime, timezone
from usage_monitor import aggregate
from usage_monitor.transcripts import UsageRecord


def self_now():
    return datetime(2026, 6, 18, 14, 30, tzinfo=timezone.utc)


def rec(ts, model="claude-opus-4-8", i=0, o=0, cc=0, cr=0, mid="m", src="f"):
    return UsageRecord(ts, model, i, o, cc, cr, mid, src)


class TestBounds(unittest.TestCase):
    def setUp(self):
        # Thursday 2026-06-18 14:30 UTC
        self.now = self_now()

    def test_today(self):
        start, end = aggregate.timeframe_bounds("today", self.now)
        self.assertEqual(start, datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc))
        self.assertIsNone(end)

    def test_week_starts_monday(self):
        start, _ = aggregate.timeframe_bounds("week", self.now)
        self.assertEqual(start, datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc))  # Mon

    def test_month(self):
        start, _ = aggregate.timeframe_bounds("month", self.now)
        self.assertEqual(start, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc))

    def test_last7days_rolling(self):
        start, _ = aggregate.timeframe_bounds("last7days", self.now)
        self.assertEqual(start, datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc))

    def test_all_open(self):
        self.assertEqual(aggregate.timeframe_bounds("all", self.now), (None, None))


class TestFilterAndRollup(unittest.TestCase):
    def test_filter_by_time(self):
        recs = [
            rec(datetime(2026, 6, 17, tzinfo=timezone.utc), mid="old"),
            rec(datetime(2026, 6, 18, 12, tzinfo=timezone.utc), mid="new"),
        ]
        start = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
        kept = aggregate.filter_by_time(recs, start, None)
        self.assertEqual([r.message_id for r in kept], ["new"])

    def test_rollup(self):
        recs = [
            rec(self_now(), i=0, o=1_000_000, model="claude-opus-4-8", mid="a"),
            rec(self_now(), i=0, o=1_000_000, model="claude-haiku-4-5-20251001", mid="b"),
        ]
        out = aggregate.rollup(recs, "accurate")
        self.assertEqual(out["total_tokens"], 2_000_000)
        self.assertAlmostEqual(out["total_cost"], 30.0)  # opus 25 + haiku 5
        self.assertAlmostEqual(out["by_model"]["claude-opus-4-8"]["cost"], 25.0)
        self.assertAlmostEqual(out["by_model"]["claude-haiku-4-5"]["cost"], 5.0)


if __name__ == "__main__":
    unittest.main()
