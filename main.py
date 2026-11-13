"""polymarket-nvidia-ceo-forecast-01 entry (Python 3.13, standard library only).

Forecasts the Yes price of every market of Polymarket's "Next CEO of NVIDIA?"
event for the 240 minutes after each checkpoint, as five quantiles per minute.

Method (everything is computed from the case's own price history; no network,
no randomness, deterministic):
  * Median: the last price (persistence). A trend drift was tested on the six
    practice cases and made the loss worse on every variant, so there is none:
    these prices are step-like and mean-reverting around the last print.
  * Spread: per-market sigma from realized 1-minute volatility, blended over
    a short window (last 60 min), a medium window (last 360 min) and a long
    window (last 1440 min), converted from mean absolute change with the
    normal factor sqrt(pi/2), floored and capped. A market that has been
    moving gets wider quantiles; a quiet one gets narrower ones. The floor
    keeps a minimum spread for a market that has been dead quiet, in case
    it jumps in the forecast window.
  * Quantiles: last price + z_tau * sigma * sqrt(h), clamped to [0, 1],
    rounded to 6 decimals — the same random-walk shape as the house baseline,
    with a per-market sigma instead of one fixed sigma 0.0025.

Run: python3 main.py (reads $MAKEFUN_INPUT_DIR or /input, writes
$MAKEFUN_OUTPUT_DIR or /output). One <id>.out per <id>.in, byte-identical
across runs.
"""
import json
import math
import os
from pathlib import Path

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.644854, -0.67449, 0.0, 0.67449, 1.644854]

# Tuning constants (chosen on the six practice cases; see BUILD_LOG.md).
# Practice mean pinball loss: baseline 0.363589, this entry 0.278388.
SIGMA_FLOOR = 0.0006
SIGMA_CAP = 0.015
SIGMA_SHORT_W = 0.5   # weight on the last-60-min window
SIGMA_MED_W = 0.3     # weight on the last-360-min window
SIGMA_LONG_W = 0.2    # weight on the last-1440-min window
JUMP_CAP = 0.02        # one minute's |change| above this counts as this


def price6(x):
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    y = min(1.0, max(0.0, x))
    return math.floor(y * 1e6 + 0.5) / 1e6 + 0.0


def _mean_abs_change(prices, window):
    """Mean |1-min change| over the last `window` minutes, jumps capped."""
    n = len(prices)
    if n < 2:
        return None
    take = min(window, n - 1)
    s = 0.0
    for i in range(n - take, n):
        d = abs(prices[i] - prices[i - 1])
        s += d if d < JUMP_CAP else JUMP_CAP
    return s / take


def _sigma(prices):
    """Per-market sigma (price units per sqrt-minute) from realized vol."""
    if len(prices) < 2:
        return 0.0025
    parts = []
    for window, w in ((60, SIGMA_SHORT_W), (360, SIGMA_MED_W), (1440, SIGMA_LONG_W)):
        m = _mean_abs_change(prices, window)
        if m is not None:
            parts.append((m * math.sqrt(math.pi / 2.0), w))
    if not parts:
        return 0.0025
    tot_w = sum(w for _, w in parts)
    sig = sum(v * w for v, w in parts) / tot_w
    return min(SIGMA_CAP, max(SIGMA_FLOOR, sig))


def forecast_market(prices, horizon):
    """240 rows of five quantiles for one market, median = last price."""
    x = prices[-1]
    sig = _sigma(prices)
    rows = []
    for h in range(1, horizon + 1):
        spread = sig * math.sqrt(h)
        rows.append([price6(x + z * spread) for z in Z])
    return rows


def forecast_case(case):
    """Return the {"forecasts": [...]} object for one parsed case."""
    horizon = case["horizon_minutes"]
    return {"forecasts": [{"id": m["id"], "q": forecast_market(m["prices"], horizon)}
                          for m in case["markets"]]}


def main():
    in_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
    out_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(p.name for p in in_dir.iterdir() if p.name.endswith(".in")):
        case = json.loads((in_dir / name).read_text(encoding="utf-8"))
        result = forecast_case(case)
        (out_dir / (name[:-3] + ".out")).write_text(json.dumps(result) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
