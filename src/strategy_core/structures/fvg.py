"""Fair-value gap (FVG) detection, predicates, and fill-tracking registry.

Canonical construction (ratified from the FVG census, whose conventions this
module promotes verbatim — the census script is archived at
``Claude-Quant-Lab/docs/archive/windows/scratch_root_census.py``):

* THREE-BAR GEOMETRY, STRICT INEQUALITIES. With ``A`` = the bar two closes ago
  and ``C`` = the bar closing now (``B`` between them):
  bullish gap iff ``A.high_ticks < C.low_ticks`` (interval ``[A.high, C.low]``);
  bearish gap iff ``A.low_ticks  > C.high_ticks`` (interval ``[C.high, A.low]``).
  Strictness means every gap is >= 1 tick; ``min_gap_ticks`` is a CAPTURE bound
  (existence floor), never a quality threshold — gap size is an emitted
  measurement the ML layer learns from (WIDE-capture ruling).
* A GAP EXISTS ONLY AT ITS OWN TIMEFRAME'S CLOSE. ``confirmed_ts_utc`` is the C
  bar's ``close_ts_utc`` and is the availability instant (the same zero-lookahead
  discipline as ``Level.available_from``): registry fill/touch participation
  requires an execution bar closing STRICTLY AFTER it.
* TRIPLETS SPAN TRADING DAYS. The detector's rolling window is NOT reset at the
  day roll (census: real triplets span the 18:00 ET boundary and weekends); both
  ``COMPLETE`` and ``END_OF_DAY`` bars participate. Cross-process continuity is
  the ``snapshot_tail`` / ``from_tail`` seam.
* FILLS ARE PHYSICAL PRICE EVENTS at execution (1m) granularity, wicks count:
  first touch = wick overlap of the gap interval; full fill = the running
  post-formation extreme traverses the FAR boundary (bullish: some later low
  <= ``gap_low_ticks``; bearish: some later high >= ``gap_high_ticks``).
  Filled gaps are dead context and leave the live set.

All geometry is integer ticks (``Bar.*_ticks``). The consecrated-entry (CE /
midpoint) comparisons use doubled ticks (``ce_ticks_x2``) so no predicate ever
divides. Streaming (:class:`FvgDetector` + :class:`FvgRegistry`) and batch
(:func:`detect_fvgs_over_bars`) shapes are locked together by
``tests/test_fvg_parity.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Sequence

from strategy_core.types import Bar, Side

__all__ = [
    "GapDirection",
    "Fvg",
    "FvgDetector",
    "detect_fvgs_over_bars",
    "FvgState",
    "FvgFillEvent",
    "FvgRegistry",
    "FvgStateSnapshot",
    "FvgRegistrySnapshot",
    "wick_overlaps",
    "body_closes_through",
    "close_through_margin_ticks",
    "penetration_ticks",
    "ce_reached",
    "interval_distance_ticks",
    "FVG_SNAPSHOT_SCHEMA_VERSION",
]

#: Bumped whenever :class:`FvgStateSnapshot` / :class:`FvgRegistrySnapshot`
#: change shape; consumers fail closed on mismatch (seed-trust discipline).
FVG_SNAPSHOT_SCHEMA_VERSION = 2


class GapDirection(StrEnum):
    """Displacement direction of the gap (distinct from trade ``Direction`` on
    purpose: a gap has a formation direction; a trade has an intent)."""

    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(frozen=True, slots=True)
class Fvg:
    """One confirmed fair-value gap. Immutable; tracking state lives in
    :class:`FvgState`.

    ``fvg_id`` is deterministic (``{seconds}s:{direction}:{c_bar_id}``) — the
    join key between streaming and batch paths and across research records.
    ``gap_low_ticks < gap_high_ticks`` always (direction says which edge is the
    "far" boundary). ``a_open_ts_utc`` is carried so the ``fully_formed_after``
    causality family stays derivable as a row filter downstream.
    """

    fvg_id: str
    timeframe_seconds: int
    direction: GapDirection
    gap_low_ticks: int
    gap_high_ticks: int
    size_ticks: int
    a_bar_id: str
    c_bar_id: str
    a_open_ts_utc: datetime
    confirmed_ts_utc: datetime
    trading_day: date

    @property
    def ce_ticks_x2(self) -> int:
        """Consequent encroachment (midpoint) in DOUBLED ticks — compare against
        ``2 * price_ticks`` so midpoint predicates never divide."""
        return self.gap_low_ticks + self.gap_high_ticks

    @property
    def far_boundary_ticks(self) -> int:
        """The boundary whose traversal fills the gap (bullish: the low edge,
        approached from above; bearish: the high edge, approached from below)."""
        return self.gap_low_ticks if self.direction is GapDirection.BULLISH else self.gap_high_ticks

    @property
    def near_boundary_ticks(self) -> int:
        """The boundary price first reaches when retracing into the gap."""
        return self.gap_high_ticks if self.direction is GapDirection.BULLISH else self.gap_low_ticks


def _make_fvg_id(timeframe_seconds: int, direction: GapDirection, c_bar_id: str) -> str:
    return f"{timeframe_seconds}s:{direction}:{c_bar_id}"


def _gap_from_triplet(
    a: Bar, c: Bar, *, timeframe_seconds: int, min_gap_ticks: int
) -> Fvg | None:
    """Apply the census geometry to a completed (A, B, C) triplet, B implicit."""
    if a.high_ticks < c.low_ticks:
        size = c.low_ticks - a.high_ticks
        if size < min_gap_ticks:
            return None
        direction = GapDirection.BULLISH
        gap_low, gap_high = a.high_ticks, c.low_ticks
    elif a.low_ticks > c.high_ticks:
        size = a.low_ticks - c.high_ticks
        if size < min_gap_ticks:
            return None
        direction = GapDirection.BEARISH
        gap_low, gap_high = c.high_ticks, a.low_ticks
    else:
        return None
    return Fvg(
        fvg_id=_make_fvg_id(timeframe_seconds, direction, c.bar_id),
        timeframe_seconds=timeframe_seconds,
        direction=direction,
        gap_low_ticks=gap_low,
        gap_high_ticks=gap_high,
        size_ticks=size,
        a_bar_id=a.bar_id,
        c_bar_id=c.bar_id,
        a_open_ts_utc=a.logical_open_ts_utc or a.open_ts_utc,
        confirmed_ts_utc=c.availability_ts_utc,
        trading_day=c.trading_day,
    )


class FvgDetector:
    """Streaming three-bar FVG detector for ONE timeframe.

    Feed every closed bar of that timeframe in emission order (COMPLETE and
    END_OF_DAY alike; across day rolls without reset). Returns the confirmed
    :class:`Fvg` when the just-closed bar completes a gapping triplet.
    """

    def __init__(self, timeframe_seconds: int, *, min_gap_ticks: int = 1) -> None:
        if timeframe_seconds <= 0:
            raise ValueError(f"timeframe_seconds must be positive (got {timeframe_seconds})")
        if min_gap_ticks < 1:
            raise ValueError(f"min_gap_ticks must be >= 1 (got {min_gap_ticks})")
        self.timeframe_seconds = timeframe_seconds
        self.min_gap_ticks = min_gap_ticks
        self._window: list[Bar] = []  # at most the last 2 closed bars (A, B)

    def on_bar_closed(self, bar: Bar) -> Fvg | None:
        """Roll the window with ``bar`` as the new C; detect on the full triplet."""
        if bar.timeframe_ticks != self.timeframe_seconds:
            raise ValueError(
                f"bar timeframe {bar.timeframe_ticks}s does not match detector "
                f"{self.timeframe_seconds}s"
            )
        gap: Fvg | None = None
        if len(self._window) == 2:
            gap = _gap_from_triplet(
                self._window[0],
                bar,
                timeframe_seconds=self.timeframe_seconds,
                min_gap_ticks=self.min_gap_ticks,
            )
        self._window = [*self._window[-1:], bar] if self._window else [bar]
        return gap

    def snapshot_tail(self) -> tuple[Bar, ...]:
        """The rolling window (<= 2 bars) — cross-day/process detector continuity."""
        return tuple(self._window)

    @classmethod
    def from_tail(
        cls, timeframe_seconds: int, tail: Sequence[Bar], *, min_gap_ticks: int = 1
    ) -> FvgDetector:
        """Rebuild a detector from a :meth:`snapshot_tail` result."""
        if len(tail) > 2:
            raise ValueError(f"detector tail carries at most 2 bars (got {len(tail)})")
        detector = cls(timeframe_seconds, min_gap_ticks=min_gap_ticks)
        for bar in tail:
            if bar.timeframe_ticks != timeframe_seconds:
                raise ValueError(
                    f"tail bar timeframe {bar.timeframe_ticks}s does not match "
                    f"detector {timeframe_seconds}s"
                )
        detector._window = list(tail)
        return detector


def detect_fvgs_over_bars(
    bars: Sequence[Bar],
    *,
    timeframe_seconds: int,
    min_gap_ticks: int = 1,
    tail: Sequence[Bar] = (),
) -> list[Fvg]:
    """Batch twin of :class:`FvgDetector` — one pass, same triplets, same ids.

    ``tail`` is the prior detector window (<= 2 bars) so a per-day batch run
    detects the cross-boundary triplets the continuous stream would.
    """
    detector = FvgDetector.from_tail(timeframe_seconds, tail, min_gap_ticks=min_gap_ticks)
    out: list[Fvg] = []
    for bar in bars:
        gap = detector.on_bar_closed(bar)
        if gap is not None:
            out.append(gap)
    return out


# ── predicates & measurements ────────────────────────────────────────────────
# The ONLY gate predicates the IFVG reducer may use are wick_overlaps and
# body_closes_through (hard invariants). Everything else here is a MEASUREMENT
# emitted onto research records for the ML layer.


def wick_overlaps(bar: Bar, lo_ticks: int, hi_ticks: int) -> bool:
    """Closed-interval wick overlap: the bar's range touched ``[lo, hi]``."""
    return bar.high_ticks >= lo_ticks and bar.low_ticks <= hi_ticks


def body_closes_through(bar: Bar, *, boundary_ticks: int, beyond: Side) -> bool:
    """STRICT body close beyond a boundary (a close exactly AT the boundary is
    not "through"; the margin measurement lets the ML layer see boundary cases)."""
    if beyond is Side.HIGH:
        return bar.close_ticks > boundary_ticks
    return bar.close_ticks < boundary_ticks


def close_through_margin_ticks(bar: Bar, *, boundary_ticks: int, beyond: Side) -> int:
    """Signed close-vs-boundary margin (positive = through, per ``beyond``)."""
    if beyond is Side.HIGH:
        return bar.close_ticks - boundary_ticks
    return boundary_ticks - bar.close_ticks


def penetration_ticks(bar: Bar, gap: Fvg) -> int:
    """Depth this bar reached INTO the gap from its near boundary, >= 0, capped
    at the gap size (a traversal counts as full depth)."""
    if gap.direction is GapDirection.BULLISH:
        depth = gap.gap_high_ticks - bar.low_ticks
    else:
        depth = bar.high_ticks - gap.gap_low_ticks
    return max(0, min(depth, gap.size_ticks))


def ce_reached(bar: Bar, gap: Fvg) -> bool:
    """Whether the bar's wick reached the gap midpoint (CE). Doubled-tick
    comparison — exact, no division."""
    if gap.direction is GapDirection.BULLISH:
        return 2 * bar.low_ticks <= gap.ce_ticks_x2
    return 2 * bar.high_ticks >= gap.ce_ticks_x2


def interval_distance_ticks(lo1: int, hi1: int, lo2: int, hi2: int) -> int:
    """Vertical distance between two closed intervals: 0 if they overlap, else
    the nearest-edge gap (the census/doc §5.6 convention)."""
    if hi1 < lo2:
        return lo2 - hi1
    if hi2 < lo1:
        return lo1 - hi2
    return 0


# ── fill tracking ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class FvgState:
    """Mutable tracking wrapper around one live gap (the ``Zone.touched``
    precedent: tracking flags are the only mutable engine state).

    ``reached_ticks`` is the running post-formation extreme INTO the gap
    (bullish: min low seen; bearish: max high seen), ``None`` until first touch.
    """

    fvg: Fvg
    first_touch_ts_utc: datetime | None = None
    reached_ticks: int | None = None
    filled_ts_utc: datetime | None = None

    def penetration_so_far_ticks(self) -> int:
        """Deepest penetration recorded so far, 0 if untouched, capped at size."""
        if self.reached_ticks is None:
            return 0
        if self.fvg.direction is GapDirection.BULLISH:
            depth = self.fvg.gap_high_ticks - self.reached_ticks
        else:
            depth = self.reached_ticks - self.fvg.gap_low_ticks
        return max(0, min(depth, self.fvg.size_ticks))

    def remaining_fraction(self) -> float:
        """1.0 untouched .. 0.0 filled — an emitted measurement."""
        return 1.0 - self.penetration_so_far_ticks() / self.fvg.size_ticks


@dataclass(frozen=True, slots=True)
class FvgFillEvent:
    """Registry maintenance outcome for one gap on one execution bar.

    The evidence fields below default to ``None`` and are populated by the
    registry for the FSM audit channel; every existing consumer reads only
    ``fvg_id``/``kind``. This dataclass is never snapshotted, so enriching it
    cannot move any seed hash. ``prior_*`` values are captured BEFORE the
    bar's mutation of :class:`FvgState`; ``new_*``/``remaining_fraction_after``
    after it. Cap evictions have no triggering execution bar, so their wick/
    body flags stay ``None`` and ages are measured against the confirming
    gap's instant.
    """

    fvg_id: str
    kind: str  # "first_touch" | "filled" | "evicted_cap" | "evicted_age"
    ts_utc: datetime
    fvg: Fvg | None = None
    prior_reached_ticks: int | None = None
    new_reached_ticks: int | None = None
    prior_penetration_ticks: int | None = None
    new_penetration_ticks: int | None = None
    remaining_fraction_after: float | None = None
    wick_crossed_far_boundary: bool | None = None
    body_closed_through_far_boundary: bool | None = None
    age_seconds: int | None = None
    age_trading_days: int | None = None
    registry_live_count_after: int | None = None


@dataclass(frozen=True, slots=True)
class FvgStateSnapshot:
    """Frozen copy of one :class:`FvgState` for the day-seed seam."""

    fvg: Fvg
    first_touch_ts_utc: datetime | None
    reached_ticks: int | None
    filled_ts_utc: datetime | None


@dataclass(frozen=True, slots=True)
class FvgRegistrySnapshot:
    """One timeframe's cross-day carry state: the live set AND the detector
    tail (cross-boundary triplets are load-bearing — census E3)."""

    schema_version: int
    timeframe_seconds: int
    min_gap_ticks: int
    max_live: int | None
    max_age_days: int | None
    live: tuple[FvgStateSnapshot, ...]
    detector_tail: tuple[Bar, ...]


@dataclass(slots=True)
class FvgRegistry:
    """Live-gap registry for ONE timeframe with execution-granularity fill scan.

    ``max_live`` / ``max_age_days`` are MEMORY bounds (WIDE capture), never the
    doc's selection caps — selection policy is the reducer's job and is emitted,
    not enforced here. Eviction (only when a bound binds) removes oldest-first
    and emits an event so the funnel can count what a bound cost.
    """

    timeframe_seconds: int
    max_live: int | None = None
    max_age_days: int | None = None
    _live: list[FvgState] = field(default_factory=list)

    def add(self, fvg: Fvg) -> tuple[FvgFillEvent, ...]:
        """Register a newly confirmed gap; returns any cap-eviction events."""
        if fvg.timeframe_seconds != self.timeframe_seconds:
            raise ValueError(
                f"fvg timeframe {fvg.timeframe_seconds}s does not match registry "
                f"{self.timeframe_seconds}s"
            )
        self._live.append(FvgState(fvg=fvg))
        events: list[FvgFillEvent] = []
        if self.max_live is not None:
            while len(self._live) > self.max_live:
                evicted = self._live.pop(0)  # oldest first (insertion = confirmation order)
                penetration = evicted.penetration_so_far_ticks()
                events.append(
                    FvgFillEvent(
                        fvg_id=evicted.fvg.fvg_id,
                        kind="evicted_cap",
                        ts_utc=fvg.confirmed_ts_utc,
                        fvg=evicted.fvg,
                        prior_reached_ticks=evicted.reached_ticks,
                        new_reached_ticks=evicted.reached_ticks,
                        prior_penetration_ticks=penetration,
                        new_penetration_ticks=penetration,
                        remaining_fraction_after=evicted.remaining_fraction(),
                        age_seconds=int(
                            (
                                fvg.confirmed_ts_utc - evicted.fvg.confirmed_ts_utc
                            ).total_seconds()
                        ),
                        age_trading_days=(
                            fvg.trading_day - evicted.fvg.trading_day
                        ).days,
                        registry_live_count_after=len(self._live),
                    )
                )
        return tuple(events)

    def on_execution_bar(self, bar: Bar) -> tuple[FvgFillEvent, ...]:
        """Fold one execution (1m) bar through every live gap.

        HARD invariant: a gap participates only if this bar closes STRICTLY
        AFTER its confirmation instant (zero-lookahead; a gap's own C bar never
        touches it). Emits first_touch / filled / evicted_age events in live-set
        order; filled and age-evicted gaps leave the live set.
        """
        pending: list[tuple[str, FvgState, int | None]] = []
        survivors: list[FvgState] = []
        for state in self._live:
            gap = state.fvg
            availability = bar.availability_ts_utc
            if availability <= gap.confirmed_ts_utc:
                survivors.append(state)
                continue
            if (
                self.max_age_days is not None
                and (bar.trading_day - gap.trading_day).days > self.max_age_days
            ):
                pending.append(("evicted_age", state, state.reached_ticks))
                continue
            if wick_overlaps(bar, gap.gap_low_ticks, gap.gap_high_ticks):
                first = state.first_touch_ts_utc is None
                prior_reached = state.reached_ticks
                if first:
                    state.first_touch_ts_utc = availability
                extreme = bar.low_ticks if gap.direction is GapDirection.BULLISH else bar.high_ticks
                if state.reached_ticks is None:
                    state.reached_ticks = extreme
                elif gap.direction is GapDirection.BULLISH:
                    state.reached_ticks = min(state.reached_ticks, extreme)
                else:
                    state.reached_ticks = max(state.reached_ticks, extreme)
                if first:
                    pending.append(("first_touch", state, prior_reached))
                traversed = (
                    state.reached_ticks <= gap.gap_low_ticks
                    if gap.direction is GapDirection.BULLISH
                    else state.reached_ticks >= gap.gap_high_ticks
                )
                if traversed:
                    state.filled_ts_utc = availability
                    pending.append(("filled", state, prior_reached))
                    continue  # dead context — leaves the live set
            survivors.append(state)
        self._live = survivors
        live_after = len(survivors)
        events: list[FvgFillEvent] = []
        for kind, state, prior_reached in pending:
            gap = state.fvg
            if prior_reached is None:
                prior_penetration = 0
            else:
                depth = (
                    gap.gap_high_ticks - prior_reached
                    if gap.direction is GapDirection.BULLISH
                    else prior_reached - gap.gap_low_ticks
                )
                prior_penetration = max(0, min(depth, gap.size_ticks))
            far_side = Side.LOW if gap.direction is GapDirection.BULLISH else Side.HIGH
            events.append(
                FvgFillEvent(
                    fvg_id=gap.fvg_id,
                    kind=kind,
                    ts_utc=bar.availability_ts_utc,
                    fvg=gap,
                    prior_reached_ticks=prior_reached,
                    new_reached_ticks=state.reached_ticks,
                    prior_penetration_ticks=prior_penetration,
                    new_penetration_ticks=state.penetration_so_far_ticks(),
                    remaining_fraction_after=state.remaining_fraction(),
                    wick_crossed_far_boundary=(
                        bar.low_ticks <= gap.gap_low_ticks
                        if gap.direction is GapDirection.BULLISH
                        else bar.high_ticks >= gap.gap_high_ticks
                    ),
                    body_closed_through_far_boundary=body_closes_through(
                        bar, boundary_ticks=gap.far_boundary_ticks, beyond=far_side
                    ),
                    age_seconds=int(
                        (bar.availability_ts_utc - gap.confirmed_ts_utc).total_seconds()
                    ),
                    age_trading_days=(bar.trading_day - gap.trading_day).days,
                    registry_live_count_after=live_after,
                )
            )
        return tuple(events)

    def live(self) -> tuple[FvgState, ...]:
        """Live (unfilled, unevicted) gaps in deterministic order
        (confirmation ts, then id — insertion order is already that)."""
        return tuple(self._live)

    def snapshot(
        self, *, detector_tail: Sequence[Bar] = (), min_gap_ticks: int = 1
    ) -> FvgRegistrySnapshot:
        """Freeze this registry plus its companion detector's tail/floor (the
        registry does not own ``min_gap_ticks``; it rides the snapshot so the
        per-timeframe pair reconstructs from one object)."""
        return FvgRegistrySnapshot(
            schema_version=FVG_SNAPSHOT_SCHEMA_VERSION,
            timeframe_seconds=self.timeframe_seconds,
            min_gap_ticks=min_gap_ticks,
            max_live=self.max_live,
            max_age_days=self.max_age_days,
            live=tuple(
                FvgStateSnapshot(
                    fvg=s.fvg,
                    first_touch_ts_utc=s.first_touch_ts_utc,
                    reached_ticks=s.reached_ticks,
                    filled_ts_utc=s.filled_ts_utc,
                )
                for s in self._live
            ),
            detector_tail=tuple(detector_tail),
        )

    @classmethod
    def from_snapshot(cls, snap: FvgRegistrySnapshot) -> FvgRegistry:
        if snap.schema_version != FVG_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"FvgRegistrySnapshot schema {snap.schema_version} != "
                f"supported {FVG_SNAPSHOT_SCHEMA_VERSION}"
            )
        registry = cls(
            timeframe_seconds=snap.timeframe_seconds,
            max_live=snap.max_live,
            max_age_days=snap.max_age_days,
        )
        registry._live = [
            FvgState(
                fvg=s.fvg,
                first_touch_ts_utc=s.first_touch_ts_utc,
                reached_ticks=s.reached_ticks,
                filled_ts_utc=s.filled_ts_utc,
            )
            for s in snap.live
        ]
        return registry
