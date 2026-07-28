"""The ``ifvg_smc`` one-setup FSM — deterministic, no I/O, no clocks.

Engine-idiom deterministic class (like ``TimeBarEngine`` / ``StrategyLevelState``)
rather than a literal pure function: same inputs => same outputs, state crosses
process/day boundaries only through :meth:`snapshot` / :meth:`from_snapshot`,
and the replay-parity tests enforce continuous == seeded equivalence.

Phases::

    S0 scanning -> S1 parent search -> S2 parent locked -> S3 opposing armed
      -> S4 inverted -> S5 in trade -> (resolution) -> S0

CANONICAL PER-1m-CLOSE ORDER (the orchestrator feeds one :class:`IfvgStepInput`
per closed 1m bar, with registry fill maintenance ALREADY applied for this bar
and new structures confirmed AT this instant in ``new_fvgs``):

1. invalidations — selected-HTF fill, parent fill, parent-TF structural close
   (all pre-entry only, doc §7.3: ignored after entry);
2. stage-bound expiries (WIDE capture bounds — they free the slot, they do not
   judge quality);
3. price-action transitions using structures confirmed STRICTLY BEFORE this
   instant (hard invariants live here: strict-after usability, 1m body-close
   inversion, no entry on the inversion candle, risk >= 1 tick) — with the ONE
   ratified exception that the fresh-family entry executes on its own
   confirmation close (entry_price_model = confirmation_close);
4. new-structure intake — parent candidates / opposing gaps arm for FUTURE
   bars; §14.7's inversion-before-replacement invariant holds because step 3
   ran first.

Every candidate the slot logic rejects is EMITTED with ``selected=False`` and a
drop reason (the dropped-candidate ruling); every soft threshold is emitted as
a measurement. Session names are stamps, never gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from strategy_core.structures.fvg import (
    Fvg,
    FvgFillEvent,
    FvgState,
    GapDirection,
    body_closes_through,
    ce_reached,
    close_through_margin_ticks,
    interval_distance_ticks,
    penetration_ticks,
    wick_overlaps,
)
from strategy_core.structures.sweeps import (
    LevelPool,
    SweepResult,
    SweepTracker,
    SweepTrackerSnapshot,
)
from strategy_core.structures.swings import SwingPoint
from strategy_core.types import Bar, Direction, Level, Side

from .records import (
    IFVG_RECORD_SCHEMA_VERSION,
    EntryCandidateRecord,
    HtfTapRecord,
    IfvgEmission,
    InversionRecord,
    OpposingGapRecord,
    ParentCandidateRecord,
    ParentLockRecord,
    RecordEnvelope,
    SetupResolutionRecord,
)
from .section import IfvgSmcSection, ifvg_profile_hash

__all__ = [
    "IfvgReducerConfig",
    "IfvgStepInput",
    "IfvgReducer",
    "IfvgReducerSnapshot",
    "IfvgSetupSnapshot",
    "REDUCER_SNAPSHOT_SCHEMA_VERSION",
]

REDUCER_SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class IfvgReducerConfig:
    """Frozen, pydantic-free derivation of the section (built once per run)."""

    strategy_id: str
    strategy_version: str
    profile_hash: str
    tick_size: float
    htf_tf_seconds: tuple[int, ...]  # descending = rank order (4H beats 1H)
    parent_tf_seconds: tuple[int, ...]  # descending = doc priority 30m>...>3m
    parent_reaction_window_1m_bars_max: int
    lock_to_armed_1m_bars_max: int
    armed_to_inversion_1m_bars_max: int
    post_inversion_expiry_1m_bars_max: int
    parent_htf_distance_ticks_max: int
    opposing_parent_distance_ticks_max: int
    sl_buffer_ticks: int
    tp_r_multiple: float
    selected_entry_family: str

    @classmethod
    def from_section(
        cls,
        section: IfvgSmcSection,
        *,
        tick_size: float,
        strategy_id: str,
        strategy_version: str,
    ) -> IfvgReducerConfig:
        from strategy_core.constants import TIME_TF_SECONDS

        return cls(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            profile_hash=ifvg_profile_hash(section),
            tick_size=tick_size,
            htf_tf_seconds=tuple(
                sorted((TIME_TF_SECONDS[lbl] for lbl in section.htf_timeframes), reverse=True)
            ),
            parent_tf_seconds=tuple(
                sorted((TIME_TF_SECONDS[lbl] for lbl in section.parent_timeframes), reverse=True)
            ),
            parent_reaction_window_1m_bars_max=section.parent_reaction_window_1m_bars_max,
            lock_to_armed_1m_bars_max=section.lock_to_armed_1m_bars_max,
            armed_to_inversion_1m_bars_max=section.armed_to_inversion_1m_bars_max,
            post_inversion_expiry_1m_bars_max=section.post_inversion_expiry_1m_bars_max,
            parent_htf_distance_ticks_max=section.parent_htf_distance_ticks_max,
            opposing_parent_distance_ticks_max=section.opposing_parent_distance_ticks_max,
            sl_buffer_ticks=section.sl_buffer_ticks,
            tp_r_multiple=section.tp_r_multiple,
            selected_entry_family=section.selected_entry_family,
        )


@dataclass(frozen=True, slots=True)
class IfvgStepInput:
    """Everything the FSM may read at ONE 1m close (assembled by the
    orchestrator — ``replay.run_day`` offline, the plugin live)."""

    bar_1m: Bar
    #: Parent/HTF bars that closed at this instant, keyed by interval seconds.
    tf_bars_closed: Mapping[int, Bar]
    #: Structures confirmed AT this instant, keyed by interval seconds.
    new_fvgs: Mapping[int, tuple[Fvg, ...]]
    #: Registry maintenance results for this bar (already applied upstream).
    fill_events: tuple[FvgFillEvent, ...]
    #: Post-maintenance live HTF gaps (all HTF timeframes, any order).
    htf_live: tuple[FvgState, ...]
    #: Available-now key levels (points; converted on the tick grid at use).
    levels: tuple[Level, ...]
    #: Confirmed swing points eligible as pools (newest-first, both sides).
    recent_swing_highs: tuple[SwingPoint, ...]
    recent_swing_lows: tuple[SwingPoint, ...]
    session_engine: str
    session_doc: str


@dataclass(slots=True)
class _Setup:
    """The single in-flight setup (mutable engine state)."""

    setup_id: str
    phase: str
    direction: Direction
    htf: Fvg
    tap_ts_utc: datetime
    tap_ordinal: int
    # S1
    parent: Fvg | None = None
    parent_selected_ordinal: int | None = None
    # S2
    lock_ts_utc: datetime | None = None
    lock_ordinal: int | None = None
    swing_min_low: int | None = None
    swing_max_high: int | None = None
    sweep: SweepTracker | None = None
    # S3
    opposing: Fvg | None = None
    armed_ts_utc: datetime | None = None
    armed_ordinal: int | None = None
    # S4
    inversion_ts_utc: datetime | None = None
    inversion_ordinal: int | None = None
    sweep_result: SweepResult | None = None
    # S5
    entry_family: str | None = None
    entry_ticks: int | None = None
    stop_ticks: int | None = None
    tp_ticks: int | None = None
    entry_ts_utc: datetime | None = None
    entry_ordinal: int | None = None
    mfe_ticks: int = 0
    mae_ticks: int = 0


@dataclass(frozen=True, slots=True)
class IfvgSetupSnapshot:
    setup_id: str
    phase: str
    direction: Direction
    htf: Fvg
    tap_ts_utc: datetime
    tap_ordinal: int
    parent: Fvg | None
    parent_selected_ordinal: int | None
    lock_ts_utc: datetime | None
    lock_ordinal: int | None
    swing_min_low: int | None
    swing_max_high: int | None
    sweep: SweepTrackerSnapshot | None
    opposing: Fvg | None
    armed_ts_utc: datetime | None
    armed_ordinal: int | None
    inversion_ts_utc: datetime | None
    inversion_ordinal: int | None
    sweep_result: SweepResult | None
    entry_family: str | None
    entry_ticks: int | None
    stop_ticks: int | None
    tp_ticks: int | None
    entry_ts_utc: datetime | None
    entry_ordinal: int | None
    mfe_ticks: int
    mae_ticks: int


@dataclass(frozen=True, slots=True)
class IfvgReducerSnapshot:
    schema_version: int
    profile_hash: str
    ordinal: int
    seq_day: date | None
    seq: int
    setup: IfvgSetupSnapshot | None


class IfvgReducer:
    """Fold :class:`IfvgStepInput`s; emit typed records; count the funnel."""

    def __init__(self, config: IfvgReducerConfig) -> None:
        self._cfg = config
        self._ordinal = 0
        self._setup: _Setup | None = None
        self._seq_day: date | None = None
        self._seq = 0
        self._funnel: dict[str, int] = {}

    # ── public surface ─────────────────────────────────────────────────────
    @property
    def phase(self) -> str:
        return self._setup.phase if self._setup is not None else "S0"

    def funnel_counters(self) -> dict[str, int]:
        return dict(self._funnel)

    def reset_funnel(self) -> None:
        self._funnel = {}

    def step(self, inp: IfvgStepInput) -> tuple[IfvgEmission, ...]:
        self._ordinal += 1
        bar = inp.bar_1m
        out: list[IfvgEmission] = []
        self._apply_invalidations(inp, out)
        self._apply_expiries(bar, out)
        self._apply_transitions(inp, out)
        self._apply_intake(inp, out)
        return tuple(out)

    def finalize_day(self, *, last_ts_utc: datetime, trading_day: date) -> tuple[IfvgEmission, ...]:
        """Day-end hook: an in-trade setup resolves ``resolved_eod`` (its
        forward window ends with the day); PRE-entry stages carry across the
        roll via the snapshot (owner default: carry, live-faithful)."""
        s = self._setup
        if s is None or s.phase != "S5":
            return ()
        out: list[IfvgEmission] = []
        self._resolve(s, "resolved_eod", last_ts_utc, trading_day, out)
        return tuple(out)

    def snapshot(self) -> IfvgReducerSnapshot:
        s = self._setup
        return IfvgReducerSnapshot(
            schema_version=REDUCER_SNAPSHOT_SCHEMA_VERSION,
            profile_hash=self._cfg.profile_hash,
            ordinal=self._ordinal,
            seq_day=self._seq_day,
            seq=self._seq,
            setup=(
                IfvgSetupSnapshot(
                    setup_id=s.setup_id,
                    phase=s.phase,
                    direction=s.direction,
                    htf=s.htf,
                    tap_ts_utc=s.tap_ts_utc,
                    tap_ordinal=s.tap_ordinal,
                    parent=s.parent,
                    parent_selected_ordinal=s.parent_selected_ordinal,
                    lock_ts_utc=s.lock_ts_utc,
                    lock_ordinal=s.lock_ordinal,
                    swing_min_low=s.swing_min_low,
                    swing_max_high=s.swing_max_high,
                    sweep=s.sweep.snapshot() if s.sweep is not None else None,
                    opposing=s.opposing,
                    armed_ts_utc=s.armed_ts_utc,
                    armed_ordinal=s.armed_ordinal,
                    inversion_ts_utc=s.inversion_ts_utc,
                    inversion_ordinal=s.inversion_ordinal,
                    sweep_result=s.sweep_result,
                    entry_family=s.entry_family,
                    entry_ticks=s.entry_ticks,
                    stop_ticks=s.stop_ticks,
                    tp_ticks=s.tp_ticks,
                    entry_ts_utc=s.entry_ts_utc,
                    entry_ordinal=s.entry_ordinal,
                    mfe_ticks=s.mfe_ticks,
                    mae_ticks=s.mae_ticks,
                )
                if s is not None
                else None
            ),
        )

    @classmethod
    def from_snapshot(cls, snap: IfvgReducerSnapshot, config: IfvgReducerConfig) -> IfvgReducer:
        if snap.schema_version != REDUCER_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"IfvgReducerSnapshot schema {snap.schema_version} != "
                f"supported {REDUCER_SNAPSHOT_SCHEMA_VERSION}"
            )
        if snap.profile_hash != config.profile_hash:
            raise ValueError(
                "reducer snapshot profile_hash does not match the active section "
                f"({snap.profile_hash[:12]}... != {config.profile_hash[:12]}...)"
            )
        reducer = cls(config)
        reducer._ordinal = snap.ordinal
        reducer._seq_day = snap.seq_day
        reducer._seq = snap.seq
        if snap.setup is not None:
            ss = snap.setup
            reducer._setup = _Setup(
                setup_id=ss.setup_id,
                phase=ss.phase,
                direction=ss.direction,
                htf=ss.htf,
                tap_ts_utc=ss.tap_ts_utc,
                tap_ordinal=ss.tap_ordinal,
                parent=ss.parent,
                parent_selected_ordinal=ss.parent_selected_ordinal,
                lock_ts_utc=ss.lock_ts_utc,
                lock_ordinal=ss.lock_ordinal,
                swing_min_low=ss.swing_min_low,
                swing_max_high=ss.swing_max_high,
                sweep=SweepTracker.from_snapshot(ss.sweep) if ss.sweep is not None else None,
                opposing=ss.opposing,
                armed_ts_utc=ss.armed_ts_utc,
                armed_ordinal=ss.armed_ordinal,
                inversion_ts_utc=ss.inversion_ts_utc,
                inversion_ordinal=ss.inversion_ordinal,
                sweep_result=ss.sweep_result,
                entry_family=ss.entry_family,
                entry_ticks=ss.entry_ticks,
                stop_ticks=ss.stop_ticks,
                tp_ticks=ss.tp_ticks,
                entry_ts_utc=ss.entry_ts_utc,
                entry_ordinal=ss.entry_ordinal,
                mfe_ticks=ss.mfe_ticks,
                mae_ticks=ss.mae_ticks,
            )
        return reducer

    # ── helpers ────────────────────────────────────────────────────────────
    def _count(self, key: str, n: int = 1) -> None:
        self._funnel[key] = self._funnel.get(key, 0) + n

    def _env(self, ts_utc: datetime, trading_day: date, setup_id: str) -> RecordEnvelope:
        return RecordEnvelope(
            schema_version=IFVG_RECORD_SCHEMA_VERSION,
            strategy_id=self._cfg.strategy_id,
            strategy_version=self._cfg.strategy_version,
            profile_hash=self._cfg.profile_hash,
            trading_day=trading_day,
            ts_utc=ts_utc,
            setup_id=setup_id,
        )

    @staticmethod
    def _gap_direction_to_trade(direction: GapDirection) -> Direction:
        return Direction.LONG if direction is GapDirection.BULLISH else Direction.SHORT

    def _resolve(
        self,
        s: _Setup,
        resolution: str,
        ts_utc: datetime,
        trading_day: date,
        out: list[IfvgEmission],
    ) -> None:
        self._count(resolution)
        out.append(
            IfvgEmission(
                kind="resolution",
                record=SetupResolutionRecord(
                    envelope=self._env(ts_utc, trading_day, s.setup_id),
                    resolution=resolution,
                    direction=s.direction,
                    entry_family=s.entry_family,
                    entry_ticks=s.entry_ticks,
                    stop_ticks=s.stop_ticks,
                    tp_ticks=s.tp_ticks,
                    mfe_ticks=s.mfe_ticks if s.entry_ordinal is not None else None,
                    mae_ticks=s.mae_ticks if s.entry_ordinal is not None else None,
                    bars_in_trade=(
                        self._ordinal - s.entry_ordinal if s.entry_ordinal is not None else None
                    ),
                    tap_ts_utc=s.tap_ts_utc,
                    parent_confirmed_ts_utc=s.parent.confirmed_ts_utc if s.parent else None,
                    lock_ts_utc=s.lock_ts_utc,
                    armed_ts_utc=s.armed_ts_utc,
                    inversion_ts_utc=s.inversion_ts_utc,
                    entry_ts_utc=s.entry_ts_utc,
                    htf_fvg_id=s.htf.fvg_id,
                    parent_fvg_id=s.parent.fvg_id if s.parent else None,
                    opposing_fvg_id=s.opposing.fvg_id if s.opposing else None,
                ),
            )
        )
        self._setup = None

    # ── step 1: invalidations (pre-entry only) ─────────────────────────────
    def _apply_invalidations(self, inp: IfvgStepInput, out: list[IfvgEmission]) -> None:
        s = self._setup
        if s is None or s.phase == "S5":
            return
        bar = inp.bar_1m
        filled = {e.fvg_id for e in inp.fill_events if e.kind == "filled"}
        if s.htf.fvg_id in filled:
            self._resolve(s, "invalidated_htf_filled", bar.close_ts_utc, bar.trading_day, out)
            return
        if s.parent is not None and s.parent.fvg_id in filled:
            if s.phase == "S1":
                self._count("candidate_died_filled")
                s.parent = None
                s.parent_selected_ordinal = None
            else:
                self._resolve(
                    s, "invalidated_parent_filled", bar.close_ts_utc, bar.trading_day, out
                )
                return
        if s.parent is not None:
            tf_bar = inp.tf_bars_closed.get(s.parent.timeframe_seconds)
            if tf_bar is not None:
                structural = (
                    body_closes_through(
                        tf_bar, boundary_ticks=s.parent.gap_low_ticks, beyond=Side.LOW
                    )
                    if s.parent.direction is GapDirection.BULLISH
                    else body_closes_through(
                        tf_bar, boundary_ticks=s.parent.gap_high_ticks, beyond=Side.HIGH
                    )
                )
                if structural:
                    if s.phase == "S1":
                        self._count("candidate_died_structural")
                        s.parent = None
                        s.parent_selected_ordinal = None
                    else:
                        self._resolve(
                            s,
                            "invalidated_parent_structural",
                            bar.close_ts_utc,
                            bar.trading_day,
                            out,
                        )

    # ── step 2: stage-bound expiries ────────────────────────────────────────
    def _apply_expiries(self, bar: Bar, out: list[IfvgEmission]) -> None:
        s = self._setup
        if s is None or s.phase == "S5":
            return
        cfg = self._cfg
        checks = {
            "S1": (s.tap_ordinal, cfg.parent_reaction_window_1m_bars_max, "expired_parent_search"),
            "S2": (s.lock_ordinal, cfg.lock_to_armed_1m_bars_max, "expired_lock_wait"),
            "S3": (s.armed_ordinal, cfg.armed_to_inversion_1m_bars_max, "expired_armed"),
            "S4": (s.inversion_ordinal, cfg.post_inversion_expiry_1m_bars_max, "expired_entry_wait"),
        }
        anchor, bound, reason = checks[s.phase]
        if anchor is not None and (self._ordinal - anchor) > bound:
            self._resolve(s, reason, bar.close_ts_utc, bar.trading_day, out)

    # ── step 3: price-action transitions ────────────────────────────────────
    def _apply_transitions(self, inp: IfvgStepInput, out: list[IfvgEmission]) -> None:
        s = self._setup
        bar = inp.bar_1m
        if s is None:
            self._scan_taps(inp, out)
            return
        # Manipulation-leg accumulators run from the lock bar through inversion.
        if s.phase in ("S2", "S3") and s.lock_ordinal is not None:
            s.swing_min_low = (
                bar.low_ticks if s.swing_min_low is None else min(s.swing_min_low, bar.low_ticks)
            )
            s.swing_max_high = (
                bar.high_ticks if s.swing_max_high is None else max(s.swing_max_high, bar.high_ticks)
            )
            if s.sweep is not None:
                s.sweep.on_bar(bar)
        if s.phase == "S1":
            self._try_lock(inp, s, out)
        elif s.phase == "S3":
            self._try_inversion(inp, s, out)
        elif s.phase == "S4":
            self._watch_entries(inp, s, out)
        elif s.phase == "S5":
            self._walk_trade(inp, s, out)

    def _scan_taps(self, inp: IfvgStepInput, out: list[IfvgEmission]) -> None:
        bar = inp.bar_1m
        taps = [
            state
            for state in inp.htf_live
            if state.fvg.confirmed_ts_utc < bar.close_ts_utc
            and wick_overlaps(bar, state.fvg.gap_low_ticks, state.fvg.gap_high_ticks)
        ]
        if not taps:
            return
        # Rank: higher timeframe first (4H beats 1H), then newest confirmation.
        taps.sort(
            key=lambda st: (st.fvg.timeframe_seconds, st.fvg.confirmed_ts_utc), reverse=True
        )
        top_tf = taps[0].fvg.timeframe_seconds
        top_dirs = {st.fvg.direction for st in taps if st.fvg.timeframe_seconds == top_tf}
        conflicted = len(top_dirs) > 1
        nearest_kind, nearest_dist = self._nearest_level(inp, bar)
        winner_state = None if conflicted else taps[0]
        live_count = len(inp.htf_live)
        for rank, state in enumerate(taps):
            gap = state.fvg
            selected = winner_state is not None and state is winner_state
            drop = None
            if conflicted:
                drop = "conflicted"
            elif not selected:
                drop = "outranked"
            self._count("htf_taps")
            if conflicted:
                self._count("taps_conflicted")
            setup_id = ""
            if selected:
                setup_id = self._new_setup_id(bar.trading_day)
            out.append(
                IfvgEmission(
                    kind="htf_tap",
                    record=HtfTapRecord(
                        envelope=self._env(bar.close_ts_utc, bar.trading_day, setup_id),
                        htf_tf_seconds=gap.timeframe_seconds,
                        fvg=gap,
                        direction=self._gap_direction_to_trade(gap.direction),
                        penetration_ticks=penetration_ticks(bar, gap),
                        ce_reached=ce_reached(bar, gap),
                        htf_age_seconds=int(
                            (bar.close_ts_utc - gap.confirmed_ts_utc).total_seconds()
                        ),
                        remaining_fraction=state.remaining_fraction(),
                        registry_live_count=live_count,
                        rank=rank,
                        conflicted=conflicted,
                        nearest_level_kind=nearest_kind,
                        nearest_level_distance_ticks=nearest_dist,
                        session_engine=inp.session_engine,
                        session_doc=inp.session_doc,
                        selected=selected,
                        drop_reason=drop,
                    ),
                )
            )
            if selected:
                self._count("setups_born")
                self._setup = _Setup(
                    setup_id=setup_id,
                    phase="S1",
                    direction=self._gap_direction_to_trade(gap.direction),
                    htf=gap,
                    tap_ts_utc=bar.close_ts_utc,
                    tap_ordinal=self._ordinal,
                )

    def _tap_scan_while_occupied(self, inp: IfvgStepInput, out: list[IfvgEmission]) -> None:
        """Taps that land while a setup is alive: recorded (slot_occupied), not acted on."""
        bar = inp.bar_1m
        nearest_kind, nearest_dist = self._nearest_level(inp, bar)
        for state in inp.htf_live:
            gap = state.fvg
            if gap.confirmed_ts_utc >= bar.close_ts_utc:
                continue
            if not wick_overlaps(bar, gap.gap_low_ticks, gap.gap_high_ticks):
                continue
            self._count("htf_taps")
            self._count("taps_slot_occupied")
            out.append(
                IfvgEmission(
                    kind="htf_tap",
                    record=HtfTapRecord(
                        envelope=self._env(bar.close_ts_utc, bar.trading_day, ""),
                        htf_tf_seconds=gap.timeframe_seconds,
                        fvg=gap,
                        direction=self._gap_direction_to_trade(gap.direction),
                        penetration_ticks=penetration_ticks(bar, gap),
                        ce_reached=ce_reached(bar, gap),
                        htf_age_seconds=int(
                            (bar.close_ts_utc - gap.confirmed_ts_utc).total_seconds()
                        ),
                        remaining_fraction=state.remaining_fraction(),
                        registry_live_count=len(inp.htf_live),
                        rank=-1,
                        conflicted=False,
                        nearest_level_kind=nearest_kind,
                        nearest_level_distance_ticks=nearest_dist,
                        session_engine=inp.session_engine,
                        session_doc=inp.session_doc,
                        selected=False,
                        drop_reason="slot_occupied",
                    ),
                )
            )

    def _try_lock(self, inp: IfvgStepInput, s: _Setup, out: list[IfvgEmission]) -> None:
        bar = inp.bar_1m
        if (
            s.parent is None
            or s.parent_selected_ordinal is None
            or s.parent_selected_ordinal >= self._ordinal
        ):
            return
        if not wick_overlaps(bar, s.parent.gap_low_ticks, s.parent.gap_high_ticks):
            return
        s.phase = "S2"
        s.lock_ts_utc = bar.close_ts_utc
        s.lock_ordinal = self._ordinal
        s.swing_min_low = bar.low_ticks
        s.swing_max_high = bar.high_ticks
        s.sweep = SweepTracker(
            direction=s.direction,
            pools=self._build_pools(inp),
            armed_ts=bar.close_ts_utc,
        )
        s.sweep.on_bar(bar)
        self._count("parents_locked")
        out.append(
            IfvgEmission(
                kind="parent_lock",
                record=ParentLockRecord(
                    envelope=self._env(bar.close_ts_utc, bar.trading_day, s.setup_id),
                    parent_fvg_id=s.parent.fvg_id,
                    penetration_ticks=penetration_ticks(bar, s.parent),
                    ce_reached=ce_reached(bar, s.parent),
                    elapsed_1m_bars_since_selection=self._ordinal - s.parent_selected_ordinal,
                ),
            )
        )

    def _try_inversion(self, inp: IfvgStepInput, s: _Setup, out: list[IfvgEmission]) -> None:
        bar = inp.bar_1m
        if s.opposing is None or s.armed_ordinal is None or s.armed_ordinal >= self._ordinal:
            return
        if s.direction is Direction.LONG:
            through = body_closes_through(
                bar, boundary_ticks=s.opposing.gap_high_ticks, beyond=Side.HIGH
            )
            margin = close_through_margin_ticks(
                bar, boundary_ticks=s.opposing.gap_high_ticks, beyond=Side.HIGH
            )
        else:
            through = body_closes_through(
                bar, boundary_ticks=s.opposing.gap_low_ticks, beyond=Side.LOW
            )
            margin = close_through_margin_ticks(
                bar, boundary_ticks=s.opposing.gap_low_ticks, beyond=Side.LOW
            )
        if not through:
            return
        s.phase = "S4"
        s.inversion_ts_utc = bar.close_ts_utc
        s.inversion_ordinal = self._ordinal
        s.sweep_result = s.sweep.result() if s.sweep is not None else None
        self._count("inversions")
        out.append(
            IfvgEmission(
                kind="inversion",
                record=InversionRecord(
                    envelope=self._env(bar.close_ts_utc, bar.trading_day, s.setup_id),
                    opposing_fvg_id=s.opposing.fvg_id,
                    close_through_margin_ticks=margin,
                    bars_armed_to_inversion=self._ordinal - s.armed_ordinal,
                    opposing_size_ticks=s.opposing.size_ticks,
                    sweep=s.sweep_result
                    if s.sweep_result is not None
                    else SweepResult(False, (), 0, None, None, None),
                ),
            )
        )

    def _watch_entries(self, inp: IfvgStepInput, s: _Setup, out: list[IfvgEmission]) -> None:
        bar = inp.bar_1m
        if s.inversion_ordinal is None or s.inversion_ordinal >= self._ordinal:
            return  # never on the inversion candle
        candidates: list[tuple[str, Fvg | None]] = []
        want = GapDirection.BULLISH if s.direction is Direction.LONG else GapDirection.BEARISH
        for gap in inp.new_fvgs.get(60, ()):
            if gap.direction is want and gap.confirmed_ts_utc > s.inversion_ts_utc:  # type: ignore[operator]
                candidates.append(("fresh_fvg_continuation", gap))
        assert s.opposing is not None
        if wick_overlaps(bar, s.opposing.gap_low_ticks, s.opposing.gap_high_ticks):
            candidates.append(("ifvg_retest", None))
        if not candidates:
            return
        entry = bar.close_ticks
        if s.direction is Direction.LONG:
            stop = s.swing_min_low - self._cfg.sl_buffer_ticks  # type: ignore[operator]
            risk = entry - stop
        else:
            stop = s.swing_max_high + self._cfg.sl_buffer_ticks  # type: ignore[operator]
            risk = stop - entry
        tp_offset = round(risk * self._cfg.tp_r_multiple)
        tp = entry + tp_offset if s.direction is Direction.LONG else entry - tp_offset
        parent = s.parent
        assert parent is not None
        entry_to_parent = interval_distance_ticks(
            entry, entry, parent.gap_low_ticks, parent.gap_high_ticks
        )
        for family, gap in candidates:
            self._count(f"entry_candidates_{family}")
            selectable = family == self._cfg.selected_entry_family and s.phase == "S4"
            drop: str | None = None
            if not selectable:
                drop = "family_not_selected" if s.phase == "S4" else "already_in_trade"
            elif risk < 1:
                drop = "risk_lt_min"
            selected = selectable and risk >= 1
            out.append(
                IfvgEmission(
                    kind="entry_candidate",
                    record=EntryCandidateRecord(
                        envelope=self._env(bar.close_ts_utc, bar.trading_day, s.setup_id),
                        entry_family=family,
                        entry_fvg=gap,
                        entry_ticks=entry,
                        stop_ticks=stop,
                        risk_ticks=risk,
                        tp_ticks=tp,
                        bars_since_inversion=self._ordinal - s.inversion_ordinal,
                        entry_to_parent_ticks=entry_to_parent,
                        in_engine_session=inp.session_engine,
                        in_doc_session=inp.session_doc,
                        selected=selected,
                        drop_reason=drop,
                    ),
                )
            )
            if selected:
                s.phase = "S5"
                s.entry_family = family
                s.entry_ticks = entry
                s.stop_ticks = stop
                s.tp_ticks = tp
                s.entry_ts_utc = bar.close_ts_utc
                s.entry_ordinal = self._ordinal
                s.mfe_ticks = 0
                s.mae_ticks = 0
                self._count("entries_selected")

    def _walk_trade(self, inp: IfvgStepInput, s: _Setup, out: list[IfvgEmission]) -> None:
        bar = inp.bar_1m
        if s.entry_ordinal is None or self._ordinal <= s.entry_ordinal:
            return
        assert s.entry_ticks is not None and s.stop_ticks is not None and s.tp_ticks is not None
        if s.direction is Direction.LONG:
            s.mfe_ticks = max(s.mfe_ticks, bar.high_ticks - s.entry_ticks)
            s.mae_ticks = max(s.mae_ticks, s.entry_ticks - bar.low_ticks)
            hit_stop = bar.low_ticks <= s.stop_ticks
            hit_tp = bar.high_ticks >= s.tp_ticks
        else:
            s.mfe_ticks = max(s.mfe_ticks, s.entry_ticks - bar.low_ticks)
            s.mae_ticks = max(s.mae_ticks, bar.high_ticks - s.entry_ticks)
            hit_stop = bar.high_ticks >= s.stop_ticks
            hit_tp = bar.low_ticks <= s.tp_ticks
        # MAE-first conservatism: a bar that reaches both resolves as the loss
        # (kernel ladder agreement is pinned by test_ifvg_labels).
        if hit_stop:
            self._resolve(s, "resolved_sl", bar.close_ts_utc, bar.trading_day, out)
        elif hit_tp:
            self._resolve(s, "resolved_tp", bar.close_ts_utc, bar.trading_day, out)

    # ── step 4: new-structure intake ─────────────────────────────────────────
    def _apply_intake(self, inp: IfvgStepInput, out: list[IfvgEmission]) -> None:
        s = self._setup
        if s is None:
            return
        if s.tap_ordinal != self._ordinal:
            # Taps landing while the slot is busy are still recorded — but not
            # on the setup's own birth bar (those were the _scan_taps records).
            self._tap_scan_while_occupied(inp, out)
        if s.phase == "S1":
            self._intake_parent_candidates(inp, s, out)
        elif s.phase in ("S2", "S3"):
            self._intake_opposing(inp, s, out)

    def _intake_parent_candidates(
        self, inp: IfvgStepInput, s: _Setup, out: list[IfvgEmission]
    ) -> None:
        bar = inp.bar_1m
        want = GapDirection.BULLISH if s.direction is Direction.LONG else GapDirection.BEARISH
        arrivals: list[Fvg] = []
        for tf in self._cfg.parent_tf_seconds:
            for gap in inp.new_fvgs.get(tf, ()):
                if gap.direction is want:
                    arrivals.append(gap)
        if not arrivals:
            return
        # Doc priority: higher parent TF outranks; newest wins within a TF.
        arrivals.sort(key=lambda g: (g.timeframe_seconds, g.confirmed_ts_utc), reverse=True)
        for rank, gap in enumerate(arrivals):
            distance = interval_distance_ticks(
                gap.gap_low_ticks,
                gap.gap_high_ticks,
                s.htf.gap_low_ticks,
                s.htf.gap_high_ticks,
            )
            self._count("parent_candidates")
            selected = False
            drop: str | None = None
            if distance > self._cfg.parent_htf_distance_ticks_max:
                drop = "distance_gt_capture"
            elif s.parent is None:
                selected = True
            elif gap.timeframe_seconds > s.parent.timeframe_seconds or (
                gap.timeframe_seconds == s.parent.timeframe_seconds
                and gap.confirmed_ts_utc > s.parent.confirmed_ts_utc
            ):
                # Outranks (higher TF) or same-TF STRICTLY-newer wins: replace;
                # the displaced candidate is re-emitted with its drop reason.
                # Equal-instant same-TF arrivals keep the incumbent (deterministic).
                out.append(
                    IfvgEmission(
                        kind="parent_candidate",
                        record=ParentCandidateRecord(
                            envelope=self._env(bar.close_ts_utc, bar.trading_day, s.setup_id),
                            parent_tf_seconds=s.parent.timeframe_seconds,
                            fvg=s.parent,
                            distance_to_htf_ticks=interval_distance_ticks(
                                s.parent.gap_low_ticks,
                                s.parent.gap_high_ticks,
                                s.htf.gap_low_ticks,
                                s.htf.gap_high_ticks,
                            ),
                            elapsed_1m_bars_since_tap=self._ordinal - s.tap_ordinal,
                            confirmed_after=s.parent.confirmed_ts_utc > s.tap_ts_utc,
                            fully_formed_after=s.parent.a_open_ts_utc >= s.tap_ts_utc,
                            rank=-1,
                            selected=False,
                            drop_reason="replaced_by_newer",
                        ),
                    )
                )
                self._count("parents_replaced")
                selected = True
            else:
                drop = "outranked"
            out.append(
                IfvgEmission(
                    kind="parent_candidate",
                    record=ParentCandidateRecord(
                        envelope=self._env(bar.close_ts_utc, bar.trading_day, s.setup_id),
                        parent_tf_seconds=gap.timeframe_seconds,
                        fvg=gap,
                        distance_to_htf_ticks=distance,
                        elapsed_1m_bars_since_tap=self._ordinal - s.tap_ordinal,
                        confirmed_after=gap.confirmed_ts_utc > s.tap_ts_utc,
                        fully_formed_after=gap.a_open_ts_utc >= s.tap_ts_utc,
                        rank=rank,
                        selected=selected,
                        drop_reason=drop,
                    ),
                )
            )
            if selected:
                s.parent = gap
                s.parent_selected_ordinal = self._ordinal

    def _intake_opposing(self, inp: IfvgStepInput, s: _Setup, out: list[IfvgEmission]) -> None:
        bar = inp.bar_1m
        counter = GapDirection.BEARISH if s.direction is Direction.LONG else GapDirection.BULLISH
        assert s.parent is not None
        for gap in inp.new_fvgs.get(60, ()):
            if gap.direction is not counter:
                continue
            distance = interval_distance_ticks(
                gap.gap_low_ticks,
                gap.gap_high_ticks,
                s.parent.gap_low_ticks,
                s.parent.gap_high_ticks,
            )
            self._count("opposing_candidates")
            if distance > self._cfg.opposing_parent_distance_ticks_max:
                out.append(
                    self._opposing_emission(
                        s, gap, distance, bar, selected=False, drop="distance_gt_capture"
                    )
                )
                continue
            if s.opposing is not None:
                # §14.7: the just-run inversion check (step 3) precedes any
                # replacement; the displaced gap is recorded.
                out.append(
                    self._opposing_emission(
                        s,
                        s.opposing,
                        interval_distance_ticks(
                            s.opposing.gap_low_ticks,
                            s.opposing.gap_high_ticks,
                            s.parent.gap_low_ticks,
                            s.parent.gap_high_ticks,
                        ),
                        bar,
                        selected=False,
                        drop="replaced_by_newer",
                    )
                )
                self._count("opposing_replaced")
            s.opposing = gap
            s.armed_ts_utc = bar.close_ts_utc
            s.armed_ordinal = self._ordinal
            if s.phase == "S2":
                s.phase = "S3"
                self._count("opposing_armed")
            out.append(self._opposing_emission(s, gap, distance, bar, selected=True, drop=None))

    def _opposing_emission(
        self,
        s: _Setup,
        gap: Fvg,
        distance: int,
        bar: Bar,
        *,
        selected: bool,
        drop: str | None,
    ) -> IfvgEmission:
        return IfvgEmission(
            kind="opposing",
            record=OpposingGapRecord(
                envelope=self._env(bar.close_ts_utc, bar.trading_day, s.setup_id),
                fvg=gap,
                distance_to_parent_ticks=distance,
                elapsed_1m_bars_since_lock=(
                    self._ordinal - s.lock_ordinal if s.lock_ordinal is not None else 0
                ),
                confirmed_after=(
                    gap.confirmed_ts_utc > s.lock_ts_utc if s.lock_ts_utc is not None else False
                ),
                fully_formed_after=(
                    gap.a_open_ts_utc >= s.lock_ts_utc if s.lock_ts_utc is not None else False
                ),
                selected=selected,
                drop_reason=drop,
            ),
        )

    # ── shared measurement helpers ───────────────────────────────────────────
    def _nearest_level(self, inp: IfvgStepInput, bar: Bar) -> tuple[str | None, int | None]:
        best_kind: str | None = None
        best_dist: int | None = None
        for level in inp.levels:
            if level.available_from is not None and level.available_from > bar.close_ts_utc:
                continue
            price_ticks = round(level.price / self._cfg.tick_size)
            dist = abs(bar.close_ticks - price_ticks)
            if best_dist is None or dist < best_dist:
                best_kind, best_dist = level.name, dist
        return best_kind, best_dist

    def _build_pools(self, inp: IfvgStepInput) -> tuple[LevelPool, ...]:
        pools = [
            LevelPool(
                kind=level.name,
                price_ticks=round(level.price / self._cfg.tick_size),
                side=level.side,
                available_from=level.available_from,
            )
            for level in inp.levels
        ]
        pools.extend(
            LevelPool("swing_high", p.price_ticks, Side.HIGH, p.confirmed_ts_utc)
            for p in inp.recent_swing_highs
        )
        pools.extend(
            LevelPool("swing_low", p.price_ticks, Side.LOW, p.confirmed_ts_utc)
            for p in inp.recent_swing_lows
        )
        return tuple(pools)

    def _new_setup_id(self, trading_day: date) -> str:
        if self._seq_day != trading_day:
            self._seq_day = trading_day
            self._seq = 0
        self._seq += 1
        return f"ifvg:{trading_day.isoformat()}:{self._seq:04d}"
