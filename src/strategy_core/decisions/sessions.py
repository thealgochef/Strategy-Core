"""ET session classification and the shared trading-day primitive.

Single-sourced from the canonical research training path. The session windows and
the slicing comparisons (half-open ``[start, end)``, with Asia crossing midnight as
``t >= start or t < end``) are ported verbatim from
``dashboard_utility_builder.py`` -- ``_ET`` and the session time constants
(lines 44-51) and ``_slice_session`` (lines 332-344). The trading-day boundary
(CME 18:00 ET rollover) and the optional closed-window are carried on the
``SessionScheme`` (constants.RESEARCH_SESSION_SCHEME); the comparison
``local.time() >= trading_day_boundary`` rolls a trade into the *next* calendar
day, matching the 18:00->18:00 ET trading day the dataset is built under.

NOTE on the rollover citation: the builder never computes a trading-day label as a
named function -- it materializes each date's dataset over an 18:00 ET (prev day)
-> 18:00 ET (current day) span (builder:276-279, the 23:00->23:00 UTC window during
EST). The ``>=`` boundary and its 18:00 value are grounded in two single-sourced
places that DO state it explicitly: the contract emitter's
``_TRADING_DAY_BOUNDARY = time(18, 0)`` (``strategy_contract.py:53``) and Trade-Lab's
``classify_session`` rollover ``local_time >= time(18, 0)`` (``domain/sessions.py:44``).
Both use ``>=`` (18:00:00 rolls forward), which this module matches.

Trade-Lab's ``domain/candles.py`` is Chicago-based and is *not* canonical for
sessions; the canonical scheme is ET and already encoded as
``constants.RESEARCH_SESSION_SCHEME``. Both repos call into this one module so a
trade classifies into the same session/trading-day in research and live.

Ported from:
  Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/dashboard_utility_builder.py
    :44-51  (_ET, _ASIA_START/_END, _LONDON_START/_END, _NY_RTH_START/_END)
    :314-322 (_ensure_et_index -- UTC->ET conversion semantics)
    :332-344 (_slice_session -- the per-window mask comparisons)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from strategy_core.constants import RESEARCH_SESSION_SCHEME
from strategy_core.types import SessionInfo, SessionScheme

__all__ = [
    "classify_session",
    "trading_day_for",
    "is_in_closed_window",
]

#: Session name returned for a timestamp inside a trading day but outside every
#: named window (e.g. the ET 08:00-09:30 pre-RTH gap and the 16:15-18:00 gap).
_NO_SESSION = "none"

#: Session name returned for a timestamp inside the scheme's ``closed_window``.
_CLOSED_SESSION = "closed"


def _to_local(ts_utc: datetime, scheme: SessionScheme) -> datetime:
    """Convert a tz-aware UTC timestamp into the scheme's local timezone.

    Mirrors ``_ensure_et_index`` (dashboard_utility_builder.py:314-322): a naive
    index is illegal here (the research path localizes to UTC first, but at this
    layer a naive timestamp is a caller bug), and a tz-aware timestamp is simply
    converted to the scheme timezone via ``zoneinfo``.
    """
    if ts_utc.tzinfo is None:
        raise ValueError("ts_utc must be timezone-aware (UTC); got a naive datetime")
    return ts_utc.astimezone(ZoneInfo(scheme.timezone))


def classify_session(
    ts_utc: datetime,
    scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
) -> SessionInfo:
    """Classify a UTC timestamp into its trading day and named session window.

    1. Convert to the scheme timezone (raises ``ValueError`` if ``ts_utc`` is naive).
    2. If ``scheme.closed_window`` is set and ``start <= local.time() < end``, the
       timestamp has no trading day: ``SessionInfo(None, "closed", local)``.
    3. ``trading_day``: at/after ``trading_day_boundary`` rolls to the next
       calendar day (CME 18:00 ET rollover); otherwise the local calendar date.
    4. ``session``: the first window name (in ``scheme.sessions`` iteration order)
       whose ``SessionWindow.contains(local.time())`` is True, else ``"none"``.

    The half-open window comparisons live in ``SessionWindow.contains`` and match
    ``_slice_session`` (dashboard_utility_builder.py:332-344) exactly: normal
    windows use ``start <= t < end``; Asia (crosses midnight) uses
    ``t >= start or t < end``.
    """
    local = _to_local(ts_utc, scheme)
    local_time = local.time()

    if scheme.closed_window is not None:
        closed_start, closed_end = scheme.closed_window
        if closed_start <= local_time < closed_end:
            return SessionInfo(trading_day=None, session=_CLOSED_SESSION, local_ts=local)

    if local_time >= scheme.trading_day_boundary:
        trading_day = local.date() + timedelta(days=1)
    else:
        trading_day = local.date()

    session = _NO_SESSION
    for name, window in scheme.sessions.items():
        if window.contains(local_time):
            session = name
            break

    return SessionInfo(trading_day=trading_day, session=session, local_ts=local)


def trading_day_for(
    ts_utc: datetime,
    scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
) -> date | None:
    """Return the trading day a UTC timestamp belongs to, or ``None`` if closed.

    The trading-day primitive the candle builders share. Identical rule to
    ``classify_session`` step 3; returns ``None`` for timestamps inside the
    scheme's ``closed_window`` (which have no trading day).
    """
    return classify_session(ts_utc, scheme).trading_day


def is_in_closed_window(
    ts_utc: datetime,
    scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
) -> bool:
    """Whether a UTC timestamp falls in the scheme's ``closed_window``.

    ``False`` when the scheme has no closed window (the research scheme drops
    nothing). Raises ``ValueError`` if ``ts_utc`` is naive (via ``_to_local``).
    """
    if scheme.closed_window is None:
        # Still validate tz-awareness for a consistent contract across the three
        # functions: a naive timestamp is a caller bug regardless of scheme.
        _to_local(ts_utc, scheme)
        return False
    local_time = _to_local(ts_utc, scheme).time()
    closed_start, closed_end = scheme.closed_window
    return closed_start <= local_time < closed_end
