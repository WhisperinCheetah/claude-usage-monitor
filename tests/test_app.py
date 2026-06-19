import unittest

from usage_monitor.app import (
    clamp_to_monitors,
    clamp_to_screen,
    parse_xrandr_monitors,
)


class TestClampToScreen(unittest.TestCase):
    def test_position_on_screen_is_unchanged(self):
        self.assertEqual(clamp_to_screen(100, 50, 384, 206, 3840, 1587), (100, 50))

    def test_off_right_edge_is_pulled_back(self):
        x, y = clamp_to_screen(4085, 50, 384, 206, 3840, 1587)
        self.assertEqual(x, 3840 - 384)
        self.assertEqual(y, 50)

    def test_off_bottom_edge_is_pulled_back(self):
        x, y = clamp_to_screen(10, 5000, 384, 206, 3840, 1587)
        self.assertEqual(y, 1587 - 206)

    def test_negative_is_clamped_to_origin(self):
        self.assertEqual(clamp_to_screen(-200, -50, 384, 206, 3840, 1587), (0, 0))

    def test_window_larger_than_screen_pins_to_origin(self):
        self.assertEqual(clamp_to_screen(100, 100, 5000, 5000, 1920, 1080), (0, 0))


class TestParseXrandrMonitors(unittest.TestCase):
    SAMPLE = (
        "Monitors: 2\n"
        " 0: +*HDMI-1-0 1920/477x1080/268+0+0  HDMI-1-0\n"
        " 1: +eDP-1 1920/344x1080/193+1920+507  eDP-1\n"
    )

    def test_parses_each_monitor_rect(self):
        self.assertEqual(
            parse_xrandr_monitors(self.SAMPLE),
            [(0, 0, 1920, 1080), (1920, 507, 1920, 1080)],
        )

    def test_empty_or_garbage_returns_empty(self):
        self.assertEqual(parse_xrandr_monitors(""), [])
        self.assertEqual(parse_xrandr_monitors("not xrandr output"), [])


class TestClampToMonitors(unittest.TestCase):
    # The user's real layout: side-by-side monitors at different y-offsets,
    # leaving a dead zone in the top-right of the bounding box.
    MONITORS = [(0, 0, 1920, 1080), (1920, 507, 1920, 1080)]

    def test_dead_zone_position_lands_on_a_real_monitor(self):
        # (4085, 50) is past every monitor and in the inter-monitor gap.
        x, y = clamp_to_monitors(4085, 50, 384, 206, self.MONITORS)
        # Nearest monitor is eDP-1; window must sit fully inside it.
        self.assertTrue(1920 <= x <= 1920 + 1920 - 384)
        self.assertTrue(507 <= y <= 507 + 1080 - 206)

    def test_position_already_on_a_monitor_is_unchanged(self):
        self.assertEqual(clamp_to_monitors(100, 100, 384, 206, self.MONITORS), (100, 100))

    def test_position_on_second_monitor_stays_there(self):
        self.assertEqual(
            clamp_to_monitors(2000, 600, 384, 206, self.MONITORS), (2000, 600)
        )

    def test_no_monitors_returns_input_unchanged(self):
        self.assertEqual(clamp_to_monitors(4085, 50, 384, 206, []), (4085, 50))


if __name__ == "__main__":
    unittest.main()
