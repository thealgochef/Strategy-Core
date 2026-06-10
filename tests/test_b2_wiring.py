"""Plugin construction + lifecycle regression (post-B3 / post-S-B3a).

(Originally the B2 PART 2 flag-resolver / W2 / W4-off-vs-on tests. B3 removed the
``SC_PLUGIN_ROUTING`` flag and the None path; S-B3a then deleted the runtime's redundant
``level_state`` copy and moved the first-touch dedup into the plugin, so the old
runtime-vs-plugin fingerprint lockstep has nothing to compare against. What remains and
still matters: ``touch_reversal_kwargs()`` attaches the plugin, a bare runtime
auto-attaches it, and the runtime's lifecycle methods (``load_prior_day_summary`` /
``set_static_levels`` / ``reset``) write through to the plugin's level state AND its
fired-keys dedup — including that ``reset()`` clears the dedup so a re-seeded same-day
replay re-fires.)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from strategy_core.runtime.state import StrategyRuntime
from strategy_core.runtime.wiring import touch_reversal_kwargs
from strategy_core.types import Level, Side, Trade

DECISION_TF = 147


def _fingerprint(ls) -> tuple:
    """The mutable level-tracking fields of a StrategyLevelState (the W4 invariant target)."""
    return (
        ls._trading_day,
        ls._day_high,
        ls._day_low,
        {k: (r.high_ticks, r.low_ticks) for k, r in ls._ranges.items()},
        {k: (s.high_ticks, s.low_ticks) for k, s in sorted(ls._summaries.items())},
        tuple((lvl.name, lvl.price, lvl.side, lvl.available_from) for lvl in ls._static_levels),
    )


def _bar_trades(n_bars: int, base: datetime) -> list[Trade]:
    low_t = round(99.0 / 0.25)  # 396
    high_t = round(101.0 / 0.25)  # 404
    return [
        Trade(event_ts_utc=base + timedelta(seconds=i), price_ticks=low_t if i % 2 == 0 else high_t, size=1, side="B")
        for i in range(n_bars * DECISION_TF)
    ]


def _runtime() -> StrategyRuntime:
    return StrategyRuntime(requested_symbol="NQ", timeframes=(DECISION_TF,), decision_timeframe=DECISION_TF)


def test_kwargs_attaches_plugin_and_section() -> None:
    kw = touch_reversal_kwargs()
    assert set(kw) == {"plugin", "strategy_section"}
    assert kw["plugin"].strategy_id == "touch_reversal"


def test_bare_runtime_auto_attaches_touch_plugin() -> None:
    rt = _runtime()
    assert rt._plugin is not None and rt._plugin.strategy_id == "touch_reversal"


def test_lifecycle_propagation_reaches_plugin_state() -> None:
    """The runtime's lifecycle methods write through to the plugin's level state — the SOLE
    level fold since S-B3a — and ``reset()`` clears BOTH the plugin's level state and its
    plugin-owned ``_fired_keys`` dedup, so a re-seeded same-day replay re-fires the same
    zone (non-vacuous; were the dedup not cleared, the second pass would be suppressed)."""
    rt = _runtime()
    base = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)  # NY session, trading_day 2026-01-06

    def _seed() -> None:
        rt.load_prior_day_summary(date(2026, 1, 5), high_ticks=403, low_ticks=397)  # pdh 100.75 / pdl 99.25
        rt.set_static_levels((Level("manual", 100.0, Side.LOW, None),))

    def _run(trades: list[Trade]) -> int:
        return sum(len(rt.process_event(tr).touches) for tr in trades)

    # Pass 1: seed via the lifecycle methods (which must reach the plugin), replay.
    _seed()
    assert _run(_bar_trades(3, base)) > 0, "expected the seeded levels to be touched"
    fp = _fingerprint(rt._plugin._levels)
    assert fp[4] == {date(2026, 1, 5): (403, 397)}, "summary did not reach the plugin"
    assert fp[5] and fp[5][0][0] == "manual", "static level did not reach the plugin"
    assert len(rt._plugin._fired_keys) > 0, "the fired touch was not recorded in the plugin dedup"

    # Pass 2: reset() clears the plugin's level state AND its fired-keys dedup.
    rt.reset()
    assert (rt._plugin._levels._trading_day, rt._plugin._levels._day_high, rt._plugin._levels._day_low) == (None, None, None)
    assert rt._plugin._fired_keys == set()

    # Re-seed + SAME-day replay: the same zone fires again — proof the reset cleared the
    # day-scoped dedup (and the reseed reached the plugin) end-to-end.
    _seed()
    assert _run(_bar_trades(3, base + timedelta(hours=1))) > 0
