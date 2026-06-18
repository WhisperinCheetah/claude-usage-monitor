"""Map recent spend to a gray->green heat color and a gradient indicator icon.

The top-bar indicator is tinted by how much was spent in a fixed rolling window
(``COLOR_WINDOW_SECONDS``): gray means no recent usage, full green means spend
at or above ``COLOR_MAX_SPEND`` over that window. These constants are the knobs
to tune the scale.
"""

COLOR_WINDOW_SECONDS = 600     # color reflects spend over the last 10 minutes
COLOR_MAX_SPEND = 6.0          # USD over the window that saturates to full green
N_BUCKETS = 16                 # number of pre-rendered gradient steps

_IDLE_RGB = (90, 90, 90)       # gray = no recent usage
_HOT_RGB = (46, 204, 113)      # green = high recent usage


def intensity(spend: float) -> float:
    """Normalize spend over the window to 0..1."""
    if spend <= 0 or COLOR_MAX_SPEND <= 0:
        return 0.0
    return min(spend / COLOR_MAX_SPEND, 1.0)


def bucket(spend: float, n: int = N_BUCKETS) -> int:
    """Index of the pre-rendered gradient step for a given spend."""
    return round(intensity(spend) * (n - 1))


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def color_hex(t: float) -> str:
    """Gray->green hex color for t in 0..1."""
    t = max(0.0, min(t, 1.0))
    r = _lerp(_IDLE_RGB[0], _HOT_RGB[0], t)
    g = _lerp(_IDLE_RGB[1], _HOT_RGB[1], t)
    b = _lerp(_IDLE_RGB[2], _HOT_RGB[2], t)
    return f"#{r:02x}{g:02x}{b:02x}"


def bucket_color_hex(i: int, n: int = N_BUCKETS) -> str:
    if n <= 1:
        return color_hex(1.0)
    return color_hex(i / (n - 1))


def gradient_svg(fill_hex: str) -> str:
    """A filled rounded-square icon tinted `fill_hex`, dark chart line + '$'."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" '
        'viewBox="0 0 128 128">'
        f'<rect x="8" y="8" width="112" height="112" rx="24" fill="{fill_hex}"/>'
        '<polyline points="22,92 50,66 74,78 106,38" fill="none" stroke="#1e1e1e" '
        'stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="106" cy="38" r="8" fill="#1e1e1e"/>'
        '<text x="22" y="44" font-family="sans-serif" font-size="34" '
        'font-weight="bold" fill="#1e1e1e">$</text>'
        '</svg>'
    )
