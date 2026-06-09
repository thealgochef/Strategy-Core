"""B2 PART 2 — the flag resolver, the construction helper, W2 (registry empty), and W4
(lifecycle propagation keeps the plugin's level state in lockstep, off == on).

These are the synthetic, store-independent gates. The REAL-data go-live gate lives in
validation/test_b2_golive_runtime_parity.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta

from strategy_core.config import PLUGIN_ROUTING_ENV, plugin_routing_enabled
from strategy_core.constants import DEFAULT_TICK_SIZE
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.runtime.wiring import touch_reversal_kwargs
from strategy_core.types import CloseReason, Level, Side, Trade  # noqa: F401 (CloseReason kept for clarity)

DECISION_TF = 147


# ── resolver ──────────────────────────────────────────────────────────────────
def _set_flag(value: str | None):
    if value is None:
        os.environ.pop(PLUGIN_ROUTING_ENV, None)
    else:
        os.environ[PLUGIN_ROUTING_ENV] = value


def test_resolver_default_off_and_truthy_parsing() -> None:
    prev = os.environ.get(PLUGIN_ROUTING_ENV)
    try:
        _set_flag(None)
        assert plugin_routing_enabled() is False  # default OFF
        for truthy in ("1", "true", "TRUE", "Yes", " yes "):
            _set_flag(truthy)
            assert plugin_routing_enabled() is True, truthy
        for falsy in ("0", "false", "no", "", "  ", "on"):  # only 1/true/yes are truthy
            _set_flag(falsy)
            assert plugin_routing_enabled() is False, repr(falsy)
    finally:
        _set_flag(prev)


def test_kwargs_off_empty_on_attaches_plugin_and_section() -> None:
    prev = os.environ.get(PLUGIN_ROUTING_ENV)
    try:
        _set_flag(None)
        assert touch_reversal_kwargs() == {}  # OFF -> None path, byte-identical
        _set_flag("1")
        kw = touch_reversal_kwargs()
        assert set(kw) == {"plugin", "strategy_section"}
        assert kw["plugin"].strategy_id == "touch_reversal"
    finally:
        _set_flag(prev)


# ── W2: import strategy_core leaves the registry empty (fresh interpreter) ─────
def test_w2_import_strategy_core_leaves_registry_empty() -> None:
    """A fresh process importing strategy_core — and even calling the OFF construction
    helper — must NOT register any plugin (the plugin module is imported only on flag-ON)."""
    code = (
        "import os; os.environ.pop('SC_PLUGIN_ROUTING', None);"
        "import strategy_core;"
        "from strategy_core.runtime.wiring import touch_reversal_kwargs;"
        "assert touch_reversal_kwargs() == {};"
        "from strategy_core.strategies import registry;"
        "assert registry._REGISTRY == {}, registry._REGISTRY;"
        "print('OK')"
    )
    env = {k: v for k, v in os.environ.items() if k != PLUGIN_ROUTING_ENV}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert out.returncode == 0, f"stdout={out.stdout!r} stderr={out.stderr!r}"
    assert out.stdout.strip().endswith("OK")


# ── W4: lifecycle propagation — off == on through set_static_levels /
#        load_prior_day_summary / reset ──────────────────────────────────────────
def _bar_trades(n_bars: int, base: datetime) -> list[Trade]:
    low_t = round(99.0 / DEFAULT_TICK_SIZE)   # 396
    high_t = round(101.0 / DEFAULT_TICK_SIZE)  # 404
    return [
        Trade(event_ts_utc=base + timedelta(seconds=i), price_ticks=low_t if i % 2 == 0 else high_t, size=1, side="B")
        for i in range(n_bars * DECISION_TF)
    ]


def _build(flag_on: bool) -> StrategyRuntime:
    prev = os.environ.get(PLUGIN_ROUTING_ENV)
    _set_flag("1" if flag_on else None)
    try:
        return StrategyRuntime(
            requested_symbol="NQ",
            timeframes=(DECISION_TF,),
            decision_timeframe=DECISION_TF,
            **touch_reversal_kwargs(),
        )
    finally:
        _set_flag(prev)


def _seed(rt: StrategyRuntime) -> None:
    # Both lifecycle paths the runtime exposes that touch the level state:
    rt.load_prior_day_summary(date(2026, 1, 5), high_ticks=403, low_ticks=397)  # pdh 100.75 / pdl 99.25
    rt.set_static_levels((Level("manual", 100.0, Side.LOW, None),))


def test_w4_lifecycle_propagation_off_equals_on() -> None:
    """The plugin path (flag ON) stays byte-identical to the None path (flag OFF) when the
    levels come from load_prior_day_summary + set_static_levels, AND across reset()."""
    off = _build(flag_on=False)
    on = _build(flag_on=True)
    assert off._plugin is None and on._plugin is not None

    base = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)  # NY session, trading_day 2026-01-06

    def _run_and_compare(trades: list[Trade]) -> int:
        total = 0
        for tr in trades:
            ua = off.process_event(tr)
            ub = on.process_event(tr)
            assert ua == ub, f"off != on at {tr.event_ts_utc}"
            total += len(ua.touches)
        return total

    # Pass 1: seed via the lifecycle methods (which must propagate to the plugin), replay.
    _seed(off)
    _seed(on)
    touches_1 = _run_and_compare(_bar_trades(3, base))
    assert touches_1 > 0, "expected the seeded levels to be touched"
    assert off.snapshot() == on.snapshot()

    # Pass 2: reset() both (must reset the plugin's level state too), re-seed, replay again.
    off.reset()
    on.reset()
    # White-box (load-bearing for the reset propagation): pass 1 set the level state's
    # _day_high/_day_low/_trading_day; reset() must clear them on the PLUGIN's level state too,
    # else a dropped self._plugin.reset() leaves stale plugin state (the re-seed + same-day
    # replay below would otherwise mask it). Assert the plugin's level state == the runtime's
    # (both cleared).
    rt_ls, pl_ls = on.level_state, on._plugin._levels
    assert (pl_ls._trading_day, pl_ls._day_high, pl_ls._day_low) == \
           (rt_ls._trading_day, rt_ls._day_high, rt_ls._day_low) == (None, None, None)
    assert {k: (r.high_ticks, r.low_ticks) for k, r in pl_ls._ranges.items()} == \
           {k: (r.high_ticks, r.low_ticks) for k, r in rt_ls._ranges.items()}
    _seed(off)
    _seed(on)
    touches_2 = _run_and_compare(_bar_trades(3, base + timedelta(hours=1)))
    assert touches_2 > 0
    assert off.snapshot() == on.snapshot()
