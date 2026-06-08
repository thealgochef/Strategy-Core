"""Feed/data-source event helpers for Strategy-Core runtime sources.

These types deliberately stay independent of Trade-Lab DTOs and provider SDKs. They
carry path-safe data-quality/status information alongside neutral ``Trade``/``Quote``
objects from :mod:`strategy_core.types`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

__all__ = [
    "DataQualityCode",
    "DataQualitySeverity",
    "DataQualityWarning",
    "MarketDataItem",
    "safe_source",
    "safe_text",
]


class DataQualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DataQualityCode(StrEnum):
    INVALID_RECORD = "invalid_record"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INVALID_PRICE = "invalid_price"
    MISSING_REQUIRED_COLUMN = "missing_required_column"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    TIMESTAMP_REGRESSION = "timestamp_regression"
    BACKPRESSURE_DROP = "backpressure_drop"
    PROVIDER_ERROR = "provider_error"


_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s,;]+")
_POSIX_PATH_RE = re.compile(r"/(?:[^\s,;]+/)+[^\s,;]+")
_SECRET_RE = re.compile(r"(?i)(secret|token|password|api[_-]?key)\s*[:=]\s*[^\s,;]+")
_SECRET_WORD_RE = re.compile(r"(?i)secret|token|password|api[_-]?key")


def safe_text(value: str | None) -> str | None:
    """Return ``value`` with local paths and secret-shaped text redacted."""

    if value is None:
        return None
    text = _WINDOWS_PATH_RE.sub("<path>", str(value))
    text = _POSIX_PATH_RE.sub("<path>", text)
    text = _SECRET_RE.sub("<redacted>", text)
    return _SECRET_WORD_RE.sub("<redacted>", text)


def safe_source(source: str | None) -> str | None:
    """Path-safe source label for warnings/status.

    Full local paths are never returned. If a path-like value did not match the
    broader regex, keep only the final filename component.
    """

    text = safe_text(source)
    if text is None:
        return None
    if text == source and ("/" in text or "\\" in text):
        return text.replace("\\", "/").rsplit("/", 1)[-1]
    return text


def _freeze_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        safe_key = safe_text(str(key)) or ""
        if _SECRET_WORD_RE.search(safe_key):
            safe_key = "<redacted_key>"
        if isinstance(value, str):
            sanitized[safe_key] = safe_text(value)
        else:
            sanitized[safe_key] = value
    return MappingProxyType(sanitized)


@dataclass(frozen=True, slots=True)
class DataQualityWarning:
    code: DataQualityCode
    message: str
    severity: DataQualitySeverity = DataQualitySeverity.WARNING
    source: str | None = None
    event_ts_utc: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", safe_text(self.message) or "")
        object.__setattr__(self, "source", safe_source(self.source))
        if self.event_ts_utc is not None:
            if self.event_ts_utc.tzinfo is None:
                raise ValueError("event_ts_utc must be timezone-aware")
            object.__setattr__(self, "event_ts_utc", self.event_ts_utc.astimezone(UTC))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
            "event_ts_utc": None if self.event_ts_utc is None else self.event_ts_utc.isoformat(),
            "metadata": dict(self.metadata),
        }


# Runtime sources yield these plus neutral strategy_core.types Trade/Quote objects.
MarketDataItem = Any
