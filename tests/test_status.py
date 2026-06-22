import json
import tempfile
import unittest
from pathlib import Path

from usage_monitor import status


class TestStatus(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_missing_dir_is_not_responding(self):
        self.assertFalse(status.is_responding(now=1000, status_dir=self.dir / "nope"))

    def test_empty_dir_is_not_responding(self):
        self.assertFalse(status.is_responding(now=1000, status_dir=self.dir))

    def test_write_then_read_responding(self):
        status.write_status("responding", "sess-1", "/tmp/x", now=1000, status_dir=self.dir)
        self.assertTrue(status.is_responding(now=1000, status_dir=self.dir))

    def test_idle_is_not_responding(self):
        status.write_status("idle", "sess-1", now=1000, status_dir=self.dir)
        self.assertFalse(status.is_responding(now=1000, status_dir=self.dir))

    def test_model_is_stored_and_returned(self):
        status.write_status("responding", "sess-1", "/p", "claude-sonnet-4-6",
                            now=1000, status_dir=self.dir)
        sessions = status.responding_sessions(now=1000, status_dir=self.dir)
        self.assertEqual(sessions[0]["model"], "claude-sonnet-4-6")

    def test_model_defaults_blank_when_absent(self):
        status.write_status("responding", "sess-1", now=1000, status_dir=self.dir)
        sessions = status.responding_sessions(now=1000, status_dir=self.dir)
        self.assertEqual(sessions[0]["model"], "")

    def test_model_from_transcript_reads_newest(self):
        p = self.dir / "t.jsonl"
        p.write_text(
            json.dumps({"message": {"role": "assistant", "model": "claude-opus-4-8"}}) + "\n"
            + json.dumps({"message": {"role": "user"}}) + "\n"
            + json.dumps({"message": {"role": "assistant", "model": "claude-sonnet-4-6"}}) + "\n",
            encoding="utf-8")
        self.assertEqual(status.model_from_transcript(p), "claude-sonnet-4-6")

    def test_model_from_transcript_missing_file_is_blank(self):
        self.assertEqual(status.model_from_transcript(self.dir / "nope.jsonl"), "")

    def test_stale_responding_decays_to_not_responding(self):
        status.write_status("responding", "sess-1", now=1000, status_dir=self.dir)
        # 200s later, past the 180s freshness window.
        self.assertFalse(
            status.is_responding(now=1200, freshness_seconds=180, status_dir=self.dir)
        )

    def test_one_responding_among_idle_sessions(self):
        status.write_status("idle", "a", now=1000, status_dir=self.dir)
        status.write_status("idle", "b", now=1000, status_dir=self.dir)
        status.write_status("responding", "c", now=1000, status_dir=self.dir)
        self.assertTrue(status.is_responding(now=1000, status_dir=self.dir))

    def test_responding_sessions_returns_only_fresh_responding_sorted(self):
        status.write_status("responding", "b", "/p/b", now=1020, status_dir=self.dir)
        status.write_status("responding", "a", "/p/a", now=1000, status_dir=self.dir)
        status.write_status("idle", "c", "/p/c", now=1010, status_dir=self.dir)
        status.write_status("responding", "stale", now=500, status_dir=self.dir)
        sessions = status.responding_sessions(
            now=1030, freshness_seconds=180, status_dir=self.dir)
        self.assertEqual([s["session_id"] for s in sessions], ["a", "b"])  # ts order
        self.assertEqual(sessions[0]["cwd"], "/p/a")

    def test_responding_sessions_empty_when_no_dir(self):
        self.assertEqual(
            status.responding_sessions(now=1000, status_dir=self.dir / "nope"), [])

    def test_clear_removes_the_session(self):
        status.write_status("responding", "sess-1", now=1000, status_dir=self.dir)
        status.clear_status("sess-1", status_dir=self.dir)
        self.assertFalse(status.is_responding(now=1000, status_dir=self.dir))

    def test_clear_missing_session_is_silent(self):
        status.clear_status("ghost", status_dir=self.dir)  # must not raise

    def test_garbage_file_is_ignored(self):
        (self.dir).mkdir(parents=True, exist_ok=True)
        (self.dir / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertFalse(status.is_responding(now=1000, status_dir=self.dir))

    def test_unusual_session_id_is_sanitized(self):
        status.write_status("responding", "a/b c:d", now=1000, status_dir=self.dir)
        files = list(self.dir.glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertTrue(status.is_responding(now=1000, status_dir=self.dir))
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["session_id"], "a/b c:d")


if __name__ == "__main__":
    unittest.main()
