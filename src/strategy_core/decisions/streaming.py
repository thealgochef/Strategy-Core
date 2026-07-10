"""Streaming honest decision-time outcome resolution (D1a).

The INCREMENTAL equivalent of ``decisions/honest_entry.resolve_honest_outcome``
over the same ``decisions/outcomes`` kernel, for the live/replay serving path: a
batch caller hands ``resolve_honest_outcome`` the touch + the full day's bars at
once; a streaming caller registers a touch when its decision instant has passed
and then feeds closed bars one at a time. Rule-for-rule the two are the same
honest decision-time rule (see ``honest_entry.py``):

  1. decision_ts = touch bar close + ``decision_offset_minutes``.
  2. DROP (flatten) if decision_ts in ET is at/after ``flatten_time`` (non-strict).
  3. DROP (cutoff) if decision_ts is at/after the trading-day ``rth_end`` cutoff
     (non-strict; cutoff anchored on the TOUCH's trading day).
  4. entry = ``trade_price_at(decision_ts)`` (the injected realistic front-month
     trade-print point query — live: the runtime trade ring; batch: the parquet
     reference). DROP (no_fill) if ``None``.
  5. forward bars: closes STRICTLY inside (decision_ts, rth_cutoff); excursion +
     ``classify_mae_first(forced=False)`` per bar, exactly ``outcomes.py:180-205``.
  6. cutoff passes with zero in-window bars ever seen -> DROP (no_forward,
     carrying the entry); cutoff passes unresolved -> DROP (no_resolution,
     carrying the 4dp extremes + ``bars_to_resolution=-1``, mirroring the batch
     ``OutcomeResult`` no_resolution arm).

CALLER CONTRACT — ``register()`` MUST be invoked at-or-after the setup's
decision instant (the caller's event clock has passed ``touch_bar_ts +
offset``), because the entry point query reads the prints AT the decision
instant: a live trade ring only holds what has already printed. Trade-Lab's
wiring guarantees this structurally (predictions are produced when the
observation window — the same offset — expires); a replay harness registers a
pending touch on the first trade at/after its decision instant.

Resolved bar-inclusion rule (gate-A arbitrated, ``validation/
test_d1_streaming_vs_batch_parity.py``): the resolver consumes EVERY closed bar
of the forward timeframe the caller feeds it — including END_OF_DAY partial
freezes — exactly as the batch path consumes every bar of its ``day_bars`` list;
membership in the forward window is decided ONLY by the strict
``(decision_ts, rth_cutoff)`` close-instant bounds (``honest_entry.py:151-155``).
On the real store this makes partial bars unreachable in practice: END_OF_DAY
partials freeze at the 18:00 ET trading-day roll, after the 17:00 ET cutoff that
strictly upper-bounds every forward window.

No correctness concept lives here (SC-side); predicted-vs-actual comparison is
the consumer's concern. ``StreamResolution`` carries the entry price + decision
instant alongside the kernel ``OutcomeResult`` because the serving consumer
(and the parity/characterization gates) need the fill the excursions were
anchored on.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from strategy_core.constants import (
    DECISION_OFFSET_MINUTES,
    FLATTEN_TIME,
    LABEL_ENCODING,
    RTH_END,
    SESSION_TIMEZONE,
)
from strategy_core.decisions.outcomes import OutcomeResult, classify_mae_first
from strategy_core.types import Bar, Direction

__all__ = ["OpenSetupView", "StreamDrop", "StreamResolution", "StreamingHonestResolver"]

#: The bounded entry-print lookback (minutes) — the reference semantics of
#: ``validation/decision_diff_harness.py:594-616`` (``ENTRY_LOOKBACK_MIN``) and the
#: CQL ``_trade_price_at``: the most recent qualifying print AT/BEFORE the decision
#: instant, no older than this.
TRADE_PRICE_LOOKBACK_MINUTES = 30


@dataclass(frozen=True, slots=True)
class StreamDrop:
    """A registered setup that yields NO tradeable outcome on the streaming path.

    ``reason`` mirrors ``HonestEntryDrop`` plus the streaming-only terminal arm:

    * ``"flatten"`` / ``"cutoff"`` / ``"no_fill"`` — registration-time drops,
      exactly ``honest_entry.py``'s firing order; ``entry_price`` is ``None``.
    * ``"no_forward"`` — the cutoff passed with zero in-window forward bars ever
      seen; carries the resolved ``entry_price`` (mirrors ``HonestEntryDrop``).
    * ``"no_resolution"`` — the cutoff passed with in-window bars consumed but
      neither barrier hit; carries ``entry_price``, the 4dp running extremes,
      and ``bars_to_resolution=-1`` (mirrors the batch ``OutcomeResult``
      no_resolution arm, which D1's ratified semantics treat as a drop).
    """

    reason: str
    key: object
    decision_ts_utc: datetime
    entry_price: float | None = None
    max_mfe: float | None = None
    max_mae: float | None = None
    bars_to_resolution: int | None = None


@dataclass(frozen=True, slots=True)
class StreamResolution:
    """A resolved setup: the kernel ``OutcomeResult`` + the fill it was anchored on.

    ``resolved_ts_utc`` is the RESOLVING bar's ``close_ts_utc`` — the instant the
    barrier classification fired (stamped by ``on_bar``). DELIBERATE ASYMMETRY with
    the batch path: the kernel ``OutcomeResult`` carries no timestamp because a
    batch caller indexes ``bars_to_resolution`` into the ``day_bars`` list it
    already holds; a streaming consumer sees each bar once, so the envelope must
    carry the close instant or it is lost. Gate A therefore cannot check this field
    against batch — it is pinned by the resolution-path unit test in
    ``tests/test_streaming_resolver.py`` instead.
    """

    key: object
    decision_ts_utc: datetime
    entry_price: float
    resolved_ts_utc: datetime
    result: OutcomeResult


@dataclass(frozen=True, slots=True)
class OpenSetupView:
    """Read-only projection of one open setup's registration-time economics (EXEC P1).

    The honest fill and the barrier prices the resolver already implied at
    registration, surfaced for OBSERVER consumers (Trade-Lab's paper-execution
    tracker): the fill exists at ``register()`` but previously surfaced only at
    resolution/drop. ``prediction_id`` is the caller's registration ``key``
    (Trade-Lab registers the prediction id). ``entry_ts_utc`` is the decision
    instant the fill was anchored at.

    Prices are integer TICKS of the resolver's ``tick_size``: the fill comes off
    the tick grid (a real print) and the production tp/sl offsets are tick
    multiples, so ``round()`` only absorbs float representation noise. Barriers
    follow the excursion rule exactly — LONG tp = entry + tp_points, sl =
    entry - sl_points; SHORT mirrored. Both SL-side labels (trap and
    blowthrough) share the one SL barrier; MAE-first arbitration is the
    resolver's concern, not the view's.

    Each ``open_setups()`` call constructs views fresh from the private state,
    so an already-returned tuple is a point-in-time snapshot: later
    ``on_bar``/``flush``/``reset`` calls never retro-change it.
    """

    prediction_id: object
    entry_price_ticks: int
    entry_ts_utc: datetime
    direction: Direction
    tp_price_ticks: int
    sl_price_ticks: int


@dataclass(slots=True)
class _OpenSetup:
    key: object
    direction: Direction
    decision_ts_utc: datetime
    rth_cutoff: datetime
    entry_points: float
    max_mfe: float = field(default=0.0)
    max_mae: float = field(default=0.0)
    bars_seen: int = field(default=0)


def _as_direction(direction: Direction | str) -> Direction:
    # Accept the engine enum or its string forms ("LONG"/"long"); prefix-match is the
    # established convention (touch plugin FixedPointsBarrier._is_long).
    if isinstance(direction, Direction):
        return direction
    return Direction.LONG if str(direction).upper().startswith("L") else Direction.SHORT


class StreamingHonestResolver:
    """Incremental honest decision-time outcome resolution over closed forward bars.

    One resolver instance serves one runtime/contract; ``reset()`` clears all open
    setups (runtime reset / model hot-swap). Construction fails loud when the
    forward timeframe is not among the runtime's configured timeframes — a
    mismatch would otherwise mean NO bar ever matches and every setup silently
    rides to its cutoff (the D-window recon's silent-never-resolve hole).
    """

    def __init__(
        self,
        *,
        forward_timeframe_ticks: int,
        tick_size: float,
        tp_points: float,
        sl_points: float,
        trap_mfe_min: float,
        trade_price_at: Callable[[datetime], float | None],
        decision_offset_minutes: int = DECISION_OFFSET_MINUTES,
        flatten_time: time = FLATTEN_TIME,
        rth_end: time = RTH_END,
        timezone: str = SESSION_TIMEZONE,
        available_timeframes: Sequence[int] | None = None,
    ) -> None:
        if available_timeframes is not None and forward_timeframe_ticks not in tuple(
            available_timeframes
        ):
            raise ValueError(
                f"forward timeframe {forward_timeframe_ticks}t is not among the runtime's "
                f"configured timeframes {tuple(available_timeframes)}; no bar would ever "
                "advance the resolver (fail loud at activation, not silently never-resolve)"
            )
        self._forward_timeframe_ticks = int(forward_timeframe_ticks)
        self._tick_size = float(tick_size)
        self._tp_points = float(tp_points)
        self._sl_points = float(sl_points)
        self._trap_mfe_min = float(trap_mfe_min)
        self._trade_price_at = trade_price_at
        self._decision_offset = timedelta(minutes=decision_offset_minutes)
        self._flatten_time = flatten_time
        self._rth_end = rth_end
        self._tz = ZoneInfo(timezone)
        self._open: list[_OpenSetup] = []

    @property
    def forward_timeframe_ticks(self) -> int:
        return self._forward_timeframe_ticks

    @property
    def open_count(self) -> int:
        return len(self._open)

    def open_setups(self) -> tuple[OpenSetupView, ...]:
        """Snapshot every open setup as a read-only :class:`OpenSetupView`.

        Additive observer accessor (EXEC P1): no mutation, no influence on
        registration/advancement/resolution. See the view docstring for field
        semantics; ordering follows registration order (the ``_open`` list).
        """

        tick = self._tick_size
        views: list[OpenSetupView] = []
        for setup in self._open:
            if setup.direction is Direction.LONG:
                tp_price = setup.entry_points + self._tp_points
                sl_price = setup.entry_points - self._sl_points
            else:  # SHORT
                tp_price = setup.entry_points - self._tp_points
                sl_price = setup.entry_points + self._sl_points
            views.append(
                OpenSetupView(
                    prediction_id=setup.key,
                    entry_price_ticks=round(setup.entry_points / tick),
                    entry_ts_utc=setup.decision_ts_utc,
                    direction=setup.direction,
                    tp_price_ticks=round(tp_price / tick),
                    sl_price_ticks=round(sl_price / tick),
                )
            )
        return tuple(views)

    def register(
        self,
        key: object,
        *,
        touch_bar_ts_utc: datetime,
        trading_day: date,
        direction: Direction | str,
    ) -> StreamDrop | None:
        """Register one touch-anchored setup; returns its registration-time drop, if any.

        Inputs are the TOUCH's bar-close instant (the decision anchor — NOT a
        downstream prediction/observation timestamp) and the touch's trading day
        (anchors the rth_end cutoff). The drop checks run in ``honest_entry``'s
        exact firing order: flatten -> cutoff -> entry (no_fill). MUST be called
        at-or-after the decision instant (see the module docstring's caller
        contract). Returns ``None`` when the setup is live (tracked until a
        barrier resolves it or its cutoff passes).
        """
        decision_ts_utc = touch_bar_ts_utc + self._decision_offset
        rth_cutoff = datetime.combine(trading_day, self._rth_end, tzinfo=self._tz)
        # W1 P2a: flatten anchored to the setup's trading day (absolute instant),
        # mirroring honest_entry — evening next-trading-day setups are not embargoed.
        flatten_cutoff = datetime.combine(trading_day, self._flatten_time, tzinfo=self._tz)

        if decision_ts_utc >= flatten_cutoff:
            return StreamDrop(reason="flatten", key=key, decision_ts_utc=decision_ts_utc)
        if decision_ts_utc >= rth_cutoff:
            return StreamDrop(reason="cutoff", key=key, decision_ts_utc=decision_ts_utc)
        entry_price = self._trade_price_at(decision_ts_utc)
        if entry_price is None:
            return StreamDrop(reason="no_fill", key=key, decision_ts_utc=decision_ts_utc)

        self._open.append(
            _OpenSetup(
                key=key,
                direction=_as_direction(direction),
                decision_ts_utc=decision_ts_utc,
                rth_cutoff=rth_cutoff,
                entry_points=float(entry_price),
            )
        )
        return None

    def on_bar(self, bar: Bar) -> tuple[StreamResolution | StreamDrop, ...]:
        """Advance every open setup with one just-closed bar.

        Bars whose ``timeframe_ticks`` differ from the forward timeframe are
        ignored. A bar closing at/after a setup's cutoff finalizes that setup
        (no_forward / no_resolution) WITHOUT contributing its range — the batch
        forward window is strictly ``close < rth_cutoff`` (``honest_entry.py:154``),
        so a cutoff-straddling bar's extremes never count.
        """
        if bar.timeframe_ticks != self._forward_timeframe_ticks:
            return ()

        emitted: list[StreamResolution | StreamDrop] = []
        still_open: list[_OpenSetup] = []
        for setup in self._open:
            if bar.close_ts_utc >= setup.rth_cutoff:
                emitted.append(self._finalize(setup))
                continue
            if bar.close_ts_utc <= setup.decision_ts_utc:
                still_open.append(setup)
                continue

            # Exactly outcomes.py:180-205, incrementally: per-bar excursions off the
            # bar's high/low, running maxima updated BEFORE classification.
            high = bar.high_ticks * self._tick_size
            low = bar.low_ticks * self._tick_size
            if setup.direction == Direction.LONG:
                bar_mfe = high - setup.entry_points
                bar_mae = setup.entry_points - low
            else:  # SHORT
                bar_mfe = setup.entry_points - low
                bar_mae = high - setup.entry_points
            setup.max_mfe = max(setup.max_mfe, bar_mfe)
            setup.max_mae = max(setup.max_mae, bar_mae)
            setup.bars_seen += 1

            decided = classify_mae_first(
                setup.max_mfe,
                setup.max_mae,
                tp_points=self._tp_points,
                sl_points=self._sl_points,
                trap_mfe_min=self._trap_mfe_min,
                forced=False,
            )
            if decided is None:
                still_open.append(setup)
                continue
            emitted.append(
                StreamResolution(
                    key=setup.key,
                    decision_ts_utc=setup.decision_ts_utc,
                    entry_price=setup.entry_points,
                    resolved_ts_utc=bar.close_ts_utc,
                    result=OutcomeResult(
                        label=decided,
                        label_encoded=LABEL_ENCODING.get(decided),
                        max_mfe=round(setup.max_mfe, 4),
                        max_mae=round(setup.max_mae, 4),
                        # The batch resolver reports the ZERO-BASED index of the
                        # resolving bar within the forward window.
                        bars_to_resolution=setup.bars_seen - 1,
                    ),
                )
            )
        self._open = still_open
        return tuple(emitted)

    def flush(self, now_ts_utc: datetime) -> tuple[StreamDrop, ...]:
        """Finalize every open setup whose cutoff is at/before ``now_ts_utc``.

        The explicit cutoff signal for callers whose bar stream stops before any
        bar closes at/after a setup's cutoff (replay day-end, session shutdown):
        on the real store, prints halt at 17:00 ET — the cutoff itself — so the
        finalizing signal can never arrive as a forward-timeframe bar close
        within the same trading day.
        """
        emitted: list[StreamDrop] = []
        still_open: list[_OpenSetup] = []
        for setup in self._open:
            if setup.rth_cutoff <= now_ts_utc:
                emitted.append(self._finalize(setup))
            else:
                still_open.append(setup)
        self._open = still_open
        return tuple(emitted)

    def reset(self) -> None:
        """Drop all open setups (runtime reset / model hot-swap)."""
        self._open.clear()

    @staticmethod
    def _finalize(setup: _OpenSetup) -> StreamDrop:
        if setup.bars_seen == 0:
            return StreamDrop(
                reason="no_forward",
                key=setup.key,
                decision_ts_utc=setup.decision_ts_utc,
                entry_price=setup.entry_points,
            )
        return StreamDrop(
            reason="no_resolution",
            key=setup.key,
            decision_ts_utc=setup.decision_ts_utc,
            entry_price=setup.entry_points,
            max_mfe=round(setup.max_mfe, 4),
            max_mae=round(setup.max_mae, 4),
            bars_to_resolution=-1,
        )
