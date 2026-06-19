import unittest

from usage_monitor.app import clamp_to_screen


class TestClampToScreen(unittest.TestCase):
    def test_position_on_screen_is_unchanged(self):
        self.assertEqual(clamp_to_screen(100, 50, 384, 206, 3840, 1587), (100, 50))

    def test_off_right_edge_is_pulled_back(self):
        # The real-world bug: saved x past every monitor's right edge.
        x, y = clamp_to_screen(4085, 50, 384, 206, 3840, 1587)
        self.assertEqual(x, 3840 - 384)  # fully visible against the right edge
        self.assertEqual(y, 50)

    def test_off_bottom_edge_is_pulled_back(self):
        x, y = clamp_to_screen(10, 5000, 384, 206, 3840, 1587)
        self.assertEqual(y, 1587 - 206)

    def test_negative_is_clamped_to_origin(self):
        self.assertEqual(clamp_to_screen(-200, -50, 384, 206, 3840, 1587), (0, 0))

    def test_window_larger_than_screen_pins_to_origin(self):
        self.assertEqual(clamp_to_screen(100, 100, 5000, 5000, 1920, 1080), (0, 0))


if __name__ == "__main__":
    unittest.main()
