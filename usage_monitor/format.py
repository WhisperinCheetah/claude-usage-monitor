"""Human-friendly formatting for tokens and cost."""


def fmt_tokens(n: int) -> str:
    n = int(n)
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            return f"{n / limit:.1f}{suffix}"
    return str(n)


def fmt_cost(usd: float) -> str:
    return f"${usd:.2f}"


def fmt_spark_cost(usd: float) -> str:
    """Compact cost for an in-bar sparkline label — fewer chars than fmt_cost.

    Drops cents once it would only add noise: ``$42`` / ``$123`` for larger
    bars, ``$3.4`` mid-range, ``$0.42`` for sub-dollar. Empty for non-positive
    so the caller can skip zero bars.
    """
    if usd <= 0:
        return ""
    if usd >= 10:
        return f"${usd:.0f}"
    if usd >= 1:
        return f"${usd:.1f}"
    return f"${usd:.2f}"
