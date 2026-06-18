import tempfile
import unittest
from pathlib import Path
from usage_monitor import config


class TestConfig(unittest.TestCase):
    def test_missing_returns_defaults(self):
        cfg = config.load_config(Path("/no/such/config.json"))
        self.assertEqual(cfg, config.DEFAULTS)
        self.assertIsNot(cfg, config.DEFAULTS)  # must be a copy

    def test_corrupt_returns_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text("{not json")
            self.assertEqual(config.load_config(p), config.DEFAULTS)

    def test_round_trip_and_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "c.json"
            config.save_config(p, {"timeframe": "today", "x": 5})
            cfg = config.load_config(p)
            self.assertEqual(cfg["timeframe"], "today")
            self.assertEqual(cfg["x"], 5)
            self.assertEqual(cfg["mode"], "accurate")  # default filled in


if __name__ == "__main__":
    unittest.main()
