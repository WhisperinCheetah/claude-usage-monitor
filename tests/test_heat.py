import unittest
from usage_monitor import heat


class TestHeat(unittest.TestCase):
    def test_intensity_bounds(self):
        self.assertEqual(heat.intensity(0), 0.0)
        self.assertEqual(heat.intensity(-5), 0.0)
        self.assertEqual(heat.intensity(heat.COLOR_MAX_SPEND), 1.0)
        self.assertEqual(heat.intensity(heat.COLOR_MAX_SPEND * 10), 1.0)
        self.assertAlmostEqual(heat.intensity(heat.COLOR_MAX_SPEND / 2), 0.5)

    def test_bucket_bounds(self):
        self.assertEqual(heat.bucket(0), 0)
        self.assertEqual(heat.bucket(heat.COLOR_MAX_SPEND), heat.N_BUCKETS - 1)
        self.assertEqual(heat.bucket(heat.COLOR_MAX_SPEND * 5), heat.N_BUCKETS - 1)

    def test_color_endpoints(self):
        self.assertEqual(heat.color_hex(0), "#5a5a5a")   # gray (90,90,90)
        self.assertEqual(heat.color_hex(1), "#2ecc71")   # green (46,204,113)

    def test_color_monotonic_green(self):
        # green channel should rise from idle to hot
        g0 = int(heat.color_hex(0)[3:5], 16)
        g1 = int(heat.color_hex(1)[3:5], 16)
        self.assertGreater(g1, g0)

    def test_gradient_svg_contains_fill(self):
        svg = heat.gradient_svg("#123456")
        self.assertIn("<svg", svg)
        self.assertIn("#123456", svg)


if __name__ == "__main__":
    unittest.main()
