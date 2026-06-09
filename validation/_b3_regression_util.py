"""Shared digest + seeding helpers for the B3 plugin-path REGRESSION gates.

B3 removed the flag-OFF / None path, so the real-data parity gates (go-live, multi-day
reset) can no longer build a comparator runtime. They are repurposed into plugin-path
REGRESSION tests that re-run the plugin path and assert against digests FROZEN from the
final green off-vs-on run — captured while ``plugin == None`` was still provable, so the
frozen digests are canonical-correct. After the removal, only the dead None branch is gone;
the plugin path itself is byte-unchanged, so re-running it must reproduce the digests.

This module owns the digest computation, the EXACT seeding, and the day lists that BOTH the
one-time freeze and the regression tests use — so the freeze and the checks cannot drift.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from strategy_core.types import Level, Side

# ── fixtures ──────────────────────────────────────────────────────────────────
FIXTURE_DIR = Path(__file__).resolve().parent / "_fixtures" / "b3_regression"

# ── day lists (single source for freeze + regression) ─────────────────────────
#: Go-live days — independent (a FRESH runtime per day), synthetic prior-day PDH/PDL placed
#: inside the day's range. Mirrors the original go-live SAMPLE_DAYS.
GOLIVE_DAYS = ["2025-07-15", "2025-07-07"]
#: Multi-day reset-bracketed sequence — 9 consecutive trading days, ONE runtime rolled
#: production-style (reset + reseed from the preceding processed day) at each boundary.
MULTIDAY_DAYS = [
    "2025-07-10", "2025-07-11", "2025-07-14", "2025-07-15", "2025-07-16",
    "2025-07-17", "2025-07-18", "2025-07-21", "2025-07-22",
]

#: Static reference level availability — ungated/touchable; a concrete past instant keeps
#: the seed unambiguous (``build_zones`` ignores None constituents in its merge max()).
STATIC_AVAILABLE_FROM = datetime(2000, 1, 1, tzinfo=UTC)


# ── digest ────────────────────────────────────────────────────────────────────
def _canon(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str).encode()


class SeqDigest:
    """Rolling sha256 over a per-trade ``RuntimeUpdate.to_dict()`` sequence + trade/touch counts.

    The sha is order- and content-sensitive: any single-trade divergence in the serialized
    update sequence flips ``hexdigest()``. So digest equality ⟺ identical per-trade
    ``to_dict()`` streams (modulo a negligible sha256 collision) — the strong regression anchor.
    """

    __slots__ = ("_h", "n", "touches")

    def __init__(self) -> None:
        self._h = hashlib.sha256()
        self.n = 0
        self.touches = 0

    def add(self, update) -> None:
        self._h.update(_canon(update.to_dict()))
        self.n += 1
        self.touches += len(update.touches)

    def hexdigest(self) -> str:
        return self._h.hexdigest()


def snapshot_sha256(snapshot) -> str:
    return hashlib.sha256(_canon(snapshot.to_dict())).hexdigest()


# ── seeding (identical for freeze + regression) ───────────────────────────────
def golive_synthetic_pdh_pdl(trades) -> tuple[int, int]:
    """The go-live seeding: prior-day PDH/PDL placed INSIDE the day's range so they are
    touchable. Byte-for-byte the original ``run_day`` computation."""
    ticks = [t.price_ticks for t in trades]
    lo, hi = min(ticks), max(ticks)
    span = hi - lo
    return lo + round(0.66 * span), lo + round(0.33 * span)


def day_extremes_ticks(trades) -> tuple[int, int]:
    """The processed day's high/low in ticks — the faithful PDH/PDL the NEXT day rolls in."""
    ticks = [t.price_ticks for t in trades]
    return max(ticks), min(ticks)


def static_reference_levels(high_ticks: int, low_ticks: int, tick_size: float) -> tuple[Level, ...]:
    """One touchable static reference at the prior day's midpoint (the B3-prep reseed)."""
    mid = (high_ticks + low_ticks) // 2
    return (Level("prior_session_mid", mid * tick_size, Side.LOW, STATIC_AVAILABLE_FROM),)


# ── per-day digest runners (ONE runtime; shared by freeze cross-check + regression) ──
def golive_day_digest(runtime, day, read_trades, window) -> dict | None:
    """Build the per-day digest for ONE runtime under the go-live seeding (fresh runtime,
    synthetic inside-range PDH/PDL). Returns None if the day has no store data."""
    trades = read_trades(day)
    if not trades:
        return None
    prev, _, _ = window(day)
    pdh, pdl = golive_synthetic_pdh_pdl(trades)
    runtime.load_prior_day_summary(prev, high_ticks=pdh, low_ticks=pdl)
    dig = SeqDigest()
    for tr in trades:
        dig.add(runtime.process_event(tr))
    return {
        "day": day,
        "n_trades": dig.n,
        "touches": dig.touches,
        "seq_sha256": dig.hexdigest(),
        "snapshot_sha256": snapshot_sha256(runtime.snapshot()),
    }


def multiday_digests(runtime, days, read_trades, tick_size) -> list[dict]:
    """Roll ONE runtime through the reset-bracketed multi-day sequence (reset + reseed from
    the PRECEDING processed day at each boundary) and return per-day digests. Absent days are
    marked skipped; the sequence is chain-dependent, so callers requiring reproducibility must
    ensure ALL days are present."""
    out: list[dict] = []
    prev_extremes: tuple[int, int, date] | None = None
    for i, day in enumerate(days):
        trades = read_trades(day)
        if not trades:
            out.append({"day": day, "skip": True})
            continue
        if i > 0 and prev_extremes is not None:
            runtime.reset()
            ph, pl, pday = prev_extremes
            runtime.load_prior_day_summary(pday, high_ticks=ph, low_ticks=pl)
            runtime.set_static_levels(static_reference_levels(ph, pl, tick_size))
        dig = SeqDigest()
        for tr in trades:
            dig.add(runtime.process_event(tr))
        out.append({
            "day": day,
            "skip": False,
            "n_trades": dig.n,
            "touches": dig.touches,
            "seq_sha256": dig.hexdigest(),
            "snapshot_sha256": snapshot_sha256(runtime.snapshot()),
        })
        prev_extremes = (*day_extremes_ticks(trades), date.fromisoformat(day))
    return out


# ── fixture IO ────────────────────────────────────────────────────────────────
def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def save_fixture(name: str, data: dict) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
