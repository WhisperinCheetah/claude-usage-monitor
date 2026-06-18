"""Human-friendly formatting for tokens and cost."""


def fmt_tokens(n: int) -> str:
    n = int(n)
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            return f"{n / limit:.1f}{suffix}"
    return str(n)


def fmt_cost(usd: float) -> str:
    return f"${usd:.2f}"
