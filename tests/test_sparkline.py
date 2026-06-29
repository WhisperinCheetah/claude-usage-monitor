import unittest
from datetime import datetime, timedelta, timezone
from usage_monitor import sparkline
from usage_monitor.transcripts import UsageRecord


def rec(ts, o=0, model="claude-opus-4-8", mid="m"):
    return UsageRecord(ts, model, 0, o, 0, 0, mid, "f")


class TestSparkline(unittest.TestCase):
    def setUp(self):
        # Aware so bucketize can align to this timezone deterministically.
        self.now = datetime(2026, 6, 18, 14, 30, tzinfo=timezone.utc)

    def test_range_keys_and_next(self):
        self.assertEqual(sparkline.range_keys(), ["1h", "12h", "24h", "7d", "30d"])
        self.assertEqual(sparkline.next_range("1h"), "12h")
        self.assertEqual(sparkline.next_range("12h"), "24h")
        self.assertEqual(sparkline.next_range("30d"), "1h")  # wraps

    def test_bucketize_length(self):
        self.assertEqual(len(sparkline.bucketize([], self.now, "1h", "accurate")), 12)
        self.assertEqual(len(sparkline.bucketize([], self.now, "12h", "accurate")), 12)
        self.assertEqual(len(sparkline.bucketize([], self.now, "24h", "accurate")), 24)
        self.assertEqual(len(sparkline.bucketize([], self.now, "7d", "accurate")), 7)
        self.assertEqual(len(sparkline.bucketize([], self.now, "30d", "accurate")), 30)

    def test_hour_buckets_align_to_clock(self):
        # now = 14:30, so the current (newest, idx 23) hourly bucket is 14:00-15:00.
        recs = [
            rec(self.now, o=1_000_000),                          # 14:30 -> idx 23
            rec(self.now - timedelta(minutes=45), o=1_000_000),  # 13:45 -> idx 22
            rec(self.now - timedelta(hours=23), o=1_000_000),    # 15:30 prev day -> idx 0
            rec(self.now - timedelta(days=2), o=1_000_000),      # out of range -> dropped
        ]
        out = sparkline.bucketize(recs, self.now, "24h", "accurate")
        self.assertAlmostEqual(out[23], 25.0)   # opus 1M output = $25
        self.assertAlmostEqual(out[22], 25.0)
        self.assertAlmostEqual(out[0], 25.0)
        self.assertAlmostEqual(sum(out), 75.0)  # the 2-day-old record excluded

    def test_day_buckets_reset_at_midnight(self):
        # 7 daily bars; idx 6 is today, idx 5 yesterday, ... idx 0 six days ago.
        recs = [
            rec(self.now.replace(hour=14), o=1_000_000),         # today 14:00 -> idx 6
            rec(self.now.replace(hour=0, minute=30), o=1_000_000),  # today 00:30 -> idx 6
            rec(self.now - timedelta(days=1), o=1_000_000),      # yesterday -> idx 5
            rec(self.now - timedelta(days=6), o=1_000_000),      # six days ago -> idx 0
            rec(self.now - timedelta(days=7), o=1_000_000),      # seven days ago -> dropped
        ]
        out = sparkline.bucketize(recs, self.now, "7d", "accurate")
        self.assertAlmostEqual(out[6], 50.0)    # both of today's records
        self.assertAlmostEqual(out[5], 25.0)
        self.assertAlmostEqual(out[0], 25.0)
        self.assertAlmostEqual(sum(out), 100.0)  # the 7-day-old record excluded

    def test_record_just_before_midnight_is_previous_day(self):
        # A record 13h ago (yesterday 23:00 from a 12:00 now) belongs to idx 5,
        # not today, even though it's well under 24h old -> proves calendar reset.
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        recs = [rec(datetime(2026, 6, 17, 23, 0, tzinfo=timezone.utc), o=1_000_000)]
        out = sparkline.bucketize(recs, now, "7d", "accurate")
        self.assertAlmostEqual(out[5], 25.0)
        self.assertAlmostEqual(out[6], 0.0)


if __name__ == "__main__":
    unittest.main()
