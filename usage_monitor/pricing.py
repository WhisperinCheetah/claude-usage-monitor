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
