"""Integer-tick candle primitives and bounded incremental displacement windows."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from strategy_core.candles.exchange_calendar import (
    CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
    ContextSourceCoverage,
    DEFAULT_CONTEXT_SOURCE_COVERAGE,
    ExchangeMinuteSchedule,
    MinuteSlotStatus,
    SourceCoverageStatus,
)
from strategy_core.structures.context import (
    ContextIdentity,
    ContextRecord,
    MissingReason,
    canonical_json,
    context_uuid,
    record_provenance,
)
from strategy_core.structures.fvg import Fvg, GapDirection
from strategy_core.types import Bar, BarKind, SessionScheme

__all__ = [
    "CandlePrimitives",
    "DisplacementAccumulator",
    "DisplacementAccumulatorSnapshot",
    "DisplacementWindowSummary",
    "candle_primitives",
    "overlap_fraction",
]


_CHAIN_DOMAIN = b"ifvg-context-chain-v2\0"


class _LengthPrefixedRecordChain:
    """Portable constant-space record chain used by formula v2 seeds.

    ``hashlib`` digests are portable bytes; unlike a live SHA-256 compression
    context they need no OpenSSL/platform state serialization.
    """

    __slots__ = ("_digest", "_record_count")

    def __init__(self, *, digest_hex: str | None = None, record_count: int = 0) -> None:
        if record_count < 0:
            raise ValueError("record-chain count must be non-negative")
        if digest_hex is None:
            digest = hashlib.sha256(_CHAIN_DOMAIN).digest()
        else:
            try:
                digest = bytes.fromhex(digest_hex)
            except ValueError as error:
                raise ValueError("invalid record-chain digest") from error
            if len(digest) != hashlib.sha256().digest_size:
                raise ValueError("invalid record-chain digest length")
        self._digest = digest
        self._record_count = record_count

    @property
    def record_count(self) -> int:
        return self._record_count

    def update(self, canonical_record_bytes: bytes) -> None:
        if not isinstance(canonical_record_bytes, bytes):
            raise TypeError("record-chain update requires bytes")
        if len(canonical_record_bytes) >= 1 << 64:
            raise ValueError("record is too large for the uint64 length prefix")
        self._digest = hashlib.sha256(
            self._digest
            + len(canonical_record_bytes).to_bytes(8, "big")
            + canonical_record_bytes
        ).digest()
        self._record_count += 1

    def hexdigest(self) -> str:
        return self._digest.hex()


@dataclass(frozen=True, slots=True)
class CandlePrimitives:
    range_ticks: int
    body_ticks: int
    upper_wick_ticks: int
    lower_wick_ticks: int
    close_location_value: float | None
    true_range_ticks: int
    missing_reason: MissingReason | None


def candle_primitives(bar: Bar, *, previous_close_ticks: int) -> CandlePrimitives:
    range_ticks = bar.high_ticks - bar.low_ticks
    body_ticks = abs(bar.close_ticks - bar.open_ticks)
    upper_wick = bar.high_ticks - max(bar.open_ticks, bar.close_ticks)
    lower_wick = min(bar.open_ticks, bar.close_ticks) - bar.low_ticks
    close_location = (
        (2 * bar.close_ticks - bar.high_ticks - bar.low_ticks) / range_ticks
        if range_ticks
        else None
    )
    true_range = max(
        range_ticks,
        abs(bar.high_ticks - previous_close_ticks),
        abs(bar.low_ticks - previous_close_ticks),
    )
    return CandlePrimitives(
        range_ticks=range_ticks,
        body_ticks=body_ticks,
        upper_wick_ticks=upper_wick,
        lower_wick_ticks=lower_wick,
        close_location_value=close_location,
        true_range_ticks=true_range,
        missing_reason=None if range_ticks else MissingReason.ZERO_RANGE,
    )


def overlap_fraction(left: Bar, right: Bar) -> tuple[float | None, MissingReason | None]:
    intersection = max(0, min(left.high_ticks, right.high_ticks) - max(left.low_ticks, right.low_ticks))
    union = max(left.high_ticks, right.high_ticks) - min(left.low_ticks, right.low_ticks)
    if union == 0:
        return None, MissingReason.ZERO_RANGE
    return intersection / union, None


@dataclass(frozen=True, slots=True, kw_only=True)
class DisplacementWindowSummary(ContextRecord):
    displacement_window_id: UUID
    setup_id: str
    window_kind: str
    start_evidence_id: str
    end_evidence_id: str
    b0_bar_id: str
    start_ts: datetime
    last_included_bar_id: str | None
    end_ts: datetime | None
    expected_orientation: str
    observed_bar_ids_hash: str
    calendar_policy_id: str
    calendar_schedule_hash: str
    source_gap_policy_id: str
    source_coverage_hash: str
    source_partition_dates: tuple[str, ...]
    unavailable_partition_dates: tuple[str, ...]
    metric_missing_reasons: Mapping[str, str]
    metrics: Mapping[str, int | float | None]


@dataclass(frozen=True, slots=True)
class _DisplacementStatistics:
    observed_bar_count: int
    eligible_observed_close_count: int
    extra_bar_count: int
    last_bar: Bar | None
    last_eligible_close_ts: datetime | None
    range_sum: int
    range_min: int | None
    range_max: int | None
    body_sum: int
    upper_wick_sum: int
    lower_wick_sum: int
    true_range_sum: int
    ratio_count: int
    body_fraction_sum: float
    body_fraction_min: float | None
    body_fraction_max: float | None
    upper_fraction_sum: float
    lower_fraction_sum: float
    close_location_sum: float
    overlap_sum: float
    overlap_count: int
    bullish: int
    bearish: int
    doji: int
    directional: int
    opposing: int
    directional_body_sum: int
    opposing_body_sum: int
    current_directional_run: int
    max_directional_run: int
    path_length: int
    oriented_peak: int
    max_favorable: int
    max_pullback: int
    last_fvg_id: str | None
    last_fvg_confirmed_ts: datetime | None
    bullish_fvg_count: int
    bearish_fvg_count: int
    bullish_fvg_width_sum_ticks: int
    bearish_fvg_width_sum_ticks: int


@dataclass(frozen=True, slots=True)
class DisplacementAccumulatorSnapshot:
    setup_id: str
    window_kind: str
    start_evidence_id: str
    b0: Bar
    expected_sign: int
    setup_sign: int
    statistics: _DisplacementStatistics
    bar_ids_chain_hash: str
    bar_ids_chain_record_count: int


class DisplacementAccumulator:
    """Incremental ``(B0,end]`` accumulator.

    All continuous aggregates update once per accepted 1m bar.  State is constant
    space regardless of stage duration: only sufficient statistics, the previous
    bar, and a resumable ordered-ID SHA-256 state enter the seed.
    """

    def __init__(
        self,
        *,
        identity: ContextIdentity,
        scheme: SessionScheme,
        schedule: ExchangeMinuteSchedule = CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
        source_coverage: ContextSourceCoverage = DEFAULT_CONTEXT_SOURCE_COVERAGE,
        setup_id: str,
        window_kind: str,
        start_evidence_id: str,
        b0: Bar,
        expected_sign: int,
        setup_sign: int,
    ) -> None:
        if b0.kind is not BarKind.TIME or b0.timeframe_ticks != 60 or not b0.is_complete:
            raise ValueError("displacement B0 must be a completed 1m TIME bar")
        if expected_sign not in (-1, 1) or setup_sign not in (-1, 1):
            raise ValueError("displacement orientation signs must be -1 or +1")
        self.identity = identity
        self.scheme = scheme
        self.schedule = schedule
        self.source_coverage = source_coverage
        self.setup_id = setup_id
        self.window_kind = window_kind
        self.start_evidence_id = start_evidence_id
        self.b0 = b0
        self.expected_sign = expected_sign
        self.setup_sign = setup_sign
        self._observed_bar_count = 0
        self._eligible_observed_close_count = 0
        self._extra_bar_count = 0
        self._last_bar: Bar | None = None
        self._last_eligible_close_ts: datetime | None = None
        self._bar_ids_hash = _LengthPrefixedRecordChain()
        self._range_sum = 0
        self._range_min: int | None = None
        self._range_max: int | None = None
        self._body_sum = 0
        self._upper_wick_sum = 0
        self._lower_wick_sum = 0
        self._true_range_sum = 0
        self._ratio_count = 0
        self._body_fraction_sum = 0.0
        self._body_fraction_min: float | None = None
        self._body_fraction_max: float | None = None
        self._upper_fraction_sum = 0.0
        self._lower_fraction_sum = 0.0
        self._close_location_sum = 0.0
        self._overlap_sum = 0.0
        self._overlap_count = 0
        self._bullish = 0
        self._bearish = 0
        self._doji = 0
        self._directional = 0
        self._opposing = 0
        self._directional_body_sum = 0
        self._opposing_body_sum = 0
        self._current_directional_run = 0
        self._max_directional_run = 0
        self._path_length = 0
        origin = self.expected_sign * b0.close_ticks
        self._oriented_peak = origin
        self._max_favorable = 0
        self._max_pullback = 0
        self._last_fvg_id: str | None = None
        self._last_fvg_confirmed_ts: datetime | None = None
        self._bullish_fvg_count = 0
        self._bearish_fvg_count = 0
        self._bullish_fvg_width_sum_ticks = 0
        self._bearish_fvg_width_sum_ticks = 0
        self._finalize_cache_key: tuple[datetime, str] | None = None
        self._finalize_cache_summary: DisplacementWindowSummary | None = None
        self._validate_observed_close(b0.availability_ts_utc, label="B0")

    @property
    def observed_bar_count(self) -> int:
        return self._observed_bar_count

    @staticmethod
    def _scheduled_close(close_ts: datetime) -> datetime:
        """Normalize legacy print-time bars to their containing minute close.

        Formula-v2 TIME bars carry an exact ``logical_close_ts_utc`` already.  The
        compatibility path still accepts older synthetic/legacy bars whose
        availability is the last print (often ``:59``).
        """

        instant = close_ts.astimezone(UTC)
        normalized = instant.replace(second=0, microsecond=0)
        if normalized != instant:
            normalized += timedelta(minutes=1)
        return normalized

    def _validate_observed_close(self, close_ts: datetime, *, label: str) -> datetime:
        scheduled_close = self._scheduled_close(close_ts)
        slot = self.schedule.slot(scheduled_close)
        if slot.status is not MinuteSlotStatus.ELIGIBLE:
            raise ValueError(
                f"displacement {label} occupies ineligible exchange minute: "
                f"{slot.status.value}"
            )
        coverage = self.source_coverage.status_for_close(scheduled_close)
        if coverage is not SourceCoverageStatus.AVAILABLE:
            raise ValueError(
                f"displacement {label} contradicts source coverage: {coverage.value}"
            )
        return scheduled_close

    def on_bar(self, bar: Bar) -> None:
        if bar.kind is not BarKind.TIME or bar.timeframe_ticks != 60 or not bar.is_complete:
            return
        if bar.availability_ts_utc <= self.b0.availability_ts_utc:
            return
        if self._last_bar is not None and (
            bar.availability_ts_utc,
            bar.bar_id,
        ) <= (
            self._last_bar.availability_ts_utc,
            self._last_bar.bar_id,
        ):
            raise ValueError("displacement bars must be strictly ordered")
        scheduled_close = self._validate_observed_close(
            bar.availability_ts_utc,
            label="bar",
        )
        if scheduled_close == self._last_eligible_close_ts:
            raise ValueError("displacement contains duplicate eligible minute close")
        previous_close = self._last_bar.close_ticks if self._last_bar is not None else self.b0.close_ticks
        primitive = candle_primitives(bar, previous_close_ticks=previous_close)
        self._range_sum += primitive.range_ticks
        self._range_min = primitive.range_ticks if self._range_min is None else min(self._range_min, primitive.range_ticks)
        self._range_max = primitive.range_ticks if self._range_max is None else max(self._range_max, primitive.range_ticks)
        self._body_sum += primitive.body_ticks
        self._upper_wick_sum += primitive.upper_wick_ticks
        self._lower_wick_sum += primitive.lower_wick_ticks
        self._true_range_sum += primitive.true_range_ticks
        if primitive.range_ticks:
            body_fraction = primitive.body_ticks / primitive.range_ticks
            upper_fraction = primitive.upper_wick_ticks / primitive.range_ticks
            lower_fraction = primitive.lower_wick_ticks / primitive.range_ticks
            self._ratio_count += 1
            self._body_fraction_sum += body_fraction
            self._body_fraction_min = body_fraction if self._body_fraction_min is None else min(self._body_fraction_min, body_fraction)
            self._body_fraction_max = body_fraction if self._body_fraction_max is None else max(self._body_fraction_max, body_fraction)
            self._upper_fraction_sum += upper_fraction
            self._lower_fraction_sum += lower_fraction
            self._close_location_sum += primitive.close_location_value or 0.0
        if self._last_bar is not None:
            overlap, _reason = overlap_fraction(self._last_bar, bar)
            if overlap is not None:
                self._overlap_sum += overlap
                self._overlap_count += 1

        candle_sign = (bar.close_ticks > bar.open_ticks) - (bar.close_ticks < bar.open_ticks)
        if candle_sign > 0:
            self._bullish += 1
        elif candle_sign < 0:
            self._bearish += 1
        else:
            self._doji += 1
        if candle_sign == self.expected_sign:
            self._directional += 1
            self._directional_body_sum += primitive.body_ticks
            self._current_directional_run += 1
            self._max_directional_run = max(self._max_directional_run, self._current_directional_run)
        else:
            self._current_directional_run = 0
            if candle_sign == -self.expected_sign:
                self._opposing += 1
                self._opposing_body_sum += primitive.body_ticks

        self._path_length += abs(bar.close_ticks - previous_close)
        oriented_close = self.expected_sign * bar.close_ticks
        self._oriented_peak = max(self._oriented_peak, oriented_close)
        origin = self.expected_sign * self.b0.close_ticks
        self._max_favorable = max(self._max_favorable, oriented_close - origin)
        self._max_pullback = max(self._max_pullback, self._oriented_peak - oriented_close)
        self._eligible_observed_close_count += 1
        self._last_eligible_close_ts = scheduled_close
        self._bar_ids_hash.update(canonical_json(bar.bar_id).encode("utf-8"))
        self._observed_bar_count += 1
        self._last_bar = bar
        self._finalize_cache_key = None
        self._finalize_cache_summary = None

    def on_fvg(self, fvg: Fvg) -> None:
        if (
            fvg.timeframe_seconds == 60
            and fvg.confirmed_ts_utc > self.b0.availability_ts_utc
            and fvg.fvg_id != self._last_fvg_id
        ):
            self._finalize_cache_key = None
            self._finalize_cache_summary = None
            self._last_fvg_id = fvg.fvg_id
            self._last_fvg_confirmed_ts = (
                fvg.confirmed_ts_utc
                if self._last_fvg_confirmed_ts is None
                else max(self._last_fvg_confirmed_ts, fvg.confirmed_ts_utc)
            )
            if fvg.direction is GapDirection.BULLISH:
                self._bullish_fvg_count += 1
                self._bullish_fvg_width_sum_ticks += fvg.size_ticks
            else:
                self._bearish_fvg_count += 1
                self._bearish_fvg_width_sum_ticks += fvg.size_ticks

    def _window_source_evidence(
        self,
        end_ts: datetime,
    ) -> tuple[int, int, int, tuple[str, ...], tuple[str, ...]]:
        expected = 0
        available = 0
        unavailable = 0
        partitions: set[str] = set()
        unavailable_partitions: set[str] = set()
        start_close = self._scheduled_close(self.b0.availability_ts_utc)
        end_close = self._scheduled_close(end_ts)
        if end_close > self.source_coverage.cutoff_ts_utc:
            cutoff_start = max(start_close, self.source_coverage.cutoff_ts_utc)
            if self.schedule.eligible_close_count(cutoff_start, end_close):
                raise ValueError(
                    "eligible displacement minute has contradictory source coverage: "
                    f"{SourceCoverageStatus.AFTER_CUTOFF.value}"
                )
        covered_end = min(end_close, self.source_coverage.cutoff_ts_utc)
        partition_counts = (
            self.schedule.eligible_counts_by_partition(
                start_close,
                covered_end,
                partition_timezone=self.source_coverage.partition_timezone,
            )
            if covered_end > start_close
            else ()
        )
        for partition, partition_count in partition_counts:
            expected += partition_count
            partitions.add(partition.isoformat())
            status = self.source_coverage.status_for_partition(partition)
            if status is SourceCoverageStatus.AVAILABLE:
                available += partition_count
            elif status is SourceCoverageStatus.UNAVAILABLE:
                unavailable += partition_count
                unavailable_partitions.add(partition.isoformat())
            else:
                raise ValueError(
                    "eligible displacement minute has contradictory source coverage: "
                    f"{status.value}"
                )
        return (
            expected,
            available,
            unavailable,
            tuple(sorted(partitions)),
            tuple(sorted(unavailable_partitions)),
        )

    def finalize(
        self,
        *,
        end_evidence_id: str,
        end_bar: Bar,
    ) -> DisplacementWindowSummary:
        if end_bar.availability_ts_utc < self.b0.availability_ts_utc:
            raise ValueError("displacement end precedes B0")
        # The observer finalizes immediately on the transition; an already-advanced
        # accumulator containing later evidence is a causality violation, never truncated.
        if (
            self._last_bar is not None
            and self._last_bar.availability_ts_utc > end_bar.availability_ts_utc
        ):
            raise ValueError("displacement accumulator consumed a post-transition bar")
        if (
            self._last_fvg_confirmed_ts is not None
            and self._last_fvg_confirmed_ts > end_bar.availability_ts_utc
        ):
            raise ValueError("displacement accumulator consumed a post-transition FVG")
        cache_key = (end_bar.availability_ts_utc, end_bar.bar_id)
        if (
            cache_key == self._finalize_cache_key
            and self._finalize_cache_summary is not None
        ):
            return replace(
                self._finalize_cache_summary,
                displacement_window_id=context_uuid(
                    self.identity.feature_formula_version,
                    self.identity.feature_schema_hash,
                    self.setup_id,
                    self.window_kind,
                    self.start_evidence_id,
                    end_evidence_id,
                ),
                end_evidence_id=end_evidence_id,
            )
        observed = self._observed_bar_count
        (
            expected,
            expected_available,
            expected_unavailable,
            source_partitions,
            unavailable_partitions,
        ) = self._window_source_evidence(end_bar.availability_ts_utc)
        if self._eligible_observed_close_count > expected_available:
            raise ValueError("observed displacement bars exceed audited available minute slots")
        missing = expected_available - self._eligible_observed_close_count
        if missing > 0:
            primary_reason = MissingReason.SOURCE_BAR_MISSING
        elif expected_unavailable > 0:
            primary_reason = MissingReason.SOURCE_PARTITION_UNAVAILABLE
        elif observed == 0:
            primary_reason = MissingReason.INSUFFICIENT_OBSERVATIONS
        else:
            primary_reason = None
        valid = primary_reason is None
        count = observed
        mean_tr = self._true_range_sum / count if count else None
        raw_net = self._last_bar.close_ticks - self.b0.close_ticks if self._last_bar else None
        expected_net = raw_net * self.expected_sign if raw_net is not None else None
        setup_net = raw_net * self.setup_sign if raw_net is not None else None
        if raw_net is None:
            efficiency = None
        elif self._path_length == 0:
            efficiency = 0.0
        else:
            efficiency = abs(raw_net) / self._path_length
        signed = (raw_net > 0) - (raw_net < 0) if raw_net is not None else 0
        directional_fvg_count = (
            self._bullish_fvg_count if self.expected_sign == 1 else self._bearish_fvg_count
        )
        opposing_fvg_count = (
            self._bearish_fvg_count if self.expected_sign == 1 else self._bullish_fvg_count
        )
        directional_fvg_width = (
            self._bullish_fvg_width_sum_ticks
            if self.expected_sign == 1
            else self._bearish_fvg_width_sum_ticks
        )
        opposing_fvg_width = (
            self._bearish_fvg_width_sum_ticks
            if self.expected_sign == 1
            else self._bullish_fvg_width_sum_ticks
        )
        wall_minutes = (
            end_bar.availability_ts_utc - self.b0.availability_ts_utc
        ).total_seconds() / 60
        metric_reasons: dict[str, str] = {}

        def window_value(value: int | float | None, name: str) -> int | float | None:
            if not valid:
                return None
            return value

        ratio_reason = (
            primary_reason
            if not valid
            else (MissingReason.ZERO_RANGE if self._ratio_count == 0 else None)
        )
        overlap_reason = (
            primary_reason
            if not valid
            else (
                MissingReason.INSUFFICIENT_PAIRS
                if observed < 2
                else (MissingReason.ZERO_RANGE if self._overlap_count == 0 else None)
            )
        )
        tr_reason = (
            primary_reason
            if not valid
            else (MissingReason.ZERO_MEAN_TRUE_RANGE if not mean_tr else None)
        )

        def nullable(value: float | None, name: str, reason: MissingReason | None) -> float | None:
            if reason is not None:
                # Window-wide invalidity is already canonical on the record.  Do
                # not repeat the same reason for every nullable metric in the live
                # transition snapshot; metric-specific reasons remain explicit on
                # otherwise-valid windows.
                if valid or reason is not primary_reason:
                    metric_reasons[name] = reason.value
                return None
            return value

        raw_normalized = raw_net / mean_tr if raw_net is not None and mean_tr else None
        expected_normalized = expected_net / mean_tr if expected_net is not None and mean_tr else None
        setup_normalized = setup_net / mean_tr if setup_net is not None and mean_tr else None
        metrics: dict[str, int | float | None] = {
            "observed_bar_count": observed,
            "expected_eligible_bar_count": expected,
            "missing_bar_count": missing,
            "wall_elapsed_minutes": wall_minutes,
            "eligible_elapsed_minutes": expected,
            "range_ticks_mean": window_value(self._range_sum / count if count else None, "range_ticks_mean"),
            "range_ticks_min": window_value(self._range_min, "range_ticks_min"),
            "range_ticks_max": window_value(self._range_max, "range_ticks_max"),
            "body_ticks_sum": window_value(self._body_sum, "body_ticks_sum"),
            "upper_wick_ticks_mean": window_value(self._upper_wick_sum / count if count else None, "upper_wick_ticks_mean"),
            "lower_wick_ticks_mean": window_value(self._lower_wick_sum / count if count else None, "lower_wick_ticks_mean"),
            "true_range_ticks_mean": window_value(mean_tr, "true_range_ticks_mean"),
            "body_fraction_mean": nullable(self._body_fraction_sum / self._ratio_count if self._ratio_count else None, "body_fraction_mean", ratio_reason),
            "body_fraction_min": nullable(self._body_fraction_min, "body_fraction_min", ratio_reason),
            "body_fraction_max": nullable(self._body_fraction_max, "body_fraction_max", ratio_reason),
            "upper_wick_fraction_mean": nullable(self._upper_fraction_sum / self._ratio_count if self._ratio_count else None, "upper_wick_fraction_mean", ratio_reason),
            "lower_wick_fraction_mean": nullable(self._lower_fraction_sum / self._ratio_count if self._ratio_count else None, "lower_wick_fraction_mean", ratio_reason),
            "directional_wick_fraction_mean": nullable((self._lower_fraction_sum if self.expected_sign == 1 else self._upper_fraction_sum) / self._ratio_count if self._ratio_count else None, "directional_wick_fraction_mean", ratio_reason),
            "opposing_wick_fraction_mean": nullable((self._upper_fraction_sum if self.expected_sign == 1 else self._lower_fraction_sum) / self._ratio_count if self._ratio_count else None, "opposing_wick_fraction_mean", ratio_reason),
            "raw_close_location_mean": nullable(self._close_location_sum / self._ratio_count if self._ratio_count else None, "raw_close_location_mean", ratio_reason),
            "expected_close_location_mean": nullable(self.expected_sign * self._close_location_sum / self._ratio_count if self._ratio_count else None, "expected_close_location_mean", ratio_reason),
            "setup_close_location_mean": nullable(self.setup_sign * self._close_location_sum / self._ratio_count if self._ratio_count else None, "setup_close_location_mean", ratio_reason),
            "overlap_fraction_mean": nullable(self._overlap_sum / self._overlap_count if self._overlap_count else None, "overlap_fraction_mean", overlap_reason),
            "bullish_bar_count": window_value(self._bullish, "bullish_bar_count"),
            "bearish_bar_count": window_value(self._bearish, "bearish_bar_count"),
            "doji_bar_count": window_value(self._doji, "doji_bar_count"),
            "directional_bar_count": window_value(self._directional, "directional_bar_count"),
            "opposing_bar_count": window_value(self._opposing, "opposing_bar_count"),
            "directional_bar_fraction": window_value(self._directional / count if count else None, "directional_bar_fraction"),
            "opposing_bar_fraction": window_value(self._opposing / count if count else None, "opposing_bar_fraction"),
            "max_consecutive_directional_bars": window_value(self._max_directional_run, "max_consecutive_directional_bars"),
            "directional_body_ticks_sum": window_value(self._directional_body_sum, "directional_body_ticks_sum"),
            "opposing_body_ticks_sum": window_value(self._opposing_body_sum, "opposing_body_ticks_sum"),
            "raw_close_progress_ticks_mean": window_value(raw_net / count if raw_net is not None and count else None, "raw_close_progress_ticks_mean"),
            "expected_close_progress_ticks_mean": window_value(expected_net / count if expected_net is not None and count else None, "expected_close_progress_ticks_mean"),
            "setup_close_progress_ticks_mean": window_value(setup_net / count if setup_net is not None and count else None, "setup_close_progress_ticks_mean"),
            "raw_net_move_ticks": window_value(raw_net, "raw_net_move_ticks"),
            "expected_net_move_ticks": window_value(expected_net, "expected_net_move_ticks"),
            "setup_net_move_ticks": window_value(setup_net, "setup_net_move_ticks"),
            "raw_net_move_normalized": nullable(raw_normalized, "raw_net_move_normalized", tr_reason),
            "expected_net_move_normalized": nullable(expected_normalized, "expected_net_move_normalized", tr_reason),
            "setup_net_move_normalized": nullable(setup_normalized, "setup_net_move_normalized", tr_reason),
            "raw_velocity_normalized": nullable(raw_normalized / expected if raw_normalized is not None and expected else None, "raw_velocity_normalized", tr_reason or (MissingReason.INSUFFICIENT_OBSERVATIONS if expected <= 0 else None)),
            "expected_velocity_normalized": nullable(expected_normalized / expected if expected_normalized is not None and expected else None, "expected_velocity_normalized", tr_reason or (MissingReason.INSUFFICIENT_OBSERVATIONS if expected <= 0 else None)),
            "setup_velocity_normalized": nullable(setup_normalized / expected if setup_normalized is not None and expected else None, "setup_velocity_normalized", tr_reason or (MissingReason.INSUFFICIENT_OBSERVATIONS if expected <= 0 else None)),
            "path_efficiency_abs": window_value(efficiency, "path_efficiency_abs"),
            "raw_path_efficiency_signed": window_value(efficiency * signed if efficiency is not None else None, "raw_path_efficiency_signed"),
            "expected_path_efficiency_signed": window_value(efficiency * signed * self.expected_sign if efficiency is not None else None, "expected_path_efficiency_signed"),
            "setup_path_efficiency_signed": window_value(efficiency * signed * self.setup_sign if efficiency is not None else None, "setup_path_efficiency_signed"),
            "max_pullback_ticks": window_value(self._max_pullback, "max_pullback_ticks"),
            "max_pullback_fraction": nullable(self._max_pullback / self._max_favorable if self._max_favorable > 0 else None, "max_pullback_fraction", primary_reason if not valid else (MissingReason.NOT_APPLICABLE if self._max_favorable <= 0 else None)),
            "bullish_fvg_count": window_value(self._bullish_fvg_count, "bullish_fvg_count"),
            "bearish_fvg_count": window_value(self._bearish_fvg_count, "bearish_fvg_count"),
            "directional_fvg_count": window_value(directional_fvg_count, "directional_fvg_count"),
            "opposing_fvg_count": window_value(opposing_fvg_count, "opposing_fvg_count"),
            "bullish_fvg_width_sum_ticks": window_value(self._bullish_fvg_width_sum_ticks, "bullish_fvg_width_sum_ticks"),
            "bearish_fvg_width_sum_ticks": window_value(self._bearish_fvg_width_sum_ticks, "bearish_fvg_width_sum_ticks"),
            "directional_fvg_width_sum_ticks": window_value(directional_fvg_width, "directional_fvg_width_sum_ticks"),
            "opposing_fvg_width_sum_ticks": window_value(opposing_fvg_width, "opposing_fvg_width_sum_ticks"),
            "directional_fvg_width_sum_normalized": nullable(directional_fvg_width / mean_tr if mean_tr else None, "directional_fvg_width_sum_normalized", tr_reason),
            "directional_gap_density": window_value(directional_fvg_count / count if count else None, "directional_gap_density"),
        }
        ids_hash = self._bar_ids_hash.hexdigest()
        summary = DisplacementWindowSummary(
            **record_provenance(
                self.identity,
                as_of_ts=end_bar.availability_ts_utc,
                as_of_cursor=(
                    f"{end_bar.availability_ts_utc.isoformat()}|60|"
                    f"{end_bar.trading_day.isoformat()}|{end_bar.bar_id}"
                ),
                source_close_ts=end_bar.availability_ts_utc if observed else None,
                source_confirmed_ts=None,
                valid=valid,
                warmup_complete=observed > 0,
                source_available=expected_unavailable == 0,
                missing_reason=primary_reason,
            ),
            displacement_window_id=context_uuid(
                self.identity.feature_formula_version,
                self.identity.feature_schema_hash,
                self.setup_id,
                self.window_kind,
                self.start_evidence_id,
                end_evidence_id,
            ),
            setup_id=self.setup_id,
            window_kind=self.window_kind,
            start_evidence_id=self.start_evidence_id,
            end_evidence_id=end_evidence_id,
            b0_bar_id=self.b0.bar_id,
            start_ts=self.b0.availability_ts_utc,
            last_included_bar_id=self._last_bar.bar_id if self._last_bar else None,
            end_ts=end_bar.availability_ts_utc,
            expected_orientation="bullish" if self.expected_sign == 1 else "bearish",
            observed_bar_ids_hash=ids_hash,
            calendar_policy_id=self.schedule.policy_id,
            calendar_schedule_hash=self.schedule.content_hash,
            source_gap_policy_id=self.source_coverage.policy_id,
            source_coverage_hash=self.source_coverage.content_hash,
            source_partition_dates=source_partitions,
            unavailable_partition_dates=unavailable_partitions,
            metric_missing_reasons=MappingProxyType(dict(sorted(metric_reasons.items()))),
            metrics=MappingProxyType(metrics),
        )
        self._finalize_cache_key = cache_key
        self._finalize_cache_summary = summary
        return summary

    def snapshot(self) -> DisplacementAccumulatorSnapshot:
        return DisplacementAccumulatorSnapshot(
            setup_id=self.setup_id,
            window_kind=self.window_kind,
            start_evidence_id=self.start_evidence_id,
            b0=self.b0,
            expected_sign=self.expected_sign,
            setup_sign=self.setup_sign,
            statistics=_DisplacementStatistics(
                observed_bar_count=self._observed_bar_count,
                eligible_observed_close_count=self._eligible_observed_close_count,
                extra_bar_count=self._extra_bar_count,
                last_bar=self._last_bar,
                last_eligible_close_ts=self._last_eligible_close_ts,
                range_sum=self._range_sum,
                range_min=self._range_min,
                range_max=self._range_max,
                body_sum=self._body_sum,
                upper_wick_sum=self._upper_wick_sum,
                lower_wick_sum=self._lower_wick_sum,
                true_range_sum=self._true_range_sum,
                ratio_count=self._ratio_count,
                body_fraction_sum=self._body_fraction_sum,
                body_fraction_min=self._body_fraction_min,
                body_fraction_max=self._body_fraction_max,
                upper_fraction_sum=self._upper_fraction_sum,
                lower_fraction_sum=self._lower_fraction_sum,
                close_location_sum=self._close_location_sum,
                overlap_sum=self._overlap_sum,
                overlap_count=self._overlap_count,
                bullish=self._bullish,
                bearish=self._bearish,
                doji=self._doji,
                directional=self._directional,
                opposing=self._opposing,
                directional_body_sum=self._directional_body_sum,
                opposing_body_sum=self._opposing_body_sum,
                current_directional_run=self._current_directional_run,
                max_directional_run=self._max_directional_run,
                path_length=self._path_length,
                oriented_peak=self._oriented_peak,
                max_favorable=self._max_favorable,
                max_pullback=self._max_pullback,
                last_fvg_id=self._last_fvg_id,
                last_fvg_confirmed_ts=self._last_fvg_confirmed_ts,
                bullish_fvg_count=self._bullish_fvg_count,
                bearish_fvg_count=self._bearish_fvg_count,
                bullish_fvg_width_sum_ticks=self._bullish_fvg_width_sum_ticks,
                bearish_fvg_width_sum_ticks=self._bearish_fvg_width_sum_ticks,
            ),
            bar_ids_chain_hash=self._bar_ids_hash.hexdigest(),
            bar_ids_chain_record_count=self._bar_ids_hash.record_count,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: DisplacementAccumulatorSnapshot,
        *,
        identity: ContextIdentity,
        scheme: SessionScheme,
        schedule: ExchangeMinuteSchedule = CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE,
        source_coverage: ContextSourceCoverage = DEFAULT_CONTEXT_SOURCE_COVERAGE,
    ) -> DisplacementAccumulator:
        accumulator = cls(
            identity=identity,
            scheme=scheme,
            schedule=schedule,
            source_coverage=source_coverage,
            setup_id=snapshot.setup_id,
            window_kind=snapshot.window_kind,
            start_evidence_id=snapshot.start_evidence_id,
            b0=snapshot.b0,
            expected_sign=snapshot.expected_sign,
            setup_sign=snapshot.setup_sign,
        )
        statistics = snapshot.statistics
        accumulator._observed_bar_count = statistics.observed_bar_count
        accumulator._eligible_observed_close_count = statistics.eligible_observed_close_count
        accumulator._extra_bar_count = statistics.extra_bar_count
        accumulator._last_bar = statistics.last_bar
        accumulator._last_eligible_close_ts = statistics.last_eligible_close_ts
        accumulator._range_sum = statistics.range_sum
        accumulator._range_min = statistics.range_min
        accumulator._range_max = statistics.range_max
        accumulator._body_sum = statistics.body_sum
        accumulator._upper_wick_sum = statistics.upper_wick_sum
        accumulator._lower_wick_sum = statistics.lower_wick_sum
        accumulator._true_range_sum = statistics.true_range_sum
        accumulator._ratio_count = statistics.ratio_count
        accumulator._body_fraction_sum = statistics.body_fraction_sum
        accumulator._body_fraction_min = statistics.body_fraction_min
        accumulator._body_fraction_max = statistics.body_fraction_max
        accumulator._upper_fraction_sum = statistics.upper_fraction_sum
        accumulator._lower_fraction_sum = statistics.lower_fraction_sum
        accumulator._close_location_sum = statistics.close_location_sum
        accumulator._overlap_sum = statistics.overlap_sum
        accumulator._overlap_count = statistics.overlap_count
        accumulator._bullish = statistics.bullish
        accumulator._bearish = statistics.bearish
        accumulator._doji = statistics.doji
        accumulator._directional = statistics.directional
        accumulator._opposing = statistics.opposing
        accumulator._directional_body_sum = statistics.directional_body_sum
        accumulator._opposing_body_sum = statistics.opposing_body_sum
        accumulator._current_directional_run = statistics.current_directional_run
        accumulator._max_directional_run = statistics.max_directional_run
        accumulator._path_length = statistics.path_length
        accumulator._oriented_peak = statistics.oriented_peak
        accumulator._max_favorable = statistics.max_favorable
        accumulator._max_pullback = statistics.max_pullback
        accumulator._last_fvg_id = statistics.last_fvg_id
        accumulator._last_fvg_confirmed_ts = statistics.last_fvg_confirmed_ts
        accumulator._bullish_fvg_count = statistics.bullish_fvg_count
        accumulator._bearish_fvg_count = statistics.bearish_fvg_count
        accumulator._bullish_fvg_width_sum_ticks = statistics.bullish_fvg_width_sum_ticks
        accumulator._bearish_fvg_width_sum_ticks = statistics.bearish_fvg_width_sum_ticks
        accumulator._bar_ids_hash = _LengthPrefixedRecordChain(
            digest_hex=snapshot.bar_ids_chain_hash,
            record_count=snapshot.bar_ids_chain_record_count,
        )
        if accumulator._bar_ids_hash.record_count != statistics.observed_bar_count:
            raise ValueError("displacement record-chain count does not match statistics")
        return accumulator
