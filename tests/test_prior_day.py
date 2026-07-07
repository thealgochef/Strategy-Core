"""SEED window: the canonical prior-day store-walk (``strategy_core.data.prior_day``).

Real-store probes assert the SEED_PARITY_RECON.md §5 oracles exactly (the recon's
computed ground truth, produced by this same reader path and cross-checked against an
independent pyarrow computation and QL's own carry). Skip-guarded on store presence like
the existing real-data tests (env override + sibling-checkout default, the QL e2e
convention).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from strategy_core.data.prior_day import PriorDayExtremes, prior_full_day_extremes

ENV_NQ_STORE = "STRATEGY_CORE_NQ_STORE"
_DEFAULT_NQ_STORE = (
    Path(__file__).resolve().parents[1].parent / "Claude-Quant-Lab" / "data" / "databento" / "NQ"
)


def _resolve_store() -> Path:
    override = os.environ.get(ENV_NQ_STORE)
    if override:
        return Path(override).expanduser()
    return _DEFAULT_NQ_STORE


STORE = _resolve_store()

# The three recon probes exercise distinct carry-through shapes; guard on the exact
# directories each walk visits so a partial store skips rather than fails.
_PROBE_DIRS = ["2026-01-11", "2026-01-09", "2025-12-25", "2025-12-24", "2025-11-19"]
_HAVE_STORE = STORE.is_dir() and all((STORE / d).is_dir() for d in _PROBE_DIRS)

real_store = pytest.mark.skipif(
    not _HAVE_STORE, reason=f"Databento NQ store with the recon probe days not present at {STORE}"
)


# ── Real-store probes: the SEED_PARITY_RECON §5 oracles ──────────────────────
@real_store
def test_sunday_file_carry_through_2026_01_12() -> None:
    """2026-01-11 exists but holds zero in-window trades -> the walk lands on 01-09."""
    extremes = prior_full_day_extremes(STORE, date(2026, 1, 12), requested_symbol="NQ")
    assert extremes == PriorDayExtremes(
        source_day=date(2026, 1, 9), high_ticks=103942, low_ticks=102462
    )


@real_store
def test_christmas_empty_window_carry_through_2025_12_26() -> None:
    """12-25's file rows are the evening reopen (next trading day) -> walk lands on 12-24."""
    extremes = prior_full_day_extremes(STORE, date(2025, 12, 26), requested_symbol="NQ")
    assert extremes == PriorDayExtremes(
        source_day=date(2025, 12, 24), high_ticks=103568, low_ticks=103110
    )


@real_store
def test_store_hole_carry_through_2025_11_21() -> None:
    """2025-11-20 is a dated dir with no day file (the store hole) -> walk lands on 11-19."""
    extremes = prior_full_day_extremes(STORE, date(2025, 11, 21), requested_symbol="NQ")
    assert extremes == PriorDayExtremes(
        source_day=date(2025, 11, 19), high_ticks=99952, low_ticks=97780
    )


# ── Synthetic stores ──────────────────────────────────────────────────────────
def _write_trades(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _trade_row(ts: datetime, price: float, *, seq: int = 1) -> dict:
    return {"ts_event": ts, "price": price, "size": 1, "side": "B", "sequence": seq}


def test_walk_exhaustion_returns_none(tmp_path: Path) -> None:
    """max_walk_days binds: 10 empty candidates hide a tradeable day just beyond them."""
    root = tmp_path / "NQ"
    # Ten dated dirs with no day file (empty candidates), immediately before the day.
    for dom in range(10, 20):
        (root / f"2026-03-{dom:02d}").mkdir(parents=True)
    # An eleventh candidate (older than all of the above) that HAS a trade in-window:
    # 14:00 UTC on 2026-03-09 lies inside trading day 2026-03-09 ([03-08 18:00 ET, ...)).
    _write_trades(
        root / "2026-03-09" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 9, 14, 0, tzinfo=UTC), 17000.25)],
    )
    assert prior_full_day_extremes(root, date(2026, 3, 20), requested_symbol="NQ") is None
    # Widening the walk by one reaches it — the walk itself works end-to-end.
    extremes = prior_full_day_extremes(
        root, date(2026, 3, 20), requested_symbol="NQ", max_walk_days=11
    )
    assert extremes == PriorDayExtremes(
        source_day=date(2026, 3, 9), high_ticks=68001, low_ticks=68001
    )


def test_single_day_store_first_day_returns_none(tmp_path: Path) -> None:
    """Replaying the store's first (only) day: no prior dated dir -> None."""
    root = tmp_path / "NQ"
    _write_trades(
        root / "2026-03-09" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 9, 14, 0, tzinfo=UTC), 17000.25)],
    )
    assert prior_full_day_extremes(root, date(2026, 3, 9), requested_symbol="NQ") is None


def test_out_of_window_rows_candidate_carries_through(tmp_path: Path) -> None:
    """The Christmas shape, synthetically: the nearest candidate's file rows all fall
    AT/AFTER its 18:00-ET window end (they belong to the NEXT trading day), so the walk
    must continue to the older candidate — not return None."""
    root = tmp_path / "NQ"
    # Trading day 2026-03-12 window ends 03-12 18:00 EDT = 22:00 UTC; a 23:00 UTC row
    # is outside it (it belongs to trading day 03-13).
    _write_trades(
        root / "2026-03-12" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 12, 23, 0, tzinfo=UTC), 17010.0)],
    )
    _write_trades(
        root / "2026-03-11" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 11, 14, 0, tzinfo=UTC), 17002.0)],
    )
    extremes = prior_full_day_extremes(root, date(2026, 3, 13), requested_symbol="NQ")
    assert extremes == PriorDayExtremes(
        source_day=date(2026, 3, 11), high_ticks=68008, low_ticks=68008
    )


def test_quotes_only_candidate_carries_through(tmp_path: Path) -> None:
    """A candidate whose day file yields events but no Trades (book updates only) is an
    empty candidate: the walk continues to the older trade-bearing day."""
    root = tmp_path / "NQ"
    quote_row = {
        "ts_event": datetime(2026, 3, 12, 14, 0, tzinfo=UTC),
        "action": "A",
        "price": 17010.0,
        "size": 1,
        "side": "B",
        "bid_px_00": 17009.75,
        "ask_px_00": 17010.0,
        "bid_sz_00": 5,
        "ask_sz_00": 5,
        "sequence": 1,
    }
    (root / "2026-03-12").mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist([quote_row]), root / "2026-03-12" / "mbp10.parquet")
    _write_trades(
        root / "2026-03-11" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 11, 14, 0, tzinfo=UTC), 17002.0)],
    )
    extremes = prior_full_day_extremes(root, date(2026, 3, 13), requested_symbol="NQ")
    assert extremes == PriorDayExtremes(
        source_day=date(2026, 3, 11), high_ticks=68008, low_ticks=68008
    )


def test_non_positive_max_walk_days_walks_nothing(tmp_path: Path) -> None:
    root = tmp_path / "NQ"
    _write_trades(
        root / "2026-03-09" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 9, 14, 0, tzinfo=UTC), 17000.25)],
    )
    for n in (0, -1):
        assert (
            prior_full_day_extremes(root, date(2026, 3, 10), requested_symbol="NQ", max_walk_days=n)
            is None
        )


def test_non_strict_iso_dir_names_are_not_candidates(tmp_path: Path) -> None:
    """date.fromisoformat also parses compact (20260309) and ISO-week forms; those name
    a DIFFERENT directory than day.isoformat() and must not consume walk slots."""
    root = tmp_path / "NQ"
    _write_trades(
        root / "20260309" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 9, 14, 0, tzinfo=UTC), 17000.25)],
    )
    assert prior_full_day_extremes(root, date(2026, 3, 10), requested_symbol="NQ") is None
    # The strict form of the same day IS a candidate.
    _write_trades(
        root / "2026-03-09" / "trades.parquet",
        [_trade_row(datetime(2026, 3, 9, 14, 0, tzinfo=UTC), 17000.25)],
    )
    extremes = prior_full_day_extremes(root, date(2026, 3, 10), requested_symbol="NQ")
    assert extremes == PriorDayExtremes(
        source_day=date(2026, 3, 9), high_ticks=68001, low_ticks=68001
    )
