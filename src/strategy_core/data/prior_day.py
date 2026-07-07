"""Canonical prior-day PDH/PDL extremes from the local store (the SEED window).

ONE additive helper: walk the store's dated day directories backward from a trading day
and return the most recent prior day's full-session trade extremes, computed by draining
the canonical reader (``DatabentoParquetSource.for_trading_day``, the adopted D-P-16
reader) and accumulating max/min of ``Trade.price_ticks`` over the day's
``[prev 18:00 ET, day 18:00 ET)`` window.

This is the canonical store-walk for prior-day seeding. ``SEED_PARITY_RECON.md`` §5
(Trade-Lab root, 2026-07-06) proved this computation equals QL training's bar-based
``prev_full_hl`` carry TICK-EXACTLY on 7/7 probe days — including the Presidents'/MLK
short sessions, the Christmas empty-window carry-through (12-25 -> 12-24), the
Sunday-file carry (2026-01-11 -> 2026-01-09), and the 2025-11-20 store-hole — with an
independent pyarrow re-computation agreeing on every day including exact trade counts.
A consumer that seeds ``load_prior_day_summary`` from this walk therefore reproduces the
training seed exactly (the SC emission lookup is most-recent-banked-below-D, so any
banked key ``< D`` emits identically; see the recon §4).

Walk semantics (mirrors QL's carry-through): a candidate day whose trading-day window
contains zero trades — an empty directory, a directory without a recognized day file, or
a file whose rows all fall outside the window (e.g. Christmas Day, whose evening reopen
belongs to the NEXT trading day) — is simply skipped, exactly like
``_get_session_hl_for_date``'s empty-day pass-through in QL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from strategy_core.data.databento_parquet import DatabentoParquetSource
from strategy_core.types import Trade

__all__ = ["PriorDayExtremes", "prior_full_day_extremes"]


@dataclass(frozen=True, slots=True)
class PriorDayExtremes:
    """Full-session trade extremes of ``source_day`` (integer ticks, 0.25-pt grid)."""

    source_day: date
    high_ticks: int
    low_ticks: int


def prior_full_day_extremes(
    symbol_dir: Path | str,
    trading_day: date,
    *,
    requested_symbol: str | None = None,
    max_walk_days: int = 10,
) -> PriorDayExtremes | None:
    """Most recent prior store day's full-session extremes, or ``None`` if none found.

    Enumerates the store's dated day directories strictly before ``trading_day``,
    descending, considering at most ``max_walk_days`` candidates. For each candidate the
    canonical reader's trading-day stream is drained (``front_month_only`` default True)
    accumulating max/min of ``Trade.price_ticks``; the first candidate with at least one
    trade in its window wins. Directories that exist but yield no events (no day file,
    or no in-window trades) are empty candidates, not errors. An exhausted walk returns
    ``None`` — the caller's cold-start case, parity-consistent with QL's first window day.
    """
    root = Path(symbol_dir)
    if not root.is_dir():
        return None

    candidates: list[date] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        try:
            day = date.fromisoformat(entry.name)
        except ValueError:
            continue
        if day < trading_day:
            candidates.append(day)

    for candidate in sorted(candidates, reverse=True)[:max_walk_days]:
        try:
            source = DatabentoParquetSource.for_trading_day(
                root, candidate, requested_symbol=requested_symbol
            )
        except FileNotFoundError:
            # A dated directory without a recognized day file — an empty candidate.
            continue
        high: int | None = None
        low: int | None = None
        for event in source.events():
            if isinstance(event, Trade):
                price = event.price_ticks
                if high is None or price > high:
                    high = price
                if low is None or price < low:
                    low = price
        if high is not None and low is not None:
            return PriorDayExtremes(source_day=candidate, high_ticks=high, low_ticks=low)
    return None
