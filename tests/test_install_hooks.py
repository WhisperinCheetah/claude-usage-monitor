import json
import tempfile
import unittest
from pathlib import Path

from usage_monitor import install_hooks


class TestPatchSettings(unittest.TestCase):
    def _commands(self, settings):
        out = []
        for groups in settings.get("hooks", {}).values():
            for g in groups:
                for h in g.get("hooks", []):
                    out.append(h["command"])
        return out

    def test_fresh_install_adds_all_three_events(self):
        s = install_hooks.patch_settings({}, "py", "/repo/status_hook.py")
        self.assertEqual(
            set(s["hooks"]),
            {"UserPromptSubmit", "Stop", "SessionEnd"},
        )
        cmds = self._commands(s)
        self.assertTrue(any("responding" in c for c in cmds))
        self.assertTrue(any(c.endswith("idle") for c in cmds))
        self.assertTrue(any(c.endswith("end") for c in cmds))

    def test_install_is_idempotent(self):
        once = install_hooks.patch_settings({}, "py", "/repo/status_hook.py")
        twice = install_hooks.patch_settings(once, "py", "/repo/status_hook.py")
        # Exactly one group per event, both times.
        for event in ("UserPromptSubmit", "Stop", "SessionEnd"):
            self.assertEqual(len(twice["hooks"][event]), 1)
        self.assertEqual(once, twice)

    def test_reinstall_updates_stale_path(self):
        old = install_hooks.patch_settings({}, "py", "/old/status_hook.py")
        new = install_hooks.patch_settings(old, "py3", "/new/status_hook.py")
        cmds = self._commands(new)
        self.assertTrue(all("/new/status_hook.py" in c for c in cmds))
        self.assertFalse(any("/old/" in c for c in cmds))
        self.assertEqual(len(cmds), 3)

    def test_preserves_unrelated_hooks(self):
        existing = {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "my-own-thing"}]}],
                "PreToolUse": [{"matcher": "Bash",
                                "hooks": [{"type": "command", "command": "lint"}]}],
            }
        }
        s = install_hooks.patch_settings(existing, "py", "/repo/status_hook.py")
        cmds = self._commands(s)
        self.assertIn("my-own-thing", cmds)
        self.assertIn("lint", cmds)
        self.assertIn("PreToolUse", s["hooks"])
        # Stop now has the user's hook plus ours.
        self.assertEqual(len(s["hooks"]["Stop"]), 2)

    def test_uninstall_removes_only_ours(self):
        existing = {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "my-own-thing"}]}],
            }
        }
        installed = install_hooks.patch_settings(existing, "py", "/repo/status_hook.py")
        cleaned = install_hooks._strip_ours(installed)
        cmds = self._commands(cleaned)
        self.assertEqual(cmds, ["my-own-thing"])
        self.assertNotIn("UserPromptSubmit", cleaned["hooks"])

    def test_uninstall_drops_empty_hooks_key(self):
        installed = install_hooks.patch_settings({}, "py", "/repo/status_hook.py")
        cleaned = install_hooks._strip_ours(installed)
        self.assertNotIn("hooks", cleaned)


class TestInstallIO(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "settings.json"
        self.addCleanup(self._tmp.cleanup)

    def test_install_writes_valid_json_preserving_other_keys(self):
        self.path.write_text(json.dumps({"model": "opus", "theme": "dark"}), encoding="utf-8")
        install_hooks.install(self.path, python="py", script="/repo/status_hook.py")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["model"], "opus")
        self.assertIn("hooks", data)

    def test_install_then_uninstall_round_trip(self):
        install_hooks.install(self.path, python="py", script="/repo/status_hook.py")
        install_hooks.uninstall(self.path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("hooks", data)


if __name__ == "__main__":
    unittest.main()
