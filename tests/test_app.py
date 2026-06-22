import unittest

from usage_monitor.app import (
    _heartbeat_intensities,
    clamp_to_monitors,
    clamp_to_screen,
    cycle_index,
    flash_intensity,
    flash_delta,
    parse_xrandr_monitors,
    project_name,
    running_models,
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


class TestFlashDelta(unittest.TestCase):
    def test_new_spend_since_last_poll(self):
        # A (sub)response finished between polls: flash just its small cost.
        self.assertAlmostEqual(flash_delta(10.0, 10.07), 0.07)

    def test_no_new_spend_is_zero(self):
        self.assertEqual(flash_delta(10.0, 10.0), 0.0)  # caller filters this out

    def test_never_negative_on_total_drop(self):
        # Timeframe rollover / removed records mustn't flash a negative.
        self.assertEqual(flash_delta(12.5, 10.0), 0.0)

    def test_does_not_balloon_with_concurrent_agents(self):
        # Each poll only reports the delta since the previous one — never the
        # whole concurrent window summed together (the old +$2347 bug).
        self.assertAlmostEqual(flash_delta(2000.0, 2000.12), 0.12)


class TestProjectName(unittest.TestCase):
    def test_basename(self):
        self.assertEqual(project_name("/home/a3j/Documents/projects/usage-monitor"),
                         "usage-monitor")

    def test_trailing_slash(self):
        self.assertEqual(project_name("/home/a3j/work/Slotting/"), "Slotting")

    def test_truncation_with_ellipsis(self):
        out = project_name("/x/this-is-a-very-long-project-name", max_len=10)
        self.assertEqual(len(out), 10)
        self.assertTrue(out.endswith("…"))

    def test_empty_cwd(self):
        self.assertEqual(project_name(""), "?")


class TestCycleIndex(unittest.TestCase):
    def test_single_item_always_zero(self):
        self.assertEqual(cycle_index(1, 999, 22), 0)
        self.assertEqual(cycle_index(0, 999, 22), 0)

    def test_holds_then_advances_and_wraps(self):
        self.assertEqual(cycle_index(3, 0, 10), 0)
        self.assertEqual(cycle_index(3, 9, 10), 0)   # still holding first
        self.assertEqual(cycle_index(3, 10, 10), 1)  # advanced
        self.assertEqual(cycle_index(3, 20, 10), 2)
        self.assertEqual(cycle_index(3, 30, 10), 0)  # wrapped

    def test_zero_hold_is_safe(self):
        self.assertEqual(cycle_index(3, 5, 0), 0)


class TestHeartbeat(unittest.TestCase):
    def test_each_beat_peaks_at_one_and_settles_at_zero(self):
        seq = _heartbeat_intensities(2)
        self.assertEqual(seq[-1], 0.0)
        self.assertEqual(seq.count(1.0), 2)  # one peak per beat
        self.assertTrue(all(0.0 <= t <= 1.0 for t in seq))


class TestRunningModels(unittest.TestCase):
    def test_empty_when_no_sessions(self):
        self.assertEqual(running_models([], {"s1": "claude-opus-4-8"}), set())

    def test_maps_session_to_normalized_model(self):
        sessions = [{"session_id": "s1"}, {"session_id": "s2"}]
        mm = {"s1": "claude-opus-4-8", "s2": "claude-sonnet-4-6"}
        self.assertEqual(running_models(sessions, mm),
                         {"claude-opus-4-8", "claude-sonnet-4-6"})

    def test_dedupes_shared_model(self):
        sessions = [{"session_id": "s1"}, {"session_id": "s2"}]
        mm = {"s1": "claude-opus-4-8", "s2": "claude-opus-4-8"}
        self.assertEqual(running_models(sessions, mm), {"claude-opus-4-8"})

    def test_missing_or_blank_model_is_skipped(self):
        sessions = [{"session_id": "s1"}, {"session_id": "s2"}]
        mm = {"s1": ""}  # s2 absent entirely
        self.assertEqual(running_models(sessions, mm), set())

    def test_session_model_takes_precedence_over_map(self):
        # The hook-stamped model on the session wins over the transcript map.
        sessions = [{"session_id": "s1", "model": "claude-sonnet-4-6"}]
        mm = {"s1": "claude-opus-4-8"}
        self.assertEqual(running_models(sessions, mm), {"claude-sonnet-4-6"})

    def test_falls_back_to_map_when_session_has_no_model(self):
        sessions = [{"session_id": "s1", "model": ""}]
        mm = {"s1": "claude-opus-4-8"}
        self.assertEqual(running_models(sessions, mm), {"claude-opus-4-8"})


if __name__ == "__main__":
    unittest.main()
