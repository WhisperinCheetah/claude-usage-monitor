import unittest

from usage_monitor.app import (
    _heartbeat_intensities,
    clamp_to_monitors,
    clamp_to_screen,
    flash_intensity,
    parse_xrandr_monitors,
    turn_flash_decision,
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


class TestFlashIntensity(unittest.TestCase):
    def test_zero_cost_is_zero(self):
        self.assertEqual(flash_intensity(0.0, 0.25), 0.0)

    def test_negative_cost_is_zero(self):
        self.assertEqual(flash_intensity(-1.0, 0.25), 0.0)

    def test_half_of_full_is_half(self):
        self.assertAlmostEqual(flash_intensity(0.125, 0.25), 0.5)

    def test_at_full_is_one(self):
        self.assertEqual(flash_intensity(0.25, 0.25), 1.0)

    def test_above_full_is_clamped_to_one(self):
        self.assertEqual(flash_intensity(10.0, 0.25), 1.0)

    def test_zero_or_negative_ceiling_is_zero(self):
        self.assertEqual(flash_intensity(1.0, 0.0), 0.0)
        self.assertEqual(flash_intensity(1.0, -0.5), 0.0)


class TestTurnFlashDecision(unittest.TestCase):
    def test_turn_start_banks_anchor_and_does_not_flash(self):
        # idle -> responding: remember pre-turn total (10.0), no flash yet.
        cost, anchor = turn_flash_decision(10.0, 10.0, False, True, 0.0)
        self.assertIsNone(cost)
        self.assertEqual(anchor, 10.0)

    def test_mid_turn_accumulates_silently(self):
        # responding -> responding: messages arrived (10 -> 10.4) but no flash.
        cost, anchor = turn_flash_decision(10.0, 10.4, True, True, 9.0)
        self.assertIsNone(cost)
        self.assertEqual(anchor, 9.0)  # anchor unchanged mid-turn

    def test_turn_end_flashes_whole_response_cost(self):
        # responding -> idle: flash total(12.5) - anchor(10.0) = the turn's cost.
        cost, _ = turn_flash_decision(12.5, 12.5, True, False, 10.0)
        self.assertAlmostEqual(cost, 2.5)

    def test_end_sums_many_substeps_into_one_flash(self):
        # A turn that started at 10.0 and, across several tool steps, reached
        # 13.2 flashes 3.2 once — not once per step.
        cost, _ = turn_flash_decision(13.2, 13.2, True, False, 10.0)
        self.assertAlmostEqual(cost, 3.2)

    def test_fast_turn_between_polls_flashes_delta(self):
        # idle -> idle but new cost appeared (hookless, or sub-poll turn).
        cost, _ = turn_flash_decision(10.0, 10.7, False, False, 0.0)
        self.assertAlmostEqual(cost, 0.7)

    def test_idle_with_no_new_cost_yields_zero(self):
        cost, _ = turn_flash_decision(10.0, 10.0, False, False, 0.0)
        self.assertEqual(cost, 0.0)  # caller filters this out


class TestHeartbeat(unittest.TestCase):
    def test_each_beat_peaks_at_one_and_settles_at_zero(self):
        seq = _heartbeat_intensities(2)
        self.assertEqual(seq[-1], 0.0)
        self.assertEqual(seq.count(1.0), 2)  # one peak per beat
        self.assertTrue(all(0.0 <= t <= 1.0 for t in seq))


if __name__ == "__main__":
    unittest.main()
