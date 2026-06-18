import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from usage_monitor import transcripts

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


class TestParse(unittest.TestCase):
    def test_parses_only_assistant_usage_lines(self):
        recs = transcripts.parse_file(FIXTURE)
        # lines 1,2 (assistant w/ usage, duplicated), 3 (assistant). 4 user, 5 no usage skipped.
        self.assertEqual(len(recs), 3)

    def test_fields_extracted(self):
        recs = transcripts.parse_file(FIXTURE)
        r = recs[0]
        self.assertEqual(r.message_id, "msg_a")
        self.assertEqual(r.model, "claude-opus-4-8")
        self.assertEqual((r.input, r.output, r.cache_creation, r.cache_read), (100, 200, 300, 400))
        self.assertEqual(r.timestamp, datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc))

    def test_dedup_by_message_id(self):
        recs = transcripts.dedup(transcripts.parse_file(FIXTURE))
        ids = sorted(r.message_id for r in recs)
        self.assertEqual(ids, ["msg_a", "msg_b"])


class TestDiscoveryAndCache(unittest.TestCase):
    def test_find_transcripts_missing_dir(self):
        self.assertEqual(transcripts.find_transcripts(Path("/no/such/dir")), [])

    def test_find_transcripts(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "proj"
            sub.mkdir()
            (sub / "a.jsonl").write_text("")
            (sub / "b.txt").write_text("")
            found = transcripts.find_transcripts(Path(d))
            self.assertEqual([p.name for p in found], ["a.jsonl"])

    def test_cache_reparses_on_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.jsonl"
            line = (
                '{"timestamp":"2026-06-18T10:00:00Z","message":{"id":"x","role":"assistant",'
                '"model":"claude-opus-4-8","usage":{"input_tokens":1,"output_tokens":1,'
                '"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}}\n'
            )
            p.write_text(line)
            cache = transcripts.TranscriptCache()
            self.assertEqual(len(cache.load([p])), 1)
            # append a second record; bump mtime to be safe
            p.write_text(line + line.replace('"id":"x"', '"id":"y"'))
            os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 10))
            self.assertEqual(len(cache.load([p])), 2)


if __name__ == "__main__":
    unittest.main()
