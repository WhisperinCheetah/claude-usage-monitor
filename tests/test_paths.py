import os
import sys
import unittest
from pathlib import Path
from usage_monitor import paths


class TestPaths(unittest.TestCase):
    def test_ends_with_app_name_and_absolute(self):
        d = paths.config_dir()
        self.assertEqual(d.name, paths.APP_NAME)
        self.assertTrue(d.is_absolute())

    def test_linux_respects_xdg(self):
        if sys.platform == "darwin" or os.name == "nt":
            self.skipTest("Linux-only behavior")
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = "/tmp/xdg-test"
        try:
            self.assertEqual(paths.config_dir(), Path("/tmp/xdg-test") / paths.APP_NAME)
        finally:
            if old is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old


if __name__ == "__main__":
    unittest.main()
