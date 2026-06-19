# Multi-agent responding indicator — design

Date: 2026-06-19

The "responding now" dot shows a single yes/no. With several Claude sessions
working at once, the user wants to see **how many** agents are responding and
**which projects** they are — without enlarging the fixed-size window.

## Data layer

- **`status.responding_sessions(*, now, freshness_seconds, status_dir)`** → list of
  `{"session_id", "cwd", "ts"}` for every session whose mark is `responding`
  *and* fresh, sorted by `ts` (stable left-to-right order across refreshes).
  `is_responding(...)` becomes a thin wrapper: `len(responding_sessions(...)) > 0`,
  so existing callers/tests are unaffected.

- **`aggregate.model_by_session(records)`** → `{session_id: model}`, keyed by the
  transcript filename stem (`Path(source_file).stem`, which equals the session id
  — verified against `~/.claude/projects/**/<session_id>.jsonl`), value = the
  newest record's model for that file. Pure, unit-tested. A session with no
  matching transcript (or an unknown model) renders a neutral gray dot.

Project name = `Path(cwd).name`, truncated for display.

## Rendering

Replace the single `model_label` (a one-color `tk.Label`) with a small
`tk.Canvas` on the left of the top bar. A canvas lets us draw N independently
colored, shimmering dots plus a text label with no per-refresh widget churn, and
gives full control over per-dot brightness. The canvas joins `_drag_targets` and
gets the same drag + right-click bindings as the other widgets.

Three display modes:

- **0 responding** → one steady dot in the newest record's model color + short
  model name (`● Opus`). This preserves today's idle appearance.
- **1 responding** → `● Slotting`: one shimmering dot in that agent's model
  color + its project name.
- **≥2 responding** → `●●● Slotting`: one model-colored dot per agent, drawn
  left→right in `ts` order, all shimmering. The text label **cycles** through the
  agents' project names (~2s each). The dot for the currently-named agent
  brightens so the user can correlate dot ↔ name.

## Animation

Driven by the existing 90ms `_pulse_step` loop (no new timer):

- a tick counter advances each pulse; the displayed name index is
  `cycle_index(n, tick, hold)` with `hold ≈ 22` ticks (~2s);
- each dot shimmers via the existing sine phase; the active (currently-named)
  dot uses full brightness, the others a dimmer shimmer.

Pure, unit-tested helpers extracted to module level:

- `project_name(cwd, max_len)` — basename of `cwd`, truncated with an ellipsis.
- `cycle_index(n, tick, hold)` — which of `n` items is shown at a given tick.

## Defaults

- `config.DEFAULTS["flash_full_cost"]`: `0.25 → 0.50` (whole-response flashes are
  larger now, so the full-burn ceiling rises to keep them calm).
- The user's already-saved `config.json` persists the old `0.25`; update that
  stored value to `0.50` as part of the change so the new default takes effect.

## Out of scope / unchanged

- The `+$` cost flash stays **global**: it pulses once when all responding agents
  have gone idle, summing their cost. Per-agent flashing is not worth the
  fixed-width complexity (YAGNI).
- Window size, the cost/token figures, the sparkline, and the Linux tray are
  untouched.

## Testing

- `status.responding_sessions`: only fresh `responding` sessions returned;
  sorted by `ts`; idle/stale excluded; missing dir → `[]`. `is_responding` still
  behaves (wrapper).
- `aggregate.model_by_session`: maps stem→newest model; multiple files; empty.
- `project_name`: basename, trailing-slash, truncation.
- `cycle_index`: wraps over `n`, holds for `hold` ticks, handles `n<=1`.

Canvas drawing / shimmer (Tk) is verified by running the app, not unit-tested.
