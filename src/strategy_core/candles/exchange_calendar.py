"""Deterministic exchange-minute schedule and audited source coverage.

The context formula must distinguish a scheduled closed minute from an eligible
minute whose source row is absent.  Missing rows cannot make that distinction, so
this module carries two independent pieces of evidence:

* :class:`ExchangeMinuteSchedule` says whether a global one-minute slot is expected
  to trade; and
* :class:`ContextSourceCoverage` says whether the permitted source partition for an
  expected slot was audited and available.

The default schedule is a committed snapshot.  It deliberately has finite coverage
and a content hash; runtime behavior never consults a mutable calendar package.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from functools import lru_cache
from types import MappingProxyType
from typing import Iterator, Mapping
from zoneinfo import ZoneInfo

__all__ = [
    "CALENDAR_POLICY_ID",
    "SOURCE_GAP_POLICY_ID",
    "CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE",
    "DEFAULT_CONTEXT_SOURCE_COVERAGE",
    "ContextSourceCoverage",
    "ExchangeMinuteSchedule",
    "MinuteSlot",
    "MinuteSlotStatus",
    "ScheduleClosure",
    "SourceCoverageStatus",
    "SourcePartitionCoverage",
]

CALENDAR_POLICY_ID = "cme_equity_index_futures_eth_v1"
SOURCE_GAP_POLICY_ID = "exchange_calendar_invalidate_no_impute_v2"

_MINUTE = timedelta(minutes=1)


class MinuteSlotStatus(StrEnum):
    """Why a source minute is eligible or scheduled closed."""

    ELIGIBLE = "eligible"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"
    WEEKEND_CLOSURE = "weekend_closure"
    HOLIDAY_CLOSURE = "holiday_closure"
    SPECIAL_CLOSURE = "special_closure"
    OUTSIDE_SCHEDULE_COVERAGE = "outside_schedule_coverage"


class SourceCoverageStatus(StrEnum):
    """Audited availability of the source partition containing a minute."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_PERMITTED = "not_permitted"
    AFTER_CUTOFF = "after_cutoff"


@dataclass(frozen=True, slots=True)
class MinuteSlot:
    close_ts_utc: datetime
    status: MinuteSlotStatus
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ScheduleClosure:
    """One immutable local-wall-clock closure interval from the snapshot."""

    start_local: datetime
    end_local: datetime
    status: MinuteSlotStatus
    reason: str

    def __post_init__(self) -> None:
        if self.start_local.tzinfo is not None or self.end_local.tzinfo is not None:
            raise ValueError("schedule closure bounds must be naive local datetimes")
        if self.end_local <= self.start_local:
            raise ValueError("schedule closure end must follow its start")
        if self.status not in {
            MinuteSlotStatus.HOLIDAY_CLOSURE,
            MinuteSlotStatus.SPECIAL_CLOSURE,
        }:
            raise ValueError("schedule closure must be holiday or special")


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ExchangeMinuteSchedule:
    """Finite, content-addressed minute schedule for CME equity-index ETH.

    Status is assigned to the half-open source bucket ``[close-1m, close)``.
    Eligible closes are always on the global UTC minute grid.
    """

    policy_id: str
    timezone: str
    coverage_start_utc: datetime
    coverage_end_utc: datetime
    normalized_sessions: tuple[tuple[str, str, str, tuple[int, ...]], ...]
    maintenance_windows: tuple[tuple[str, str], ...]
    holiday_closures: tuple[ScheduleClosure, ...]
    special_closures: tuple[ScheduleClosure, ...] = ()
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.policy_id != CALENDAR_POLICY_ID:
            raise ValueError(f"unsupported exchange calendar policy: {self.policy_id!r}")
        for bound in (self.coverage_start_utc, self.coverage_end_utc):
            if bound.tzinfo is None:
                raise ValueError("schedule coverage bounds must be timezone-aware")
        start = self.coverage_start_utc.astimezone(UTC)
        end = self.coverage_end_utc.astimezone(UTC)
        if end <= start:
            raise ValueError("schedule coverage end must follow start")
        if start.second or start.microsecond or end.second or end.microsecond:
            raise ValueError("schedule coverage bounds must use the minute grid")
        ZoneInfo(self.timezone)
        closures = (*self.holiday_closures, *self.special_closures)
        ordered = tuple(
            sorted(closures, key=lambda item: (item.start_local, item.end_local, item.reason))
        )
        for previous, current in zip(ordered, ordered[1:]):
            if current.start_local < previous.end_local:
                raise ValueError("committed exchange schedule closures overlap")
        payload = {
            "policy_id": self.policy_id,
            "timezone": self.timezone,
            "coverage_start_utc": start.isoformat(),
            "coverage_end_utc": end.isoformat(),
            "normalized_sessions": self.normalized_sessions,
            "maintenance_windows": self.maintenance_windows,
            "holiday_closures": [
                (
                    item.start_local.isoformat(),
                    item.end_local.isoformat(),
                    item.status.value,
                    item.reason,
                )
                for item in self.holiday_closures
            ],
            "special_closures": [
                (
                    item.start_local.isoformat(),
                    item.end_local.isoformat(),
                    item.status.value,
                    item.reason,
                )
                for item in self.special_closures
            ],
        }
        object.__setattr__(self, "coverage_start_utc", start)
        object.__setattr__(self, "coverage_end_utc", end)
        object.__setattr__(self, "content_hash", _canonical_hash(payload))

    @staticmethod
    def _time_in_window(value: time, start: time, end: time) -> bool:
        return start <= value < end if start <= end else value >= start or value < end

    def _closure_for(self, bucket_open_local: datetime) -> ScheduleClosure | None:
        naive = bucket_open_local.replace(tzinfo=None)
        for closure in (*self.holiday_closures, *self.special_closures):
            if closure.start_local <= naive < closure.end_local:
                return closure
        return None

    def slot(self, close_ts_utc: datetime) -> MinuteSlot:
        """Return typed schedule evidence for one global minute close."""

        if close_ts_utc.tzinfo is None:
            raise ValueError("minute close must be timezone-aware")
        close = close_ts_utc.astimezone(UTC)
        if close.second or close.microsecond:
            raise ValueError("minute close must be on the global UTC minute grid")
        if close <= self.coverage_start_utc or close > self.coverage_end_utc:
            return MinuteSlot(close, MinuteSlotStatus.OUTSIDE_SCHEDULE_COVERAGE)

        local_open = (close - _MINUTE).astimezone(ZoneInfo(self.timezone))
        closure = self._closure_for(local_open)
        if closure is not None:
            return MinuteSlot(close, closure.status, closure.reason)

        weekday = local_open.weekday()  # Monday=0, Sunday=6
        wall_time = local_open.time().replace(tzinfo=None)
        # CME equity-index futures: Sunday 18:00 ET through Friday 17:00 ET.
        if weekday == 5 or (weekday == 6 and wall_time < time(18)):
            return MinuteSlot(close, MinuteSlotStatus.WEEKEND_CLOSURE, "weekly_close")
        if weekday == 4 and wall_time >= time(17):
            return MinuteSlot(close, MinuteSlotStatus.WEEKEND_CLOSURE, "weekly_close")

        for start_text, end_text in self.maintenance_windows:
            start = time.fromisoformat(start_text)
            end = time.fromisoformat(end_text)
            if self._time_in_window(wall_time, start, end):
                return MinuteSlot(
                    close,
                    MinuteSlotStatus.SCHEDULED_MAINTENANCE,
                    "daily_maintenance",
                )
        return MinuteSlot(close, MinuteSlotStatus.ELIGIBLE)

    def iter_slots(
        self,
        start_exclusive: datetime,
        end_inclusive: datetime,
    ) -> Iterator[MinuteSlot]:
        """Yield global minute slots in ``(start, end]``."""

        if start_exclusive.tzinfo is None or end_inclusive.tzinfo is None:
            raise ValueError("minute interval bounds must be timezone-aware")
        start = start_exclusive.astimezone(UTC)
        end = end_inclusive.astimezone(UTC)
        if end < start:
            raise ValueError("minute interval ends before it starts")
        close = start.replace(second=0, microsecond=0)
        if close <= start:
            close += _MINUTE
        while close <= end:
            yield self.slot(close)
            close += _MINUTE

    def eligible_closes(
        self,
        start_exclusive: datetime,
        end_inclusive: datetime,
    ) -> tuple[datetime, ...]:
        return tuple(
            slot.close_ts_utc
            for slot in self.iter_slots(start_exclusive, end_inclusive)
            if slot.status is MinuteSlotStatus.ELIGIBLE
        )

    def eligible_close_count(
        self,
        start_exclusive: datetime,
        end_inclusive: datetime,
    ) -> int:
        return sum(
            slot.status is MinuteSlotStatus.ELIGIBLE
            for slot in self.iter_slots(start_exclusive, end_inclusive)
        )

    def eligible_counts_by_partition(
        self,
        start_exclusive: datetime,
        end_inclusive: datetime,
        *,
        partition_timezone: str = "UTC",
    ) -> tuple[tuple[date, int], ...]:
        """Count eligible closes by source date without rescanning old minutes.

        The source date owns closes in ``(local midnight, next midnight]``.
        Cached per-date prefix tables preserve exact DST and closure behavior while
        making repeated long-window finalization proportional to partition count.
        """

        if start_exclusive.tzinfo is None or end_inclusive.tzinfo is None:
            raise ValueError("minute interval bounds must be timezone-aware")
        start = start_exclusive.astimezone(UTC)
        end = end_inclusive.astimezone(UTC)
        if end < start:
            raise ValueError("minute interval ends before it starts")
        if start.second or start.microsecond or end.second or end.microsecond:
            raise ValueError("minute interval bounds must use the minute grid")
        if end == start:
            return ()
        timezone = ZoneInfo(partition_timezone)
        first_close = start + _MINUTE
        first_date = (first_close - timedelta(microseconds=1)).astimezone(timezone).date()
        last_date = (end - timedelta(microseconds=1)).astimezone(timezone).date()
        output: list[tuple[date, int]] = []
        current = first_date
        while current <= last_date:
            boundary_start, prefix, outside_prefix = _partition_minute_prefix(
                self,
                current,
                partition_timezone,
            )
            boundary_end = boundary_start + timedelta(minutes=len(prefix) - 1)
            left = max(start, boundary_start)
            right = min(end, boundary_end)
            if right > left:
                left_index = int((left - boundary_start).total_seconds() // 60)
                right_index = int((right - boundary_start).total_seconds() // 60)
                if outside_prefix[right_index] != outside_prefix[left_index]:
                    raise ValueError("minute interval exceeds exchange schedule coverage")
                eligible = prefix[right_index] - prefix[left_index]
                if eligible:
                    output.append((current, eligible))
            current += timedelta(days=1)
        return tuple(output)


@dataclass(frozen=True, slots=True)
class SourcePartitionCoverage:
    partition_date: date
    status: SourceCoverageStatus

    def __post_init__(self) -> None:
        if self.status not in {
            SourceCoverageStatus.AVAILABLE,
            SourceCoverageStatus.UNAVAILABLE,
        }:
            raise ValueError("partition coverage must be available or unavailable")


@dataclass(frozen=True, slots=True)
class ContextSourceCoverage:
    """Audited availability for explicitly permitted date partitions."""

    partitions: tuple[SourcePartitionCoverage, ...]
    cutoff_ts_utc: datetime
    partition_timezone: str = "UTC"
    policy_id: str = SOURCE_GAP_POLICY_ID
    content_hash: str = field(init=False)
    _by_date: Mapping[date, SourceCoverageStatus] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.policy_id != SOURCE_GAP_POLICY_ID:
            raise ValueError(f"unsupported source-gap policy: {self.policy_id!r}")
        if self.cutoff_ts_utc.tzinfo is None:
            raise ValueError("source coverage cutoff must be timezone-aware")
        ZoneInfo(self.partition_timezone)
        ordered = tuple(sorted(self.partitions, key=lambda item: item.partition_date))
        dates = [item.partition_date for item in ordered]
        if len(dates) != len(set(dates)):
            raise ValueError("source coverage declares a partition more than once")
        by_date = {item.partition_date: item.status for item in ordered}
        payload = {
            "policy_id": self.policy_id,
            "partition_timezone": self.partition_timezone,
            "cutoff_ts_utc": self.cutoff_ts_utc.astimezone(UTC).isoformat(),
            "partitions": [(item.partition_date.isoformat(), item.status.value) for item in ordered],
        }
        object.__setattr__(self, "partitions", ordered)
        object.__setattr__(self, "cutoff_ts_utc", self.cutoff_ts_utc.astimezone(UTC))
        object.__setattr__(self, "_by_date", MappingProxyType(by_date))
        object.__setattr__(self, "content_hash", _canonical_hash(payload))

    @classmethod
    def all_available(
        cls,
        *,
        start_date: date,
        end_date: date,
        cutoff_ts_utc: datetime,
        partition_timezone: str = "UTC",
    ) -> ContextSourceCoverage:
        if end_date < start_date:
            raise ValueError("source coverage end date precedes start date")
        count = (end_date - start_date).days + 1
        return cls(
            partitions=tuple(
                SourcePartitionCoverage(
                    partition_date=start_date + timedelta(days=offset),
                    status=SourceCoverageStatus.AVAILABLE,
                )
                for offset in range(count)
            ),
            cutoff_ts_utc=cutoff_ts_utc,
            partition_timezone=partition_timezone,
        )

    def partition_date_for_close(self, close_ts_utc: datetime) -> date:
        if close_ts_utc.tzinfo is None:
            raise ValueError("source close must be timezone-aware")
        # The close at midnight belongs to the source minute immediately before it.
        instant = close_ts_utc.astimezone(UTC) - timedelta(microseconds=1)
        return instant.astimezone(ZoneInfo(self.partition_timezone)).date()

    def status_for_close(self, close_ts_utc: datetime) -> SourceCoverageStatus:
        close = close_ts_utc.astimezone(UTC)
        if close > self.cutoff_ts_utc:
            return SourceCoverageStatus.AFTER_CUTOFF
        return self._by_date.get(
            self.partition_date_for_close(close),
            SourceCoverageStatus.NOT_PERMITTED,
        )

    def status_for_partition(self, partition_date: date) -> SourceCoverageStatus:
        return self._by_date.get(partition_date, SourceCoverageStatus.NOT_PERMITTED)


@lru_cache(maxsize=512)
def _partition_minute_prefix(
    schedule: ExchangeMinuteSchedule,
    partition_date: date,
    partition_timezone: str,
) -> tuple[datetime, tuple[int, ...], tuple[int, ...]]:
    """Return eligible/out-of-coverage prefix counts for one source date."""

    timezone = ZoneInfo(partition_timezone)
    local_start = datetime.combine(partition_date, time.min, tzinfo=timezone)
    local_end = datetime.combine(
        partition_date + timedelta(days=1),
        time.min,
        tzinfo=timezone,
    )
    start = local_start.astimezone(UTC)
    end = local_end.astimezone(UTC)
    minutes = int((end - start).total_seconds() // 60)
    eligible = [0]
    outside = [0]
    for offset in range(1, minutes + 1):
        status = schedule.slot(start + offset * _MINUTE).status
        eligible.append(eligible[-1] + int(status is MinuteSlotStatus.ELIGIBLE))
        outside.append(
            outside[-1] + int(status is MinuteSlotStatus.OUTSIDE_SCHEDULE_COVERAGE)
        )
    return start, tuple(eligible), tuple(outside)


def _holiday(
    day: str,
    start: str,
    end: str,
    reason: str,
) -> ScheduleClosure:
    parsed = date.fromisoformat(day)
    return ScheduleClosure(
        start_local=datetime.combine(parsed, time.fromisoformat(start)),
        end_local=datetime.combine(parsed, time.fromisoformat(end)),
        status=MinuteSlotStatus.HOLIDAY_CLOSURE,
        reason=reason,
    )


# Explicit committed snapshot used by formula v2.  Full closures cover midnight to
# the 18:00 ET reopen; early closes cover 13:00 to the reopen.  Weekly closure and
# daily maintenance are normalized rules above and are part of the content hash.
_HOLIDAY_CLOSURES = (
    _holiday("2024-01-01", "00:00", "18:00", "new_years_day"),
    _holiday("2024-01-15", "13:00", "18:00", "martin_luther_king_jr_day"),
    _holiday("2024-02-19", "13:00", "18:00", "presidents_day"),
    _holiday("2024-03-29", "00:00", "18:00", "good_friday"),
    _holiday("2024-05-27", "13:00", "18:00", "memorial_day"),
    _holiday("2024-06-19", "13:00", "18:00", "juneteenth"),
    _holiday("2024-07-04", "13:00", "18:00", "independence_day"),
    _holiday("2024-09-02", "13:00", "18:00", "labor_day"),
    _holiday("2024-11-28", "13:00", "18:00", "thanksgiving_day"),
    _holiday("2024-12-25", "00:00", "18:00", "christmas_day"),
    _holiday("2025-01-01", "00:00", "18:00", "new_years_day"),
    _holiday("2025-01-20", "13:00", "18:00", "martin_luther_king_jr_day"),
    _holiday("2025-02-17", "13:00", "18:00", "presidents_day"),
    _holiday("2025-04-18", "00:00", "18:00", "good_friday"),
    _holiday("2025-05-26", "13:00", "18:00", "memorial_day"),
    _holiday("2025-06-19", "13:00", "18:00", "juneteenth"),
    _holiday("2025-07-04", "00:00", "18:00", "independence_day"),
    _holiday("2025-09-01", "13:00", "18:00", "labor_day"),
    _holiday("2025-11-27", "13:00", "18:00", "thanksgiving_day"),
    _holiday("2025-12-25", "00:00", "18:00", "christmas_day"),
    _holiday("2026-01-01", "00:00", "18:00", "new_years_day"),
    _holiday("2026-01-19", "13:00", "18:00", "martin_luther_king_jr_day"),
    _holiday("2026-02-16", "13:00", "18:00", "presidents_day"),
    _holiday("2026-04-03", "00:00", "18:00", "good_friday"),
    _holiday("2026-05-25", "13:00", "18:00", "memorial_day"),
    _holiday("2026-06-19", "13:00", "18:00", "juneteenth"),
    _holiday("2026-07-03", "13:00", "18:00", "independence_day_observed"),
    _holiday("2026-09-07", "13:00", "18:00", "labor_day"),
    _holiday("2026-11-26", "13:00", "18:00", "thanksgiving_day"),
    _holiday("2026-12-25", "00:00", "18:00", "christmas_day"),
    _holiday("2027-01-01", "00:00", "18:00", "new_years_day"),
    _holiday("2027-01-18", "13:00", "18:00", "martin_luther_king_jr_day"),
    _holiday("2027-02-15", "13:00", "18:00", "presidents_day"),
    _holiday("2027-03-26", "00:00", "18:00", "good_friday"),
    _holiday("2027-05-31", "13:00", "18:00", "memorial_day"),
    _holiday("2027-06-18", "13:00", "18:00", "juneteenth_observed"),
    _holiday("2027-07-05", "13:00", "18:00", "independence_day_observed"),
    _holiday("2027-09-06", "13:00", "18:00", "labor_day"),
    _holiday("2027-11-25", "13:00", "18:00", "thanksgiving_day"),
    _holiday("2027-12-24", "00:00", "18:00", "christmas_day_observed"),
)

_SPECIAL_CLOSURES = (
    ScheduleClosure(
        start_local=datetime(2025, 1, 9, 9, 30),
        end_local=datetime(2025, 1, 9, 18, 0),
        status=MinuteSlotStatus.SPECIAL_CLOSURE,
        reason="national_day_of_mourning",
    ),
)

CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE = ExchangeMinuteSchedule(
    policy_id=CALENDAR_POLICY_ID,
    timezone="America/New_York",
    coverage_start_utc=datetime(2024, 1, 1, tzinfo=UTC),
    coverage_end_utc=datetime(2028, 1, 1, tzinfo=UTC),
    normalized_sessions=(
        ("sunday_reopen", "18:00", "24:00", (6,)),
        ("weekday_eth", "00:00", "17:00", (0, 1, 2, 3, 4)),
        ("weekday_reopen", "18:00", "24:00", (0, 1, 2, 3, 4)),
    ),
    maintenance_windows=(("17:00", "18:00"),),
    holiday_closures=_HOLIDAY_CLOSURES,
    special_closures=_SPECIAL_CLOSURES,
)

# Safe default for synthetic/runtime callers that do not prepare partition-specific
# evidence.  Artifact preparation supplies an explicit permitted-date declaration.
DEFAULT_CONTEXT_SOURCE_COVERAGE = ContextSourceCoverage.all_available(
    start_date=CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE.coverage_start_utc.date(),
    end_date=CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE.coverage_end_utc.date(),
    cutoff_ts_utc=CME_EQUITY_INDEX_FUTURES_ETH_SCHEDULE.coverage_end_utc,
)
