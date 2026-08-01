"""Causal confirmed-swing market structure for deterministic context features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Sequence
from uuid import UUID

from strategy_core.structures.context import (
    AnchorStatus,
    ContextIdentity,
    ContextRecord,
    MissingReason,
    canonical_sha256,
    context_uuid,
    record_provenance,
)
from strategy_core.types import Bar, BarKind, Direction, Side

__all__ = [
    "BreakDirection",
    "BreakType",
    "ConfirmedSwingEvidence",
    "ConfirmedSwingSeed",
    "MarketStructureState",
    "MarketStructureTracker",
    "MarketStructureTrackerSnapshot",
    "MtfConfluenceSnapshot",
    "Relationship",
    "StructureDirection",
    "StructureTransitionDelta",
    "build_mtf_snapshot",
    "build_structure_delta",
    "confirmed_swing_from_seed",
    "confirmed_swing_seed",
]

MARKET_STRUCTURE_SNAPSHOT_SCHEMA_VERSION = 2


class Relationship(StrEnum):
    HIGHER = "higher"
    EQUAL = "equal"
    LOWER = "lower"
    INSUFFICIENT = "insufficient"


class StructureDirection(StrEnum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class BreakType(StrEnum):
    NONE = "none"
    INITIAL_BREAK = "initial_break"
    BOS = "bos"
    CHOCH = "choch"


class BreakDirection(StrEnum):
    NONE = "none"
    BULLISH = "bullish"
    BEARISH = "bearish"


def _bar_cursor(bar: Bar) -> str:
    return (
        f"{bar.availability_ts_utc.isoformat()}|{bar.timeframe_ticks}|"
        f"{bar.trading_day.isoformat()}|{bar.bar_id}"
    )


def _relationship(newest: int, prior: int) -> Relationship:
    if newest > prior:
        return Relationship.HIGHER
    if newest < prior:
        return Relationship.LOWER
    return Relationship.EQUAL


def _setup_sign(direction: Direction | str) -> int:
    value = direction.value if isinstance(direction, Direction) else str(direction)
    return 1 if value.lower() == "long" else -1


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfirmedSwingEvidence(ContextRecord):
    swing_id: UUID
    source_timeframe: str
    source_timeframe_seconds: int
    side: Side
    price_ticks: int
    pivot_bar_id: str
    pivot_ts: datetime
    confirmation_bar_id: str
    confirmation_ts: datetime
    availability_cursor: str
    confirmation_strength: int


ConfirmedSwingSeed = tuple[
    UUID,
    str,
    int,
    Side,
    int,
    str,
    datetime,
    str,
    datetime,
    str,
    int,
]


def confirmed_swing_seed(swing: ConfirmedSwingEvidence) -> ConfirmedSwingSeed:
    """Compact, lossless seed form without repeated context provenance."""

    return (
        swing.swing_id,
        swing.source_timeframe,
        swing.source_timeframe_seconds,
        swing.side,
        swing.price_ticks,
        swing.pivot_bar_id,
        swing.pivot_ts,
        swing.confirmation_bar_id,
        swing.confirmation_ts,
        swing.availability_cursor,
        swing.confirmation_strength,
    )


def confirmed_swing_from_seed(
    seed: ConfirmedSwingSeed,
    *,
    identity: ContextIdentity,
) -> ConfirmedSwingEvidence:
    """Restore the exact evidence envelope implied by a confirmed swing."""

    (
        swing_id,
        source_timeframe,
        source_timeframe_seconds,
        side,
        price_ticks,
        pivot_bar_id,
        pivot_ts,
        confirmation_bar_id,
        confirmation_ts,
        availability_cursor,
        confirmation_strength,
    ) = seed
    return ConfirmedSwingEvidence(
        **record_provenance(
            identity,
            as_of_ts=confirmation_ts,
            as_of_cursor=availability_cursor,
            source_close_ts=confirmation_ts,
            source_confirmed_ts=confirmation_ts,
            valid=True,
            warmup_complete=True,
            source_available=True,
            missing_reason=None,
        ),
        swing_id=swing_id,
        source_timeframe=source_timeframe,
        source_timeframe_seconds=source_timeframe_seconds,
        side=side,
        price_ticks=price_ticks,
        pivot_bar_id=pivot_bar_id,
        pivot_ts=pivot_ts,
        confirmation_bar_id=confirmation_bar_id,
        confirmation_ts=confirmation_ts,
        availability_cursor=availability_cursor,
        confirmation_strength=confirmation_strength,
    )


@dataclass(frozen=True, slots=True)
class _BreakEvidence:
    break_id: UUID
    break_type: BreakType
    break_direction: BreakDirection
    broken_swing_id: UUID
    break_bar_id: str
    break_ts: datetime
    break_cursor: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketStructureState(ContextRecord):
    structure_state_id: UUID
    source_timeframe: str
    source_timeframe_seconds: int
    anchor_status: AnchorStatus
    latest_high_swing_id: UUID | None
    latest_low_swing_id: UUID | None
    prior_high_swing_id: UUID | None
    prior_low_swing_id: UUID | None
    high_relationship: Relationship
    low_relationship: Relationship
    swing_sequence_state: str
    structure_direction: StructureDirection | None
    last_break_id: UUID | None
    last_break_type: BreakType | None
    last_break_direction: BreakDirection | None
    broken_swing_id: UUID | None
    break_bar_id: str | None
    break_ts: datetime | None
    bars_since_break: int | None
    minutes_since_break: float | None
    state_age_bars: int | None
    structure_alignment: int | None
    break_alignment: int | None
    last_confirmed_swing_high_ticks: int | None
    last_confirmed_swing_low_ticks: int | None

    def comparison_tuple(self) -> tuple[Any, ...]:
        return (
            self.high_relationship,
            self.low_relationship,
            self.structure_direction,
            self.last_break_id,
            self.latest_high_swing_id,
            self.latest_low_swing_id,
        )


@dataclass(frozen=True, slots=True)
class MarketStructureTrackerSnapshot:
    schema_version: int
    timeframe: str
    timeframe_seconds: int
    anchor_status: AnchorStatus
    strength: int
    capacity: int
    window: tuple[Bar, ...]
    highs: tuple[ConfirmedSwingSeed, ...]
    lows: tuple[ConfirmedSwingSeed, ...]
    unfired_high_swing_ids: tuple[UUID, ...]
    unfired_low_swing_ids: tuple[UUID, ...]
    direction: StructureDirection
    last_break: _BreakEvidence | None
    bars_since_break: int | None
    state_age_bars: int


class MarketStructureTracker:
    """Bounded strict fractal tracker plus one-shot close-break FSM."""

    def __init__(
        self,
        *,
        timeframe: str,
        timeframe_seconds: int,
        identity: ContextIdentity,
        anchor_status: AnchorStatus = AnchorStatus.RATIFIED,
        strength: int = 3,
        capacity: int = 64,
    ) -> None:
        if strength < 1 or capacity < 2:
            raise ValueError("market structure requires strength >= 1 and capacity >= 2")
        self.timeframe = timeframe
        self.timeframe_seconds = timeframe_seconds
        self.identity = identity
        self.anchor_status = anchor_status
        self.strength = strength
        self.capacity = capacity
        self._window: list[Bar] = []
        self._highs: list[ConfirmedSwingEvidence] = []
        self._lows: list[ConfirmedSwingEvidence] = []
        self._fired: set[UUID] = set()
        self._unfired_highs: list[ConfirmedSwingEvidence] = []
        self._unfired_lows: list[ConfirmedSwingEvidence] = []
        self._direction = StructureDirection.NEUTRAL
        self._last_break: _BreakEvidence | None = None
        self._bars_since_break: int | None = None
        self._state_age_bars = 0
        self._last_source_bar: Bar | None = None

    @property
    def confirmed_swings(self) -> tuple[ConfirmedSwingEvidence, ...]:
        return tuple(sorted((*self._highs, *self._lows), key=lambda item: (item.confirmation_ts, str(item.swing_id))))

    def on_bar_closed(self, bar: Bar) -> tuple[ConfirmedSwingEvidence, ...]:
        if bar.kind is not BarKind.TIME:
            raise ValueError("context market structure accepts TIME bars only")
        if not bar.is_complete:
            return ()
        if bar.timeframe_ticks != self.timeframe_seconds:
            raise ValueError(
                f"bar timeframe {bar.timeframe_ticks}s != tracker {self.timeframe_seconds}s"
            )
        if self._last_source_bar is not None:
            prior_key = (
                self._last_source_bar.availability_ts_utc,
                self._last_source_bar.bar_id,
            )
            if (bar.availability_ts_utc, bar.bar_id) <= prior_key:
                raise ValueError("market-structure bars must be strictly ordered")

        if self._bars_since_break is not None:
            self._bars_since_break += 1
        self._state_age_bars += 1

        self._window.append(bar)
        span = 2 * self.strength + 1
        if len(self._window) > span:
            del self._window[0]

        # Evaluate breaks against swings available before this bar's close.  New pivots
        # confirmed by ``bar`` are appended only afterward, so the confirming bar can
        # never break the swing it just made available.
        self._evaluate_break(bar)
        confirmed = self._confirm_current_window(bar) if len(self._window) == span else ()
        for swing in confirmed:
            target = self._highs if swing.side is Side.HIGH else self._lows
            unfired = (
                self._unfired_highs
                if swing.side is Side.HIGH
                else self._unfired_lows
            )
            target.append(swing)
            unfired.append(swing)
            if len(target) > self.capacity:
                evicted = target.pop(0)
                self._fired.discard(evicted.swing_id)
                if evicted in unfired:
                    unfired.remove(evicted)
        self._last_source_bar = bar
        return confirmed

    def _confirm_current_window(self, confirmation_bar: Bar) -> tuple[ConfirmedSwingEvidence, ...]:
        pivot = self._window[self.strength]
        high_qualifies = True
        low_qualifies = True
        for index, item in enumerate(self._window):
            if index == self.strength:
                continue
            high_qualifies = high_qualifies and pivot.high_ticks > item.high_ticks
            low_qualifies = low_qualifies and pivot.low_ticks < item.low_ticks
            if not high_qualifies and not low_qualifies:
                return ()
        qualifying = (
            ((Side.HIGH, pivot.high_ticks, True),) if high_qualifies else ()
        ) + (((Side.LOW, pivot.low_ticks, True),) if low_qualifies else ())
        if not qualifying:
            return ()
        out: list[ConfirmedSwingEvidence] = []
        cursor = _bar_cursor(confirmation_bar)
        common = record_provenance(
            self.identity,
            as_of_ts=confirmation_bar.availability_ts_utc,
            as_of_cursor=cursor,
            source_close_ts=confirmation_bar.availability_ts_utc,
            source_confirmed_ts=confirmation_bar.availability_ts_utc,
            valid=True,
            warmup_complete=True,
            source_available=True,
            missing_reason=None,
        )
        for side, price, _qualifies in qualifying:
            swing_id = context_uuid(
                self.identity.feature_formula_version,
                self.timeframe_seconds,
                side.value.lower(),
                pivot.bar_id,
                confirmation_bar.bar_id,
            )
            out.append(
                ConfirmedSwingEvidence(
                    **common,
                    swing_id=swing_id,
                    source_timeframe=self.timeframe,
                    source_timeframe_seconds=self.timeframe_seconds,
                    side=side,
                    price_ticks=price,
                    pivot_bar_id=pivot.bar_id,
                    pivot_ts=pivot.availability_ts_utc,
                    confirmation_bar_id=confirmation_bar.bar_id,
                    confirmation_ts=confirmation_bar.availability_ts_utc,
                    availability_cursor=cursor,
                    confirmation_strength=self.strength,
                )
            )
        return tuple(out)

    def _evaluate_break(self, bar: Bar) -> None:
        high = self._unfired_highs[-1] if self._unfired_highs else None
        low = self._unfired_lows[-1] if self._unfired_lows else None
        candidate: tuple[BreakDirection, ConfirmedSwingEvidence] | None = None
        bar_key = (bar.availability_ts_utc, bar.bar_id)
        if (
            high is not None
            and bar.close_ticks > high.price_ticks
            and bar_key > (high.confirmation_ts, high.confirmation_bar_id)
        ):
            candidate = (BreakDirection.BULLISH, high)
        elif (
            low is not None
            and bar.close_ticks < low.price_ticks
            and bar_key > (low.confirmation_ts, low.confirmation_bar_id)
        ):
            candidate = (BreakDirection.BEARISH, low)
        if candidate is None:
            return
        break_direction, swing = candidate
        old_direction = self._direction
        new_direction = (
            StructureDirection.BULLISH
            if break_direction is BreakDirection.BULLISH
            else StructureDirection.BEARISH
        )
        if old_direction is StructureDirection.NEUTRAL:
            break_type = BreakType.INITIAL_BREAK
        elif old_direction is new_direction:
            break_type = BreakType.BOS
        else:
            break_type = BreakType.CHOCH
        cursor = _bar_cursor(bar)
        self._last_break = _BreakEvidence(
            break_id=context_uuid(
                self.identity.feature_formula_version,
                self.timeframe_seconds,
                break_type,
                break_direction,
                swing.swing_id,
                bar.bar_id,
            ),
            break_type=break_type,
            break_direction=break_direction,
            broken_swing_id=swing.swing_id,
            break_bar_id=bar.bar_id,
            break_ts=bar.availability_ts_utc,
            break_cursor=cursor,
        )
        self._fired.add(swing.swing_id)
        unfired = (
            self._unfired_highs
            if swing.side is Side.HIGH
            else self._unfired_lows
        )
        unfired.remove(swing)
        self._bars_since_break = 0
        if new_direction is not old_direction:
            self._direction = new_direction
            self._state_age_bars = 0

    def state(
        self,
        setup_direction: Direction | str,
        *,
        as_of_ts: datetime | None = None,
        as_of_cursor: str | None = None,
    ) -> MarketStructureState:
        if self._last_source_bar is None:
            if as_of_ts is None or as_of_cursor is None:
                raise RuntimeError(
                    "as_of_ts/as_of_cursor are required before the first source bar"
                )
            source_close_ts = None
            cursor = as_of_cursor
            record_ts = as_of_ts
        else:
            source_close_ts = self._last_source_bar.availability_ts_utc
            cursor = as_of_cursor or _bar_cursor(self._last_source_bar)
            record_ts = as_of_ts or self._last_source_bar.availability_ts_utc
        high_rel = (
            _relationship(self._highs[-1].price_ticks, self._highs[-2].price_ticks)
            if len(self._highs) >= 2
            else Relationship.INSUFFICIENT
        )
        low_rel = (
            _relationship(self._lows[-1].price_ticks, self._lows[-2].price_ticks)
            if len(self._lows) >= 2
            else Relationship.INSUFFICIENT
        )
        valid = len(self._highs) >= 2 and len(self._lows) >= 2
        sequence = (
            f"{high_rel.value}_high__{low_rel.value}_low"
            if valid
            else "insufficient"
        )
        sign = _setup_sign(setup_direction)
        direction_sign = {
            StructureDirection.BULLISH: 1,
            StructureDirection.NEUTRAL: 0,
            StructureDirection.BEARISH: -1,
        }[self._direction]
        break_sign = {
            BreakDirection.BULLISH: 1,
            BreakDirection.BEARISH: -1,
            BreakDirection.NONE: 0,
        }[
            self._last_break.break_direction
            if self._last_break is not None
            else BreakDirection.NONE
        ]
        source_confirmed = max(
            (item.confirmation_ts for item in (*self._highs, *self._lows)),
            default=None,
        )
        payload = {
            "timeframe": self.timeframe,
            "cursor": cursor,
            "highs": [str(item.swing_id) for item in self._highs[-2:]],
            "lows": [str(item.swing_id) for item in self._lows[-2:]],
            "direction": self._direction,
            "break": None if self._last_break is None else self._last_break.break_id,
            "bars_since_break": self._bars_since_break,
            "state_age_bars": self._state_age_bars,
            "setup_sign": sign,
        }
        state_id = context_uuid(
            self.identity.feature_formula_version,
            self.identity.feature_schema_hash,
            self.identity.context_config_hash,
            self.timeframe_seconds,
            cursor,
            canonical_sha256(payload),
        )
        last_break = self._last_break
        missing = None if valid else MissingReason.INSUFFICIENT_CONFIRMED_SWINGS
        return MarketStructureState(
            **record_provenance(
                self.identity,
                as_of_ts=as_of_ts or record_ts,
                as_of_cursor=cursor,
                source_close_ts=source_close_ts,
                source_confirmed_ts=source_confirmed,
                valid=valid,
                warmup_complete=valid,
                source_available=source_close_ts is not None,
                missing_reason=(
                    MissingReason.SOURCE_UNAVAILABLE
                    if source_close_ts is None
                    else missing
                ),
            ),
            structure_state_id=state_id,
            source_timeframe=self.timeframe,
            source_timeframe_seconds=self.timeframe_seconds,
            anchor_status=self.anchor_status,
            latest_high_swing_id=self._highs[-1].swing_id if self._highs else None,
            latest_low_swing_id=self._lows[-1].swing_id if self._lows else None,
            prior_high_swing_id=self._highs[-2].swing_id if len(self._highs) >= 2 else None,
            prior_low_swing_id=self._lows[-2].swing_id if len(self._lows) >= 2 else None,
            high_relationship=high_rel,
            low_relationship=low_rel,
            swing_sequence_state=sequence,
            structure_direction=self._direction if valid else None,
            last_break_id=last_break.break_id if valid and last_break else None,
            last_break_type=last_break.break_type if valid and last_break else (BreakType.NONE if valid else None),
            last_break_direction=(
                last_break.break_direction if valid and last_break else (BreakDirection.NONE if valid else None)
            ),
            broken_swing_id=last_break.broken_swing_id if valid and last_break else None,
            break_bar_id=last_break.break_bar_id if valid and last_break else None,
            break_ts=last_break.break_ts if valid and last_break else None,
            bars_since_break=self._bars_since_break if valid and last_break else None,
            minutes_since_break=(
                ((as_of_ts or record_ts) - last_break.break_ts).total_seconds() / 60
                if valid and last_break
                else None
            ),
            state_age_bars=self._state_age_bars if valid else None,
            structure_alignment=direction_sign * sign if valid else None,
            break_alignment=break_sign * sign if valid and last_break else None,
            last_confirmed_swing_high_ticks=self._highs[-1].price_ticks if valid else None,
            last_confirmed_swing_low_ticks=self._lows[-1].price_ticks if valid else None,
        )

    def snapshot(self) -> MarketStructureTrackerSnapshot:
        return MarketStructureTrackerSnapshot(
            schema_version=MARKET_STRUCTURE_SNAPSHOT_SCHEMA_VERSION,
            timeframe=self.timeframe,
            timeframe_seconds=self.timeframe_seconds,
            anchor_status=self.anchor_status,
            strength=self.strength,
            capacity=self.capacity,
            window=tuple(self._window[-2 * self.strength :]),
            highs=tuple(confirmed_swing_seed(item) for item in self._highs),
            lows=tuple(confirmed_swing_seed(item) for item in self._lows),
            unfired_high_swing_ids=tuple(
                sorted((item.swing_id for item in self._unfired_highs), key=str)
            ),
            unfired_low_swing_ids=tuple(
                sorted((item.swing_id for item in self._unfired_lows), key=str)
            ),
            direction=self._direction,
            last_break=self._last_break,
            bars_since_break=self._bars_since_break,
            state_age_bars=self._state_age_bars,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: MarketStructureTrackerSnapshot,
        *,
        identity: ContextIdentity,
    ) -> MarketStructureTracker:
        if snapshot.schema_version != MARKET_STRUCTURE_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("market-structure snapshot version mismatch")
        tracker = cls(
            timeframe=snapshot.timeframe,
            timeframe_seconds=snapshot.timeframe_seconds,
            identity=identity,
            anchor_status=snapshot.anchor_status,
            strength=snapshot.strength,
            capacity=snapshot.capacity,
        )
        tracker._window = list(snapshot.window)
        tracker._highs = [
            confirmed_swing_from_seed(item, identity=identity) for item in snapshot.highs
        ]
        tracker._lows = [
            confirmed_swing_from_seed(item, identity=identity) for item in snapshot.lows
        ]
        unfired_high_ids = set(snapshot.unfired_high_swing_ids)
        unfired_low_ids = set(snapshot.unfired_low_swing_ids)
        high_ids = {item.swing_id for item in tracker._highs}
        low_ids = {item.swing_id for item in tracker._lows}
        if not unfired_high_ids.issubset(high_ids):
            raise ValueError("market-structure seed has unknown unfired high")
        if not unfired_low_ids.issubset(low_ids):
            raise ValueError("market-structure seed has unknown unfired low")
        tracker._fired = (high_ids - unfired_high_ids) | (
            low_ids - unfired_low_ids
        )
        tracker._unfired_highs = [
            item for item in tracker._highs if item.swing_id in unfired_high_ids
        ]
        tracker._unfired_lows = [
            item for item in tracker._lows if item.swing_id in unfired_low_ids
        ]
        tracker._direction = snapshot.direction
        tracker._last_break = snapshot.last_break
        tracker._bars_since_break = snapshot.bars_since_break
        tracker._state_age_bars = snapshot.state_age_bars
        tracker._last_source_bar = tracker._window[-1] if tracker._window else None
        return tracker


@dataclass(frozen=True, slots=True, kw_only=True)
class MtfConfluenceSnapshot(ContextRecord):
    mtf_snapshot_id: UUID
    setup_id: str
    setup_direction: str
    active_mtf_timeframes: tuple[str, ...]
    state_ids: tuple[UUID, ...]
    local_structure_state_id: UUID
    states: tuple[MarketStructureState, ...]
    local_state: MarketStructureState
    aligned_tf_count: int
    conflicting_tf_count: int
    neutral_tf_count: int
    valid_tf_count: int
    break_aligned_tf_count: int
    break_conflicting_tf_count: int
    highest_aligned_tf_seconds: int | None
    highest_conflicting_tf_seconds: int | None
    lowest_conflicting_tf_seconds: int | None
    contiguous_alignment_span: int
    contiguous_conflict_span: int
    adjacent_tf_transition_count: int
    lower_support_higher_conflict: bool | None
    lower_conflict_higher_support: bool | None
    execution_pullback_inside_htf_trend: bool | None
    execution_expansion_against_htf_trend: bool | None


def _max_run(values: Sequence[int | None], target: int) -> int:
    best = current = 0
    for value in values:
        if value == target:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def build_mtf_snapshot(
    *,
    identity: ContextIdentity,
    setup_id: str,
    setup_direction: Direction | str,
    mtf_states: Sequence[MarketStructureState],
    local_state: MarketStructureState,
    as_of_ts: datetime,
    as_of_cursor: str,
) -> MtfConfluenceSnapshot:
    states = tuple(mtf_states)
    alignments = [item.structure_alignment if item.valid else None for item in states]
    valid_count = sum(value is not None for value in alignments)
    aligned = sum(value == 1 for value in alignments)
    conflict = sum(value == -1 for value in alignments)
    neutral = sum(value == 0 for value in alignments)
    break_values = [item.break_alignment if item.valid else None for item in states]
    aligned_seconds = [
        state.source_timeframe_seconds
        for state, value in zip(states, alignments, strict=True)
        if value == 1
    ]
    conflict_seconds = [
        state.source_timeframe_seconds
        for state, value in zip(states, alignments, strict=True)
        if value == -1
    ]
    adjacent = sum(
        left is not None and right is not None and left != right
        for left, right in zip(alignments, alignments[1:])
    )
    lower = alignments[:5]
    higher = alignments[5:]
    groups_valid = len(lower) == 5 and len(higher) == 2 and all(
        value is not None for value in alignments
    )
    htf_valid = len(higher) == 2 and all(value is not None for value in higher)
    local_alignment = local_state.structure_alignment if local_state.valid else None
    setup_value = (
        setup_direction.value if isinstance(setup_direction, Direction) else str(setup_direction)
    ).lower()
    valid = valid_count > 0
    state_ids = tuple(item.structure_state_id for item in states)
    summary = {
        "alignments": alignments,
        "breaks": break_values,
        "local": local_alignment,
        "counts": (aligned, conflict, neutral, valid_count),
    }
    snapshot_id = context_uuid(
        identity.feature_formula_version,
        identity.feature_schema_hash,
        identity.context_config_hash,
        setup_id,
        as_of_cursor,
        state_ids,
        local_state.structure_state_id,
        canonical_sha256(summary),
    )
    return MtfConfluenceSnapshot(
        **record_provenance(
            identity,
            as_of_ts=as_of_ts,
            as_of_cursor=as_of_cursor,
            source_close_ts=max(
                (item.source_close_ts for item in (*states, local_state) if item.source_close_ts),
                default=None,
            ),
            source_confirmed_ts=max(
                (
                    item.source_confirmed_ts
                    for item in (*states, local_state)
                    if item.source_confirmed_ts
                ),
                default=None,
            ),
            valid=valid,
            warmup_complete=all(item.valid for item in states) and local_state.valid,
            source_available=True,
            missing_reason=None if valid else MissingReason.SOURCE_UNAVAILABLE,
        ),
        mtf_snapshot_id=snapshot_id,
        setup_id=setup_id,
        setup_direction=setup_value,
        active_mtf_timeframes=tuple(item.source_timeframe for item in states),
        state_ids=state_ids,
        local_structure_state_id=local_state.structure_state_id,
        states=states,
        local_state=local_state,
        aligned_tf_count=aligned,
        conflicting_tf_count=conflict,
        neutral_tf_count=neutral,
        valid_tf_count=valid_count,
        break_aligned_tf_count=sum(value == 1 for value in break_values),
        break_conflicting_tf_count=sum(value == -1 for value in break_values),
        highest_aligned_tf_seconds=max(aligned_seconds, default=None),
        highest_conflicting_tf_seconds=max(conflict_seconds, default=None),
        lowest_conflicting_tf_seconds=min(conflict_seconds, default=None),
        contiguous_alignment_span=_max_run(alignments, 1),
        contiguous_conflict_span=_max_run(alignments, -1),
        adjacent_tf_transition_count=adjacent,
        lower_support_higher_conflict=(
            all(value == 1 for value in lower) and all(value == -1 for value in higher)
            if groups_valid
            else None
        ),
        lower_conflict_higher_support=(
            all(value == -1 for value in lower) and all(value == 1 for value in higher)
            if groups_valid
            else None
        ),
        execution_pullback_inside_htf_trend=(
            all(value == 1 for value in higher) and local_alignment == -1
            if htf_valid and local_alignment is not None
            else None
        ),
        execution_expansion_against_htf_trend=(
            all(value == -1 for value in higher) and local_alignment == 1
            if htf_valid and local_alignment is not None
            else None
        ),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class StructureTransitionDelta(ContextRecord):
    structure_delta_id: UUID
    delta_kind: str
    from_snapshot_id: UUID
    to_snapshot_id: UUID
    changed_timeframe_count: int
    support_to_conflict_count: int
    conflict_to_support_count: int
    direction_flip_count: int
    newly_confirmed_break_count: int


def build_structure_delta(
    *,
    identity: ContextIdentity,
    delta_kind: str,
    source: MtfConfluenceSnapshot,
    destination: MtfConfluenceSnapshot,
) -> StructureTransitionDelta:
    left = (*source.states, source.local_state)
    right = (*destination.states, destination.local_state)
    if len(left) != len(right):
        raise ValueError("structure delta endpoints use different timeframe sets")
    changed = sum(a.comparison_tuple() != b.comparison_tuple() for a, b in zip(left, right, strict=True))
    support_to_conflict = sum(
        a.structure_alignment == 1 and b.structure_alignment == -1
        for a, b in zip(left, right, strict=True)
    )
    conflict_to_support = sum(
        a.structure_alignment == -1 and b.structure_alignment == 1
        for a, b in zip(left, right, strict=True)
    )
    flips = sum(
        a.structure_direction in (StructureDirection.BULLISH, StructureDirection.BEARISH)
        and b.structure_direction in (StructureDirection.BULLISH, StructureDirection.BEARISH)
        and a.structure_direction is not b.structure_direction
        for a, b in zip(left, right, strict=True)
    )
    new_breaks = sum(
        b.last_break_id is not None and b.last_break_id != a.last_break_id
        for a, b in zip(left, right, strict=True)
    )
    valid = source.valid and destination.valid
    return StructureTransitionDelta(
        **record_provenance(
            identity,
            as_of_ts=destination.as_of_ts,
            as_of_cursor=destination.as_of_cursor,
            source_close_ts=destination.source_close_ts,
            source_confirmed_ts=destination.source_confirmed_ts,
            valid=valid,
            warmup_complete=source.warmup_complete and destination.warmup_complete,
            source_available=source.source_available and destination.source_available,
            missing_reason=None if valid else MissingReason.SOURCE_UNAVAILABLE,
        ),
        structure_delta_id=context_uuid(
            identity.feature_formula_version,
            identity.feature_schema_hash,
            delta_kind,
            source.mtf_snapshot_id,
            destination.mtf_snapshot_id,
        ),
        delta_kind=delta_kind,
        from_snapshot_id=source.mtf_snapshot_id,
        to_snapshot_id=destination.mtf_snapshot_id,
        changed_timeframe_count=changed,
        support_to_conflict_count=support_to_conflict,
        conflict_to_support_count=conflict_to_support,
        direction_flip_count=flips,
        newly_confirmed_break_count=new_breaks,
    )
