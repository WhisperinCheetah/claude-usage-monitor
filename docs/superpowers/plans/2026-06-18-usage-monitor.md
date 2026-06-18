# claude-usage-monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an always-on-top Tkinter widget that reads local Claude Code transcripts and shows token usage plus estimated pay-as-you-go API cost.

**Architecture:** Pure logic modules (pricing, transcript parsing, aggregation, config) with no Tkinter import, tested with stdlib `unittest`; a single `app.py` Tkinter layer does all IO/state and a periodic refresh loop. Data comes only from `~/.claude/projects/**/*.jsonl` — no network.

**Tech Stack:** Python 3 standard library only (`tkinter`, `json`, `pathlib`, `datetime`, `re`, `glob`, `unittest`). No third-party dependencies, no build step.

## Global Constraints

- Standard library only — no `pip install` for app or tests. Tests use `unittest`.
- No network calls. The OTLP exporter in `~/.claude/settings.json` is ignored.
- All source lives in package `usage_monitor/`; tests in `tests/`.
- Run tests with: `python3 -m unittest discover -s tests -v`
- Pricing per 1M tokens (verbatim): opus-4-8 in 5.00 / out 25.00; sonnet-4-6 in 3.00 / out 15.00; haiku-4-5 in 1.00 / out 5.00. Cache write = 1.25 × input, cache read = 0.1 × input.
- Timeframe keys (verbatim): `session`, `today`, `week`, `last7days`, `month`, `all`.
- Cost mode keys (verbatim): `accurate`, `simple`.

---

### Task 0: Project scaffolding

**Files:**
- Create: `usage_monitor/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `.gitignore`

- [ ] **Step 1: Initialize git and package dirs**

```bash
cd /home/a3j/Documents/projects/usage-monitor
git init
mkdir -p usage_monitor tests
touch usage_monitor/__init__.py tests/__init__.py
printf '__pycache__/\n*.pyc\n' > .gitignore
```

- [ ] **Step 2: Verify the test runner works (no tests yet)**

Run: `python3 -m unittest discover -s tests -v`
Expected: `Ran 0 tests` and `OK`.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: scaffold usage_monitor package and tests"
```

---

### Task 1: Pricing engine

**Files:**
- Create: `usage_monitor/pricing.py`
- Test: `tests/test_pricing.py`

**Interfaces:**
- Produces:
  - `PRICING: dict[str, dict[str, float]]` — keys are normalized model ids, values `{"input": float, "output": float}` per 1M tokens.
  - `FALLBACK_MODEL: str = "claude-opus-4-8"`
  - `normalize_model(model: str) -> str` — maps a raw transcript model id to a key in `PRICING`, else `FALLBACK_MODEL`.
  - `cost_for(model: str, input: int, output: int, cache_creation: int, cache_read: int, mode: str = "accurate") -> float` — USD cost for one record.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pricing.py
import unittest
from usage_monitor import pricing


class TestNormalize(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(pricing.normalize_model("claude-opus-4-8"), "claude-opus-4-8")

    def test_strips_date_suffix(self):
        self.assertEqual(
            pricing.normalize_model("claude-haiku-4-5-20251001"), "claude-haiku-4-5"
        )

    def test_unknown_falls_back(self):
        self.assertEqual(pricing.normalize_model("claude-future-9"), pricing.FALLBACK_MODEL)


class TestCost(unittest.TestCase):
    def test_accurate_output_only(self):
        # 1M output tokens on opus = $25.00
        self.assertAlmostEqual(
            pricing.cost_for("claude-opus-4-8", 0, 1_000_000, 0, 0, "accurate"), 25.0
        )

    def test_accurate_cache(self):
        # 1M cache_creation = 1.25 * 5.00 = 6.25; 1M cache_read = 0.1 * 5.00 = 0.50
        self.assertAlmostEqual(
            pricing.cost_for("claude-opus-4-8", 0, 0, 1_000_000, 1_000_000, "accurate"),
            6.75,
        )

    def test_simple_treats_cache_as_input(self):
        # simple: (input + cache_creation + cache_read) * input_rate + output * output_rate
        # haiku: (1M + 1M + 1M) * 1.00 + 1M * 5.00 = 3.00 + 5.00 = 8.00
        self.assertAlmostEqual(
            pricing.cost_for(
                "claude-haiku-4-5-20251001", 1_000_000, 1_000_000, 1_000_000, 1_000_000, "simple"
            ),
            8.0,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_pricing -v`
Expected: FAIL / ERROR (`module 'usage_monitor.pricing' has no attribute ...` or import error).

- [ ] **Step 3: Write the implementation**

```python
# usage_monitor/pricing.py
"""Pay-as-you-go cost estimation for Claude API usage (per 1M tokens)."""
import re

PRICING = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}
FALLBACK_MODEL = "claude-opus-4-8"

_CACHE_WRITE_MULT = 1.25  # 5-minute cache write = 1.25x input
_CACHE_READ_MULT = 0.10   # cache read = 0.1x input
_MILLION = 1_000_000


def normalize_model(model: str) -> str:
    if model in PRICING:
        return model
    stripped = re.sub(r"-\d{6,}$", "", model or "")
    if stripped in PRICING:
        return stripped
    return FALLBACK_MODEL


def cost_for(model, input, output, cache_creation, cache_read, mode="accurate"):
    rates = PRICING[normalize_model(model)]
    in_rate = rates["input"]
    out_rate = rates["output"]
    if mode == "simple":
        input_side = input + cache_creation + cache_read
        total = input_side * in_rate + output * out_rate
    else:  # accurate
        total = (
            input * in_rate
            + output * out_rate
            + cache_creation * in_rate * _CACHE_WRITE_MULT
            + cache_read * in_rate * _CACHE_READ_MULT
        )
    return total / _MILLION
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_pricing -v`
Expected: PASS (3+3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add usage_monitor/pricing.py tests/test_pricing.py
git commit -m "feat: add pricing engine with accurate/simple cost modes"
```

---

### Task 2: Transcript parsing and dedup

**Files:**
- Create: `usage_monitor/transcripts.py`
- Test: `tests/test_transcripts.py`
- Test fixture: `tests/fixtures/sample.jsonl`

**Interfaces:**
- Produces:
  - `UsageRecord` dataclass with fields: `timestamp: datetime`, `model: str`, `input: int`, `output: int`, `cache_creation: int`, `cache_read: int`, `message_id: str`, `source_file: str`.
  - `parse_file(path: Path) -> list[UsageRecord]` — parses one JSONL file, skipping lines that are not assistant messages with a `usage` block and a parseable `timestamp`.
  - `dedup(records: Iterable[UsageRecord]) -> list[UsageRecord]` — keeps the first record per `message_id` (records with empty `message_id` are all kept).

- [ ] **Step 1: Create the test fixture**

```bash
mkdir -p tests/fixtures
```

```jsonl
{"timestamp":"2026-06-18T10:00:00.000Z","message":{"id":"msg_a","role":"assistant","model":"claude-opus-4-8","usage":{"input_tokens":100,"output_tokens":200,"cache_creation_input_tokens":300,"cache_read_input_tokens":400}}}
{"timestamp":"2026-06-18T10:00:00.000Z","message":{"id":"msg_a","role":"assistant","model":"claude-opus-4-8","usage":{"input_tokens":100,"output_tokens":200,"cache_creation_input_tokens":300,"cache_read_input_tokens":400}}}
{"timestamp":"2026-06-18T11:00:00.000Z","message":{"id":"msg_b","role":"assistant","model":"claude-haiku-4-5-20251001","usage":{"input_tokens":10,"output_tokens":20,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}}
{"timestamp":"2026-06-18T11:30:00.000Z","message":{"id":"msg_c","role":"user","content":"hi"}}
{"not":"json valid line but parseable"}
```

Save the five lines above as `tests/fixtures/sample.jsonl` (line 2 is a duplicate of line 1; line 4 is a user turn; line 5 has no usage).

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_transcripts.py
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_transcripts -v`
Expected: FAIL (import error / missing functions).

- [ ] **Step 4: Write the implementation**

```python
# usage_monitor/transcripts.py
"""Discover and parse Claude Code JSONL transcripts into usage records."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class UsageRecord:
    timestamp: datetime
    model: str
    input: int
    output: int
    cache_creation: int
    cache_read: int
    message_id: str
    source_file: str


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        # Handle trailing 'Z' (UTC) which fromisoformat rejects on older Pythons.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _record_from_obj(obj: dict, source_file: str) -> Optional[UsageRecord]:
    msg = obj.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "assistant":
        return None
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None
    ts = _parse_ts(obj.get("timestamp", ""))
    if ts is None:
        return None
    return UsageRecord(
        timestamp=ts,
        model=msg.get("model", ""),
        input=int(usage.get("input_tokens", 0) or 0),
        output=int(usage.get("output_tokens", 0) or 0),
        cache_creation=int(usage.get("cache_creation_input_tokens", 0) or 0),
        cache_read=int(usage.get("cache_read_input_tokens", 0) or 0),
        message_id=str(msg.get("id", "")),
        source_file=source_file,
    )


def parse_file(path: Path) -> list:
    path = Path(path)
    records = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue
                rec = _record_from_obj(obj, str(path))
                if rec is not None:
                    records.append(rec)
    except OSError:
        return []
    return records


def dedup(records: Iterable) -> list:
    seen = set()
    out = []
    for r in records:
        if r.message_id:
            if r.message_id in seen:
                continue
            seen.add(r.message_id)
        out.append(r)
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_transcripts -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add usage_monitor/transcripts.py tests/test_transcripts.py tests/fixtures/sample.jsonl
git commit -m "feat: parse JSONL transcripts into deduped usage records"
```

---

### Task 3: Transcript discovery and incremental cache

**Files:**
- Modify: `usage_monitor/transcripts.py`
- Modify: `tests/test_transcripts.py`

**Interfaces:**
- Consumes: `parse_file`, `UsageRecord` from Task 2.
- Produces:
  - `default_projects_dir() -> Path` — returns `~/.claude/projects`.
  - `find_transcripts(projects_dir: Path) -> list[Path]` — all `*.jsonl` under the dir, recursively; empty list if dir missing.
  - `class TranscriptCache` with `load(paths: list[Path]) -> list[UsageRecord]` — re-parses only files whose `(mtime, size)` changed since the last `load`; returns the concatenation of all current files' records (not deduped — caller dedups).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_transcripts.py
import os
import tempfile


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_transcripts.TestDiscoveryAndCache -v`
Expected: FAIL (missing `find_transcripts` / `TranscriptCache`).

- [ ] **Step 3: Add the implementation**

```python
# append to usage_monitor/transcripts.py
import os


def default_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def find_transcripts(projects_dir: Path) -> list:
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return []
    return sorted(projects_dir.rglob("*.jsonl"))


class TranscriptCache:
    """Re-parses only files whose (mtime, size) changed since the last load."""

    def __init__(self):
        self._cache = {}  # str(path) -> (mtime, size, records)

    def load(self, paths) -> list:
        records = []
        current_keys = set()
        for path in paths:
            path = Path(path)
            key = str(path)
            current_keys.add(key)
            try:
                st = path.stat()
                sig = (st.st_mtime, st.st_size)
            except OSError:
                continue
            cached = self._cache.get(key)
            if cached is None or cached[0:2] != sig:
                recs = parse_file(path)
                self._cache[key] = (sig[0], sig[1], recs)
            records.extend(self._cache[key][2])
        # drop cache entries for files no longer present
        for stale in set(self._cache) - current_keys:
            del self._cache[stale]
        return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_transcripts -v`
Expected: PASS (all transcript tests).

- [ ] **Step 5: Commit**

```bash
git add usage_monitor/transcripts.py tests/test_transcripts.py
git commit -m "feat: add transcript discovery and incremental mtime cache"
```

---

### Task 4: Aggregation (timeframes, filtering, rollups)

**Files:**
- Create: `usage_monitor/aggregate.py`
- Test: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `UsageRecord` (Task 2), `pricing.cost_for`, `pricing.normalize_model` (Task 1).
- Produces:
  - `TIMEFRAMES: list[tuple[str, str]]` — ordered `(key, label)` pairs: `("session","Current session")`, `("today","Today")`, `("week","This week")`, `("last7days","Last 7 days")`, `("month","This month")`, `("all","All-time")`.
  - `timeframe_bounds(key: str, now: datetime) -> tuple[Optional[datetime], Optional[datetime]]` — `(start, end)`; `None` means open-ended. For `session` and `all`, returns `(None, None)`.
  - `filter_by_time(records, start, end) -> list[UsageRecord]` — keeps records with `start <= timestamp < end` (open ends ignored). Comparison is done in the record's own tz-aware time.
  - `session_file(paths: list[Path]) -> Optional[Path]` — newest file by mtime, or `None`.
  - `filter_by_file(records, path) -> list[UsageRecord]` — records whose `source_file == str(path)`.
  - `rollup(records, mode: str) -> dict` — `{"total_tokens": int, "total_cost": float, "by_model": {normalized_model: {"tokens": int, "cost": float}}}`. `total_tokens` sums input+output+cache_creation+cache_read.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_aggregate.py
import unittest
from datetime import datetime, timezone
from usage_monitor import aggregate
from usage_monitor.transcripts import UsageRecord


def rec(ts, model="claude-opus-4-8", i=0, o=0, cc=0, cr=0, mid="m", src="f"):
    return UsageRecord(ts, model, i, o, cc, cr, mid, src)


class TestBounds(unittest.TestCase):
    def setUp(self):
        # Thursday 2026-06-18 14:30 UTC
        self.now = datetime(2026, 6, 18, 14, 30, tzinfo=timezone.utc)

    def test_today(self):
        start, end = aggregate.timeframe_bounds("today", self.now)
        self.assertEqual(start, datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc))
        self.assertIsNone(end)

    def test_week_starts_monday(self):
        start, _ = aggregate.timeframe_bounds("week", self.now)
        self.assertEqual(start, datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc))  # Mon

    def test_month(self):
        start, _ = aggregate.timeframe_bounds("month", self.now)
        self.assertEqual(start, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc))

    def test_last7days_rolling(self):
        start, _ = aggregate.timeframe_bounds("last7days", self.now)
        self.assertEqual(start, datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc))

    def test_all_open(self):
        self.assertEqual(aggregate.timeframe_bounds("all", self.now), (None, None))


class TestFilterAndRollup(unittest.TestCase):
    def test_filter_by_time(self):
        recs = [
            rec(datetime(2026, 6, 17, tzinfo=timezone.utc), mid="old"),
            rec(datetime(2026, 6, 18, 12, tzinfo=timezone.utc), mid="new"),
        ]
        start = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
        kept = aggregate.filter_by_time(recs, start, None)
        self.assertEqual([r.message_id for r in kept], ["new"])

    def test_rollup(self):
        recs = [
            rec(self_now(), i=0, o=1_000_000, model="claude-opus-4-8", mid="a"),
            rec(self_now(), i=0, o=1_000_000, model="claude-haiku-4-5-20251001", mid="b"),
        ]
        out = aggregate.rollup(recs, "accurate")
        self.assertEqual(out["total_tokens"], 2_000_000)
        self.assertAlmostEqual(out["total_cost"], 30.0)  # opus 25 + haiku 5
        self.assertAlmostEqual(out["by_model"]["claude-opus-4-8"]["cost"], 25.0)
        self.assertAlmostEqual(out["by_model"]["claude-haiku-4-5"]["cost"], 5.0)


def self_now():
    return datetime(2026, 6, 18, 14, 30, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_aggregate -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

```python
# usage_monitor/aggregate.py
"""Timeframe filtering and per-model rollups over usage records."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from usage_monitor import pricing

TIMEFRAMES = [
    ("session", "Current session"),
    ("today", "Today"),
    ("week", "This week"),
    ("last7days", "Last 7 days"),
    ("month", "This month"),
    ("all", "All-time"),
]


def timeframe_bounds(key: str, now: datetime):
    if key in ("session", "all"):
        return (None, None)
    if key == "today":
        return (now.replace(hour=0, minute=0, second=0, microsecond=0), None)
    if key == "week":
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (midnight - timedelta(days=now.weekday()), None)
    if key == "month":
        return (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), None)
    if key == "last7days":
        return (now - timedelta(days=7), None)
    return (None, None)


def filter_by_time(records, start: Optional[datetime], end: Optional[datetime]):
    out = []
    for r in records:
        if start is not None and r.timestamp < start:
            continue
        if end is not None and r.timestamp >= end:
            continue
        out.append(r)
    return out


def session_file(paths) -> Optional[Path]:
    newest = None
    newest_mtime = None
    for p in paths:
        p = Path(p)
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if newest_mtime is None or m > newest_mtime:
            newest_mtime = m
            newest = p
    return newest


def filter_by_file(records, path):
    target = str(path)
    return [r for r in records if r.source_file == target]


def rollup(records, mode: str) -> dict:
    total_tokens = 0
    total_cost = 0.0
    by_model = {}
    for r in records:
        tokens = r.input + r.output + r.cache_creation + r.cache_read
        cost = pricing.cost_for(r.model, r.input, r.output, r.cache_creation, r.cache_read, mode)
        total_tokens += tokens
        total_cost += cost
        key = pricing.normalize_model(r.model)
        slot = by_model.setdefault(key, {"tokens": 0, "cost": 0.0})
        slot["tokens"] += tokens
        slot["cost"] += cost
    return {"total_tokens": total_tokens, "total_cost": total_cost, "by_model": by_model}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_aggregate -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add usage_monitor/aggregate.py tests/test_aggregate.py
git commit -m "feat: add timeframe filtering and per-model rollups"
```

---

### Task 5: Config persistence

**Files:**
- Create: `usage_monitor/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `DEFAULTS: dict` — `{"x": None, "y": None, "timeframe": "month", "mode": "accurate"}`.
  - `config_path() -> Path` — `~/.config/claude-usage-monitor/config.json`.
  - `load_config(path: Path) -> dict` — returns `DEFAULTS` merged with the file contents; on missing/corrupt file returns a copy of `DEFAULTS`.
  - `save_config(path: Path, cfg: dict) -> None` — creates parent dirs and writes JSON.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import json
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_config -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

```python
# usage_monitor/config.py
"""Load/save widget settings as JSON under ~/.config."""
import json
from pathlib import Path

DEFAULTS = {"x": None, "y": None, "timeframe": "month", "mode": "accurate"}


def config_path() -> Path:
    return Path.home() / ".config" / "claude-usage-monitor" / "config.json"


def load_config(path: Path) -> dict:
    cfg = dict(DEFAULTS)
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update({k: data[k] for k in DEFAULTS if k in data})
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update({k: cfg[k] for k in DEFAULTS if k in cfg})
    with path.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_config -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add usage_monitor/config.py tests/test_config.py
git commit -m "feat: add config persistence with defaults"
```

---

### Task 6: Token formatting helper

**Files:**
- Create: `usage_monitor/format.py`
- Test: `tests/test_format.py`

**Interfaces:**
- Produces:
  - `fmt_tokens(n: int) -> str` — `950` → `"950"`, `12_400` → `"12.4K"`, `2_500_000` → `"2.5M"`, `1_200_000_000` → `"1.2B"`.
  - `fmt_cost(usd: float) -> str` — `58.912` → `"$58.91"`, `0` → `"$0.00"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_format.py
import unittest
from usage_monitor import format as fmt


class TestFormat(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(fmt.fmt_tokens(950), "950")
        self.assertEqual(fmt.fmt_tokens(12_400), "12.4K")
        self.assertEqual(fmt.fmt_tokens(2_500_000), "2.5M")
        self.assertEqual(fmt.fmt_tokens(1_200_000_000), "1.2B")

    def test_cost(self):
        self.assertEqual(fmt.fmt_cost(58.912), "$58.91")
        self.assertEqual(fmt.fmt_cost(0), "$0.00")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_format -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

```python
# usage_monitor/format.py
"""Human-friendly formatting for tokens and cost."""


def fmt_tokens(n: int) -> str:
    n = int(n)
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            return f"{n / limit:.1f}{suffix}"
    return str(n)


def fmt_cost(usd: float) -> str:
    return f"${usd:.2f}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_format -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add usage_monitor/format.py tests/test_format.py
git commit -m "feat: add token/cost formatting helpers"
```

---

### Task 7: Tkinter app and refresh loop

**Files:**
- Create: `usage_monitor/app.py`
- Create: `run.py`

**Interfaces:**
- Consumes: `transcripts` (`default_projects_dir`, `find_transcripts`, `TranscriptCache`, `dedup`), `aggregate` (`TIMEFRAMES`, `timeframe_bounds`, `filter_by_time`, `filter_by_file`, `session_file`, `rollup`), `config` (`config_path`, `load_config`, `save_config`), `format` (`fmt_tokens`, `fmt_cost`).
- Produces: `class UsageMonitorApp` with `__init__(self, projects_dir=None, config_file=None)` and `run(self)`; module-level `main()`.

This task is UI/IO and is verified manually (Step 4), not with unittest.

- [ ] **Step 1: Write the app**

```python
# usage_monitor/app.py
"""Always-on-top Tkinter widget showing Claude token usage and estimated cost."""
import tkinter as tk
from datetime import datetime, timezone

from usage_monitor import aggregate, config, transcripts
from usage_monitor.format import fmt_cost, fmt_tokens

REFRESH_MS = 3000
_MODE_LABELS = [("accurate", "Accurate"), ("simple", "Simple")]
_MODEL_SHORT = {
    "claude-opus-4-8": "Opus",
    "claude-sonnet-4-6": "Sonnet",
    "claude-haiku-4-5": "Haiku",
}


class UsageMonitorApp:
    def __init__(self, projects_dir=None, config_file=None):
        self.projects_dir = projects_dir or transcripts.default_projects_dir()
        self.config_file = config_file or config.config_path()
        self.cfg = config.load_config(self.config_file)
        self.cache = transcripts.TranscriptCache()

        self.root = tk.Tk()
        self.root.title("Claude Usage")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, False)
        if self.cfg.get("x") is not None and self.cfg.get("y") is not None:
            self.root.geometry(f"+{self.cfg['x']}+{self.cfg['y']}")

        self._build_widgets()
        self._bind_drag()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _label(self, parent, text, **kw):
        opts = dict(bg="#1e1e1e", fg="#dddddd", font=("TkDefaultFont", 10))
        opts.update(kw)
        return tk.Label(parent, text=text, **opts)

    def _build_widgets(self):
        top = tk.Frame(self.root, bg="#1e1e1e")
        top.pack(fill="x", padx=8, pady=(8, 2))

        self.tf_var = tk.StringVar()
        tf_labels = [label for _, label in aggregate.TIMEFRAMES]
        current_tf = self._label_for_key(aggregate.TIMEFRAMES, self.cfg["timeframe"])
        self.tf_var.set(current_tf)
        tf_menu = tk.OptionMenu(top, self.tf_var, *tf_labels, command=lambda _=None: self._on_setting_change())
        tf_menu.config(bg="#2d2d2d", fg="#dddddd", highlightthickness=0, font=("TkDefaultFont", 9))
        tf_menu.pack(side="left")

        self.mode_var = tk.StringVar()
        mode_labels = [label for _, label in _MODE_LABELS]
        self.mode_var.set(self._label_for_key(_MODE_LABELS, self.cfg["mode"]))
        mode_menu = tk.OptionMenu(top, self.mode_var, *mode_labels, command=lambda _=None: self._on_setting_change())
        mode_menu.config(bg="#2d2d2d", fg="#dddddd", highlightthickness=0, font=("TkDefaultFont", 9))
        mode_menu.pack(side="right")

        body = tk.Frame(self.root, bg="#1e1e1e")
        body.pack(fill="x", padx=8)
        self.tokens_label = self._label(body, "Tokens   —", font=("TkDefaultFont", 11))
        self.tokens_label.pack(anchor="w")
        self.cost_label = self._label(body, "Cost     —", font=("TkDefaultFont", 14, "bold"), fg="#7ec699")
        self.cost_label.pack(anchor="w")
        self.breakdown_label = self._label(body, "", fg="#999999", font=("TkDefaultFont", 9))
        self.breakdown_label.pack(anchor="w")
        self.status_label = self._label(self.root, "● starting…", fg="#777777", font=("TkDefaultFont", 8))
        self.status_label.pack(anchor="w", padx=8, pady=(2, 8))

        self._drag_targets = [self.root, body, self.tokens_label, self.cost_label, self.breakdown_label]

    @staticmethod
    def _label_for_key(pairs, key):
        for k, label in pairs:
            if k == key:
                return label
        return pairs[0][1]

    @staticmethod
    def _key_for_label(pairs, label):
        for k, lab in pairs:
            if lab == label:
                return k
        return pairs[0][0]

    def _bind_drag(self):
        for w in self._drag_targets:
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _current_timeframe_key(self):
        return self._key_for_label(aggregate.TIMEFRAMES, self.tf_var.get())

    def _current_mode_key(self):
        return self._key_for_label(_MODE_LABELS, self.mode_var.get())

    def _on_setting_change(self):
        self._save()
        self.refresh()

    def _save(self):
        self.cfg["timeframe"] = self._current_timeframe_key()
        self.cfg["mode"] = self._current_mode_key()
        self.cfg["x"] = self.root.winfo_x()
        self.cfg["y"] = self.root.winfo_y()
        config.save_config(self.config_file, self.cfg)

    def _on_close(self):
        self._save()
        self.root.destroy()

    def refresh(self):
        paths = transcripts.find_transcripts(self.projects_dir)
        records = transcripts.dedup(self.cache.load(paths))
        tf = self._current_timeframe_key()
        mode = self._current_mode_key()

        if tf == "session":
            newest = aggregate.session_file(paths)
            selected = aggregate.filter_by_file(records, newest) if newest else []
        else:
            start, end = aggregate.timeframe_bounds(tf, datetime.now(timezone.utc))
            selected = aggregate.filter_by_time(records, start, end)

        result = aggregate.rollup(selected, mode)
        self.tokens_label.config(text=f"Tokens   {fmt_tokens(result['total_tokens'])}")
        self.cost_label.config(text=f"Cost     {fmt_cost(result['total_cost'])}")
        self.breakdown_label.config(text=self._breakdown_text(result["by_model"]))
        self.status_label.config(text=f"● updated {datetime.now().strftime('%H:%M:%S')}")

    @staticmethod
    def _breakdown_text(by_model):
        if not by_model:
            return "no usage in range"
        parts = []
        for model, vals in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"]):
            short = _MODEL_SHORT.get(model, model)
            parts.append(f"{short} {fmt_cost(vals['cost'])}")
        return " · ".join(parts)

    def _tick(self):
        self.refresh()
        self.root.after(REFRESH_MS, self._tick)

    def run(self):
        self.root.after(0, self._tick)
        self.root.mainloop()


def main():
    UsageMonitorApp().run()
```

```python
# run.py
"""Entry point for the Claude usage monitor widget."""
from usage_monitor.app import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Confirm the full test suite still passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS (all tasks' tests).

- [ ] **Step 3: Smoke-test that the app imports without a display**

Run: `python3 -c "import usage_monitor.app; print('import ok')"`
Expected: `import ok` (importing must not require a display).

- [ ] **Step 4: Manual run and verification**

Run: `python3 run.py`
Verify by observation:
- A small window appears and stays on top of other windows.
- "Cost" shows a non-zero dollar figure and "Tokens" a formatted count (your transcripts have real usage).
- Changing the timeframe dropdown changes the numbers (e.g. All-time ≥ This month).
- Changing the cost dropdown (Accurate ↔ Simple) changes the cost; Simple ≥ Accurate.
- Dragging the body moves the window.
- Close it, reopen with `python3 run.py` — it reappears at the same position with the same timeframe/mode (config persisted to `~/.config/claude-usage-monitor/config.json`).

- [ ] **Step 5: Commit**

```bash
git add usage_monitor/app.py run.py
git commit -m "feat: add always-on-top Tkinter widget and refresh loop"
```

---

### Task 8: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

```markdown
# claude-usage-monitor

A super-lightweight, always-on-top desktop widget that reads your local Claude
Code transcripts (`~/.claude/projects/**/*.jsonl`) and shows token usage plus
the estimated pay-as-you-go Anthropic API cost — i.e. what the same usage would
cost without a subscription.

Pure Python standard library. No dependencies, no build step, no network.

## Run

```bash
python3 run.py
```

## Use

- **Timeframe dropdown:** Current session, Today, This week (from Monday),
  Last 7 days, This month, All-time.
- **Cost dropdown:** Accurate (cache writes at 1.25×, reads at 0.1× input) or
  Simple (all input-side tokens at the flat input rate).
- Drag the body to move it; position, timeframe, and mode are remembered in
  `~/.config/claude-usage-monitor/config.json`.

## Pricing

Hardcoded per-1M-token rates in `usage_monitor/pricing.py`
(Opus 4.8 / Sonnet 4.6 / Haiku 4.5). Update that table when prices change.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

## Self-Review

**Spec coverage:**
- Data source & parsing → Task 2 (parse/dedup) + Task 3 (discovery/cache). ✓
- Cost engine (accurate/simple, normalization, fallback) → Task 1. ✓
- Timeframe filtering (all six windows, week=Monday) → Task 4. ✓
- UI (always-on-top, dropdowns, breakdown, drag, updated indicator) → Task 7. ✓
- Refresh loop (3s, incremental) → Task 3 cache + Task 7 `_tick`. ✓
- Persistence (x/y/timeframe/mode) → Task 5 + Task 7 `_save`. ✓
- Structure (pure logic vs UI) → modules split across Tasks 1–7. ✓
- Token formatting (12.4M) → Task 6. ✓
- Testing strategy → unittest tasks 1–6; manual for UI task 7. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** `UsageRecord` field names consistent across Tasks 2/3/4; `rollup` dict keys (`total_tokens`, `total_cost`, `by_model`) consumed identically in Task 7; `TIMEFRAMES`/`_MODE_LABELS` `(key,label)` shape used consistently. ✓
