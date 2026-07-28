"""FVG continuous-vs-seeded parity (``structures/fvg.py``).

The theorem the per-day research cache chain rests on: driving detection and
fill-tracking CONTINUOUSLY over N days produces exactly the same gaps, events,
and terminal state as driving each day separately seeded with the prior day's
snapshot (detector tail + registry state). Randomized multi-day walks make the
day-boundary triplets (census E3: real triplets span the 18:00 ET roll) a
routine case rather than a hand-picked one.
"""

from __future__ import annotations

import random
from dataclasses import astuple
from datetime import UTC, date, datetime, timedelta

from strategy_core.candles._ids import make_bar_id
from strategy_core.structures.fvg import (
    FvgDetector,
    FvgRegistry,
    detect_fvgs_over_bars,
)
from strategy_core.types import Bar, BarKind, CloseReason

_DAY0 = date(2026, 1, 5)
_DAY_START = datetime(2026, 1, 4, 23, 0, tzinfo=UTC)
_BARS_PER_DAY = 240


def _walk_bars(seed: int, days: int, *, tf: int = 60) -> list[list[Bar]]:
    """Per-day lists of one-timeframe bars from a seeded jumpy random walk
    (large jumps make three-bar gaps common; occasional revisits fill them)."""
    rng = random.Random(seed)
    price = 20_000
    out: list[list[Bar]] = []
    for d in range(days):
        day = _DAY0 + timedelta(days=d)
        day_bars: list[Bar] = []
        for i in range(_BARS_PER_DAY):
            jump = rng.choice((-12, -6, -2, 0, 2, 6, 12))
            price += jump
            o = price + rng.randint(-2, 2)
            c = price + rng.randint(-2, 2)
            h = max(o, c) + rng.randint(0, 3)
            low = min(o, c) - rng.randint(0, 3)
            open_ts = _DAY_START + timedelta(days=d, seconds=tf * i)
            day_bars.append(
                Bar(
                    timeframe_ticks=tf,
                    trading_day=day,
                    bar_index=i,
                    bar_id=make_bar_id(tf, day, i, BarKind.TIME),
                    open_ts_utc=open_ts,
                    close_ts_utc=open_ts + timedelta(seconds=tf - 1),
                    open_ticks=o,
                    high_ticks=h,
                    low_ticks=low,
                    close_ticks=c,
                    volume=rng.randint(1, 50),
                    trade_count=rng.randint(1, 20),
                    is_complete=i < _BARS_PER_DAY - 1,
                    is_partial=i == _BARS_PER_DAY - 1,
                    close_reason=(
                        CloseReason.COMPLETE if i < _BARS_PER_DAY - 1 else CloseReason.END_OF_DAY
                    ),
                    kind=BarKind.TIME,
                )
            )
        out.append(day_bars)
    return out


def test_detection_continuous_equals_per_day_seeded_tails() -> None:
    for seed in (7, 21, 99):
        by_day = _walk_bars(seed, days=3)
        flat = [b for day in by_day for b in day]
        continuous = detect_fvgs_over_bars(flat, timeframe_seconds=60)
        assert continuous, "walk must produce gaps for the parity to be meaningful"
        seeded: list = []
        det = FvgDetector(60)
        tail: tuple[Bar, ...] = ()
        for day_bars in by_day:
            seeded.extend(detect_fvgs_over_bars(day_bars, timeframe_seconds=60, tail=tail))
            det = FvgDetector.from_tail(60, tail)
            for bar in day_bars:
                det.on_bar_closed(bar)
            tail = det.snapshot_tail()
        assert [astuple(g) for g in seeded] == [astuple(g) for g in continuous]
        cross_day = [g for g in continuous if g.a_bar_id.split(":")[1] != str(g.trading_day)]
        assert cross_day, "at least one triplet must span a day boundary"


def test_registry_continuous_equals_snapshot_resumed() -> None:
    for seed in (7, 21, 99):
        by_day = _walk_bars(seed, days=3)
        flat = [b for day in by_day for b in day]

        cont_reg = FvgRegistry(timeframe_seconds=60, max_live=64)
        cont_det = FvgDetector(60)
        cont_events = []
        for bar in flat:
            gap = cont_det.on_bar_closed(bar)
            if gap is not None:
                cont_events.extend(cont_reg.add(gap))
            cont_events.extend(cont_reg.on_execution_bar(bar))

        seed_reg = FvgRegistry(timeframe_seconds=60, max_live=64)
        seed_det = FvgDetector(60)
        seed_events = []
        for day_bars in by_day:
            snap = seed_reg.snapshot(detector_tail=seed_det.snapshot_tail())
            seed_reg = FvgRegistry.from_snapshot(snap)
            seed_det = FvgDetector.from_tail(60, snap.detector_tail)
            for bar in day_bars:
                gap = seed_det.on_bar_closed(bar)
                if gap is not None:
                    seed_events.extend(seed_reg.add(gap))
                seed_events.extend(seed_reg.on_execution_bar(bar))

        assert [astuple(e) for e in seed_events] == [astuple(e) for e in cont_events]
        assert seed_reg.snapshot() == cont_reg.snapshot()
        kinds = {e.kind for e in cont_events}
        assert "first_touch" in kinds and "filled" in kinds
