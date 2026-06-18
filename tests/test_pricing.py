import unittest
from usage_monitor import pricing


class TestNormalize(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(pricing.normalize_model("claude-opus-4-8"), "claude-opus-4-8")

    def test_strips_date_suffix(self):
        self.assertEqual(
            pricing.normalize_model("claude-haiku-4-5-20251001"), "claude-haiku-4-5"
        )

    def test_unknown_falls_back(self):
        self.assertEqual(pricing.normalize_model("claude-future-9"), pricing.FALLBACK_MODEL)


class TestCost(unittest.TestCase):
    def test_accurate_output_only(self):
        # 1M output tokens on opus = $25.00
        self.assertAlmostEqual(
            pricing.cost_for("claude-opus-4-8", 0, 1_000_000, 0, 0, "accurate"), 25.0
        )

    def test_accurate_cache(self):
        # 1M cache_creation = 1.25 * 5.00 = 6.25; 1M cache_read = 0.1 * 5.00 = 0.50
        self.assertAlmostEqual(
            pricing.cost_for("claude-opus-4-8", 0, 0, 1_000_000, 1_000_000, "accurate"),
            6.75,
        )

    def test_simple_treats_cache_as_input(self):
        # simple: (input + cache_creation + cache_read) * input_rate + output * output_rate
        # haiku: (1M + 1M + 1M) * 1.00 + 1M * 5.00 = 3.00 + 5.00 = 8.00
        self.assertAlmostEqual(
            pricing.cost_for(
                "claude-haiku-4-5-20251001", 1_000_000, 1_000_000, 1_000_000, 1_000_000, "simple"
            ),
            8.0,
        )


if __name__ == "__main__":
    unittest.main()
