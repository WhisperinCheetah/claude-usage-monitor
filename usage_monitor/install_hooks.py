"""Install/remove the Claude Code hooks that feed the "responding" indicator.

    python -m usage_monitor.install_hooks            # install (idempotent)
    python -m usage_monitor.install_hooks --uninstall

Patches ``~/.claude/settings.json`` in place, registering ``status_hook.py`` for
UserPromptSubmit (responding), Stop (idle), and SessionEnd (end). Re-running is a
no-op; unrelated hooks you already have are left untouched. Our entries are
recognised by the ``status_hook.py`` script path in their command string.
"""
import copy
import json
import shlex
import sys
from pathlib import Path

# (Claude Code hook event, state argument passed to status_hook.py)
EVENTS = [
    ("UserPromptSubmit", "responding"),
    ("Stop", "idle"),
    ("SessionEnd", "end"),
]
_MARKER = "status_hook.py"


def hook_script() -> Path:
    return Path(__file__).resolve().parent / "hooks" / "status_hook.py"


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def build_command(state: str, python: str, script: str) -> str:
    return f"{shlex.quote(python)} {shlex.quote(script)} {state}"


def _is_ours(group) -> bool:
    if not isinstance(group, dict):
        return False
    for h in group.get("hooks", []):
        if isinstance(h, dict) and _MARKER in str(h.get("command", "")):
            return True
    return False


def _strip_ours(settings: dict) -> dict:
    """Remove only our hook groups; drop events/hooks key if left empty."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not _is_ours(g)]
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    return settings


def patch_settings(settings: dict, python: str, script: str) -> dict:
    """Return settings with our hooks freshly (re)installed. Pure."""
    settings = copy.deepcopy(settings)  # never mutate the caller's dict
    settings = _strip_ours(settings)  # clear stale entries first -> idempotent
    hooks = settings.setdefault("hooks", {})
    for event, state in EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            groups = []
            hooks[event] = groups
        groups.append({"hooks": [{"type": "command",
                                  "command": build_command(state, python, script)}]})
    return settings


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def install(path=None, python=None, script=None) -> Path:
    path = Path(path) if path else settings_path()
    python = python or sys.executable or "python3"
    script = script or str(hook_script())
    settings = patch_settings(_load(path), python, script)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return path


def uninstall(path=None) -> Path:
    path = Path(path) if path else settings_path()
    settings = _strip_ours(_load(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--uninstall" in argv:
        path = uninstall()
        print(f"Removed usage-monitor hooks from {path}")
    else:
        path = install()
        print(f"Installed usage-monitor hooks in {path}")
        print("Restart any running Claude Code sessions for the hooks to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
