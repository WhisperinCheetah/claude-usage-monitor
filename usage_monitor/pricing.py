"""Pay-as-you-go cost estimation for Claude API usage (per 1M tokens).

Rates are loaded from a JSON file so prices can be changed without editing code.
A user-supplied ``pricing.json`` in the OS-native config directory overrides the
bundled defaults if present.
"""
import json
import re
from pathlib import Path

from usage_monitor import paths

_BUNDLED_JSON = Path(__file__).parent / "pricing.json"
_MILLION = 1_000_000


def pricing_file() -> Path:
    """The pricing JSON in effect: the user override if present, else bundled."""
    user_json = paths.config_dir() / "pricing.json"
    return user_json if user_json.is_file() else _BUNDLED_JSON


def load_pricing(path=None) -> dict:
    with Path(path or pricing_file()).open("r", encoding="utf-8") as fh:
        return json.load(fh)


_data = load_pricing()
PRICING = _data["models"]
FALLBACK_MODEL = _data.get("fallback_model", "claude-opus-4-8")
_CACHE_WRITE_MULT = _data.get("cache_write_multiplier", 1.25)
_CACHE_READ_MULT = _data.get("cache_read_multiplier", 0.10)


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
