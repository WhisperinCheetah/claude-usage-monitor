import unittest
from datetime import datetime, timezone
from usage_monitor import aggregate
from usage_monitor.transcripts import UsageRecord


def self_now():
    return datetime(2026, 6, 18, 14, 30, tzinfo=timezone.utc)


def rec(ts, model="claude-opus-4-8", i=0, o=0, cc=0, cr=0, mid="m", src="f"):
    return UsageRecord(ts, model, i, o, cc, cr, mid, src)


class TestModelBySession(unittest.TestCase):
    def test_maps_session_stem_to_newest_model(self):
        t0 = datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 6, 18, 14, 5, tzinfo=timezone.utc)
        recs = [
            rec(t0, model="claude-sonnet-4-6", src="/p/sessA.jsonl"),
            rec(t1, model="claude-opus-4-8", src="/p/sessA.jsonl"),   # newer wins
            rec(t0, model="claude-haiku-4-5", src="/q/sessB.jsonl"),
        ]
        self.assertEqual(
            aggregate.model_by_session(recs),
            {"sessA": "claude-opus-4-8", "sessB": "claude-haiku-4-5"},
        )

    def test_empty(self):
        self.assertEqual(aggregate.model_by_session([]), {})


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


class TestLatestRecord(unittest.TestCase):
    def test_none_when_empty(self):
        self.assertIsNone(aggregate.latest_record([]))

    def test_picks_max_timestamp(self):
        from datetime import timedelta
        now = self_now()
        recs = [
            rec(now - timedelta(hours=2), mid="old"),
            rec(now, mid="new"),
            rec(now - timedelta(minutes=5), mid="mid"),
        ]
        self.assertEqual(aggregate.latest_record(recs).message_id, "new")


class TestDeltaWindows(unittest.TestCase):
    def test_always_selectable_minutes(self):
        for tf in ("session", "today", "week", "month", "all"):
            keys = [k for k, _ in aggregate.delta_window_options(tf)]
            for w in ("5m", "10m", "30m", "60m"):
                self.assertIn(w, keys)

    def test_month_offers_larger_than_day(self):
        day_keys = [k for k, _ in aggregate.delta_window_options("today")]
        month_keys = [k for k, _ in aggregate.delta_window_options("month")]
        self.assertNotIn("24h", day_keys)
        self.assertIn("24h", month_keys)
        self.assertGreater(len(month_keys), len(day_keys))

    def test_default_scales_with_timeframe(self):
        self.assertEqual(aggregate.delta_default("today"), "10m")
        self.assertEqual(aggregate.delta_default("month"), "24h")

    def test_delta_seconds(self):
        self.assertEqual(aggregate.delta_seconds("5m"), 300)
        self.assertEqual(aggregate.delta_seconds("24h"), 86400)
        self.assertEqual(aggregate.delta_seconds("unknown"), 300)  # fallback

    def test_recent_delta(self):
        from datetime import timedelta
        now = self_now()
        recs = [
            rec(now - timedelta(minutes=2), o=1_000_000, model="claude-opus-4-8", mid="a"),
            rec(now - timedelta(hours=2), o=1_000_000, model="claude-opus-4-8", mid="b"),
        ]
        # 5m window: only the 2-min-old record -> $25.00
        self.assertAlmostEqual(aggregate.recent_delta(recs, now, 300, "accurate"), 25.0)
        # 24h window: both -> $50.00
        self.assertAlmostEqual(aggregate.recent_delta(recs, now, 86400, "accurate"), 50.0)


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
