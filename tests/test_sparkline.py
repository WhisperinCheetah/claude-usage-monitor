import unittest
from datetime import datetime, timedelta, timezone
from usage_monitor import sparkline
from usage_monitor.transcripts import UsageRecord


def rec(ts, o=0, model="claude-opus-4-8", mid="m"):
    return UsageRecord(ts, model, 0, o, 0, 0, mid, "f")


class TestSparkline(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 18, 14, 30, tzinfo=timezone.utc)

    def test_range_keys_and_next(self):
        self.assertEqual(sparkline.range_keys(), ["1h", "24h", "7d", "30d"])
        self.assertEqual(sparkline.next_range("1h"), "24h")
        self.assertEqual(sparkline.next_range("30d"), "1h")  # wraps

    def test_bucketize_length(self):
        self.assertEqual(len(sparkline.bucketize([], self.now, "1h", "accurate")), 12)
        self.assertEqual(len(sparkline.bucketize([], self.now, "24h", "accurate")), 24)
        self.assertEqual(len(sparkline.bucketize([], self.now, "7d", "accurate")), 7)

    def test_bucketize_places_costs(self):
        # 1h range = 12 buckets of 5 min, start = now - 60 min.
        recs = [
            rec(self.now - timedelta(minutes=2), o=1_000_000),   # idx 11 (newest)
            rec(self.now - timedelta(minutes=7), o=1_000_000),   # idx 10
            rec(self.now - timedelta(hours=3), o=1_000_000),     # out of range -> dropped
        ]
        out = sparkline.bucketize(recs, self.now, "1h", "accurate")
        self.assertAlmostEqual(out[11], 25.0)   # opus 1M output = $25
        self.assertAlmostEqual(out[10], 25.0)
        self.assertAlmostEqual(sum(out), 50.0)  # the 3h-old record excluded


if __name__ == "__main__":
    unittest.main()
