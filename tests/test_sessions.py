"""Tests for ET session classification + the shared trading-day primitive.

Fidelity targets (engine v3 — zero drift from the research training path):
  * ET windows: asia 19:00->02:45 (crosses midnight), london 03:00->08:00,
    ny 09:00->17:00, with deliberate "none" gaps 18:00-19:00, 02:45-03:00,
    08:00-09:00 and 17:00-18:00.
  * Trading-day boundary at 18:00 ET (CME rollover, UNCHANGED): >= rolls to the
    next day.
  * Closed-window handling on the non-canonical Chicago reference scheme.

All timestamps are fixed tz-aware UTC datetimes. On 2025-06-02 US/Eastern is EDT
(UTC-4) and America/Chicago is CDT (UTC-5), so:
  ET local = UTC - 4h   ->  UTC = ET + 4h
  CT local = UTC - 5h   ->  UTC = CT + 5h
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from strategy_core.constants import (
    RESEARCH_SESSION_SCHEME,
    TRADE_LAB_CT_SESSION_SCHEME,
)
from strategy_core.decisions.sessions import (
    classify_session,
    is_in_closed_window,
    trading_day_for,
)


def _utc(hour: int, minute: int = 0) -> datetime:
    """A fixed 2025-06-02 UTC timestamp (deterministic; never now())."""
    return datetime(2025, 6, 2, hour, minute, tzinfo=timezone.utc)


# ── classify_session: ET boundary cases ─────────────────────────────────────


def test_1759_et_is_none_session_same_trading_day():
    # 17:59 ET: before the 18:00 boundary -> same calendar day; sits in the
    # deliberate 17:00-18:00 gap (ny ended at 17:00) -> no named window.
    info = classify_session(_utc(21, 59))
    assert info.trading_day == date(2025, 6, 2)
    assert info.session == "none"


def test_1800_vs_1900_et_boundary_gap_then_asia():
    # 18:00 ET: at the boundary -> trading day rolls to the next calendar day,
    # but asia does NOT open until 19:00 -> 18:00-19:00 is the "none" gap.
    boundary = classify_session(_utc(22, 0))
    assert boundary.trading_day == date(2025, 6, 3)
    assert boundary.session == "none"
    # 19:00 ET: asia (19:00->02:45) begins.
    asia = classify_session(_utc(23, 0))
    assert asia.trading_day == date(2025, 6, 3)
    assert asia.session == "asia"


def test_0030_et_is_asia_same_trading_day():
    # 00:30 ET: asia crosses midnight (t < 02:45); before 18:00 -> same day.
    info = classify_session(_utc(4, 30))
    assert info.trading_day == date(2025, 6, 2)
    assert info.session == "asia"


def test_0244_vs_0245_et_asia_to_none():
    # 02:44 ET: still asia (end is exclusive at 02:45).
    before = classify_session(_utc(6, 44))
    assert before.trading_day == date(2025, 6, 2)
    assert before.session == "asia"
    # 02:45 ET: asia has ended -> 02:45-03:00 gap -> "none".
    at = classify_session(_utc(6, 45))
    assert at.trading_day == date(2025, 6, 2)
    assert at.session == "none"


def test_0200_et_is_asia_not_london():
    # 02:00 ET: v3 asia runs to 02:45, so 02:00 is ASIA (not london).
    info = classify_session(_utc(6, 0))
    assert info.trading_day == date(2025, 6, 2)
    assert info.session == "asia"


def test_0300_et_is_london():
    # 03:00 ET: london 03:00->08:00 (inclusive start).
    info = classify_session(_utc(7, 0))
    assert info.trading_day == date(2025, 6, 2)
    assert info.session == "london"


def test_0859_vs_0900_et_none_to_ny():
    # 08:59 ET: 08:00-09:00 london->ny gap -> "none".
    before = classify_session(_utc(12, 59))
    assert before.trading_day == date(2025, 6, 2)
    assert before.session == "none"
    # 09:00 ET: ny opens (inclusive start).
    at = classify_session(_utc(13, 0))
    assert at.trading_day == date(2025, 6, 2)
    assert at.session == "ny"


def test_1659_vs_1700_et_ny_to_none():
    # 16:59 ET: still ny (end is exclusive at 17:00).
    before = classify_session(_utc(20, 59))
    assert before.trading_day == date(2025, 6, 2)
    assert before.session == "ny"
    # 17:00 ET: ny has ended -> 17:00-18:00 gap -> "none".
    at = classify_session(_utc(21, 0))
    assert at.trading_day == date(2025, 6, 2)
    assert at.session == "none"


def test_classify_session_returns_local_ts_in_scheme_tz():
    info = classify_session(_utc(13, 0))
    assert info.local_ts.hour == 9
    assert info.local_ts.minute == 0
    assert info.local_ts.utcoffset().total_seconds() == -4 * 3600


# ── naive datetime is rejected ──────────────────────────────────────────────


def test_naive_datetime_raises_value_error():
    naive = datetime(2025, 6, 2, 13, 30)  # no tzinfo
    with pytest.raises(ValueError):
        classify_session(naive)
    with pytest.raises(ValueError):
        trading_day_for(naive)
    with pytest.raises(ValueError):
        is_in_closed_window(naive)


# ── trading_day_for primitive mirrors classify_session ──────────────────────


def test_trading_day_for_matches_classify_session():
    for hour, minute in [(21, 59), (22, 0), (4, 30), (13, 30), (20, 15)]:
        ts = _utc(hour, minute)
        assert trading_day_for(ts) == classify_session(ts).trading_day


def test_trading_day_for_boundary_rollover():
    assert trading_day_for(_utc(21, 59)) == date(2025, 6, 2)  # 17:59 ET
    assert trading_day_for(_utc(22, 0)) == date(2025, 6, 3)  # 18:00 ET


# ── research scheme has no closed window ─────────────────────────────────────


def test_research_scheme_never_closed():
    # The canonical ET scheme drops nothing (closed_window is None).
    assert RESEARCH_SESSION_SCHEME.closed_window is None
    assert is_in_closed_window(_utc(22, 0)) is False
    assert trading_day_for(_utc(22, 0)) is not None


# ── Chicago reference scheme closed window 16:00-18:00 CT ────────────────────


def test_ct_scheme_closed_window_session_and_no_trading_day():
    # 16:00 CT (UTC 21:00): start of the CT 16:00-18:00 closed window.
    info = classify_session(_utc(21, 0), TRADE_LAB_CT_SESSION_SCHEME)
    assert info.session == "closed"
    assert info.trading_day is None
    # 17:00 CT (UTC 22:00): still inside the closed window.
    info_mid = classify_session(_utc(22, 0), TRADE_LAB_CT_SESSION_SCHEME)
    assert info_mid.session == "closed"
    assert info_mid.trading_day is None


def test_ct_scheme_is_in_closed_window_flags():
    assert is_in_closed_window(_utc(21, 0), TRADE_LAB_CT_SESSION_SCHEME) is True
    assert is_in_closed_window(_utc(22, 0), TRADE_LAB_CT_SESSION_SCHEME) is True
    # 18:00 CT (UTC 23:00): closed window end is exclusive -> not closed,
    # asia opens and the trading day rolls forward.
    reopen = classify_session(_utc(23, 0), TRADE_LAB_CT_SESSION_SCHEME)
    assert reopen.session == "asia"
    assert reopen.trading_day == date(2025, 6, 3)
    assert is_in_closed_window(_utc(23, 0), TRADE_LAB_CT_SESSION_SCHEME) is False


def test_ct_scheme_just_before_closed_window_is_ny():
    # 15:59 CT (UTC 20:59): ny 08:00->16:00 still open, not yet closed.
    info = classify_session(_utc(20, 59), TRADE_LAB_CT_SESSION_SCHEME)
    assert info.session == "ny"
    assert info.trading_day == date(2025, 6, 2)
    assert is_in_closed_window(_utc(20, 59), TRADE_LAB_CT_SESSION_SCHEME) is False
