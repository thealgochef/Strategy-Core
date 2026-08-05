"""IFVG replay parity — the cache-trust theorem + plugin-fold equivalence.

(a) Chained per-day ``run_day`` calls (seed = prior ``end_seed``) are
emission-identical to ONE continuous ``DayOrchestrator`` with a finalize at
each roll, and their terminal seeds hash identically — this is what makes a
seed-stamped per-day cache chain trustworthy.

(b) The plugin's push-shaped fold produces exactly ``run_day``'s emissions on
the same bars — the two consumption shapes share ``DayOrchestrator`` and this
pins that they cannot drift.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta

from strategy_core.candles._ids import make_bar_id
from strategy_core.strategies.ifvg_smc.replay import DayOrchestrator, run_day
from strategy_core.strategies.ifvg_smc.section import default_ifvg_smc_section
from strategy_core.strategies.ifvg_smc.state import seed_hash
from strategy_core.types import Bar, BarKind, CloseReason

_DAY0 = date(2026, 1, 5)
_DAY_START = datetime(2026, 1, 4, 23, 0, tzinfo=UTC)
_BARS_PER_DAY = 240  # 4 x 1H chunks


def _bar_1m(day_idx: int, index: int, o: int, h: int, low: int, c: int) -> Bar:
    day = _DAY0 + timedelta(days=day_idx)
    open_ts = _DAY_START + timedelta(days=day_idx, seconds=60 * index)
    return Bar(
        timeframe_ticks=60,
        trading_day=day,
        bar_index=index,
        bar_id=make_bar_id(60, day, index, BarKind.TIME),
        open_ts_utc=open_ts,
        close_ts_utc=open_ts + timedelta(seconds=59),
        open_ticks=o,
        high_ticks=h,
        low_ticks=low,
        close_ticks=c,
        volume=3,
        trade_count=2,
        is_complete=index < _BARS_PER_DAY - 1,
        is_partial=index >= _BARS_PER_DAY - 1,
        close_reason=(
            CloseReason.COMPLETE if index < _BARS_PER_DAY - 1 else CloseReason.END_OF_DAY
        ),
        kind=BarKind.TIME,
    )


def _day_1m_bars(day_idx: int, chunk_bases: list[int], rng: random.Random) -> list[Bar]:
    bars: list[Bar] = []
    for i in range(_BARS_PER_DAY):
        base = chunk_bases[i // 60]
        o = base + rng.randint(-4, 4)
        c = base + rng.randint(-4, 4)
        h = max(o, c) + rng.randint(0, 4)
        low = min(o, c) - rng.randint(0, 4)
        bars.append(_bar_1m(day_idx, i, o, h, low, c))
    return bars


def _aggregate(bars_1m: list[Bar], seconds: int) -> list[Bar]:
    n = seconds // 60
    out: list[Bar] = []
    day = bars_1m[0].trading_day
    for idx, start in enumerate(range(0, len(bars_1m), n)):
        chunk = bars_1m[start : start + n]
        out.append(
            Bar(
                timeframe_ticks=seconds,
                trading_day=day,
                bar_index=idx,
                bar_id=make_bar_id(seconds, day, idx, BarKind.TIME),
                open_ts_utc=chunk[0].open_ts_utc,
                close_ts_utc=chunk[-1].close_ts_utc,
                open_ticks=chunk[0].open_ticks,
                high_ticks=max(b.high_ticks for b in chunk),
                low_ticks=min(b.low_ticks for b in chunk),
                close_ticks=chunk[-1].close_ticks,
                volume=sum(b.volume for b in chunk),
                trade_count=sum(b.trade_count for b in chunk),
                is_complete=True,
                is_partial=False,
                close_reason=CloseReason.COMPLETE,
                kind=BarKind.TIME,
            )
        )
    return out


def _three_days() -> list[dict[int, list[Bar]]]:
    """Day 1 ramps up (1H bullish gaps), day 2 retraces into them (taps),
    day 3 chops with two-sided jumps — deterministic via seeded jitter."""
    rng = random.Random(5)
    bases = [
        [20000, 20120, 20240, 20360],
        [20300, 20180, 20060, 19940],
        [20000, 20060, 19990, 20050],
    ]
    days: list[dict[int, list[Bar]]] = []
    for day_idx, chunk_bases in enumerate(bases):
        bars_1m = _day_1m_bars(day_idx, chunk_bases, rng)
        by_tf: dict[int, list[Bar]] = {60: bars_1m}
        for seconds in (180, 300, 600, 900, 1800, 3600, 14400):
            by_tf[seconds] = _aggregate(bars_1m, seconds)
        days.append(by_tf)
    return days


def test_chained_run_day_equals_continuous_orchestrator() -> None:
    section = default_ifvg_smc_section()
    days = _three_days()

    chained_emissions = []
    seed = None
    for day_idx, by_tf in enumerate(days):
        result = run_day(
            by_tf,
            section=section,
            seed=seed,
            trading_day=_DAY0 + timedelta(days=day_idx),
        )
        chained_emissions.extend(result.emissions)
        seed = result.end_seed

    orch = DayOrchestrator(section=section, seed=None)
    continuous_emissions = []
    for day_idx, by_tf in enumerate(days):
        trading_day = _DAY0 + timedelta(days=day_idx)
        orch.reset_funnel()
        for tf, bars in by_tf.items():
            if tf == 60:
                continue
            for bar in bars:
                orch.on_higher_tf_bar(bar)
        last_ts = None
        for bar in by_tf[60]:
            continuous_emissions.extend(orch.on_decision_bar(bar))
            last_ts = bar.close_ts_utc
        continuous_emissions.extend(orch.finalize_day(trading_day))
        funnel = orch.day_funnel(trading_day, last_ts)
        from strategy_core.strategies.ifvg_smc.records import IfvgEmission

        continuous_emissions.append(IfvgEmission(kind="funnel", record=funnel))

    assert len(chained_emissions) == len(continuous_emissions)
    for a, b in zip(chained_emissions, continuous_emissions):
        assert a.kind == b.kind
        if a.kind == "funnel":
            assert a.record.counters == b.record.counters
        else:
            assert a.record == b.record

    assert seed is not None
    assert seed_hash(seed) == seed_hash(orch.end_seed(_DAY0 + timedelta(days=2)))

    # The walk must actually exercise the funnel for the parity to mean much.
    total = {}
    for e in chained_emissions:
        if e.kind == "funnel":
            for k, v in e.record.counters.items():
                total[k] = total.get(k, 0) + v
    assert total.get("htf_taps", 0) >= 1
    assert total.get("setups_born", 0) >= 1


def test_seed_hash_goldens_unchanged_by_audit_channel() -> None:
    """Golden hex digests recorded on the PRE-audit-channel tree (commit
    f16d27d0): the seed graph is frozen, so these can never move without a
    ratified schema bump — and the audit channel must not move them."""
    goldens = (
        "fcd5cdf76fd288294c5f3e5fd288708aca82b033399c69898b761f7ae55874b5",
        "2887bf357bc3bcbec0a90b346814a450e34dc1185015a71d68f96947a4084db3",
        "1bfebf0c10d5407235d8760a579b44ade10d8c18bfa40da1ef78d64ed9718e79",
    )
    section = default_ifvg_smc_section()
    for audit_mode in ("disabled", "fsm_audit_v1"):
        seed = None
        for day_idx, by_tf in enumerate(_three_days()):
            result = run_day(
                by_tf,
                section=section,
                seed=seed,
                trading_day=_DAY0 + timedelta(days=day_idx),
                audit_capture_mode=audit_mode,
            )
            seed = result.end_seed
            assert seed_hash(seed) == goldens[day_idx], (audit_mode, day_idx)


def test_audit_channel_parity_across_drive_modes() -> None:
    """Chained per-day run_day and one continuous orchestrator produce
    IDENTICAL audit tuples — the audit twin of the cache-trust theorem — and
    identical core emissions vs an audit-disabled run."""
    section = default_ifvg_smc_section()
    days = _three_days()

    chained_core: list = []
    chained_audit: list[tuple] = []
    seed = None
    for day_idx, by_tf in enumerate(days):
        result = run_day(
            by_tf,
            section=section,
            seed=seed,
            trading_day=_DAY0 + timedelta(days=day_idx),
            dataset_exhausted=day_idx == len(days) - 1,
            audit_capture_mode="fsm_audit_v1",
        )
        chained_core.extend(result.emissions)
        chained_audit.append(result.audit_emissions)
        seed = result.end_seed

    plain_core: list = []
    seed = None
    for day_idx, by_tf in enumerate(days):
        result = run_day(
            by_tf,
            section=section,
            seed=seed,
            trading_day=_DAY0 + timedelta(days=day_idx),
            dataset_exhausted=day_idx == len(days) - 1,
        )
        assert result.audit_emissions == ()
        plain_core.extend(result.emissions)
        seed = result.end_seed

    assert len(chained_core) == len(plain_core)
    for a, b in zip(chained_core, plain_core):
        assert a.kind == b.kind
        if a.kind != "funnel":
            assert a.record == b.record

    orch = DayOrchestrator(
        section=section, seed=None, audit_capture_mode="fsm_audit_v1"
    )
    continuous_audit: list[tuple] = []
    for day_idx, by_tf in enumerate(days):
        trading_day = _DAY0 + timedelta(days=day_idx)
        orch.reset_funnel()
        for tf, bars in by_tf.items():
            if tf == 60:
                continue
            for bar in bars:
                orch.on_higher_tf_bar(bar)
        for bar in by_tf[60]:
            orch.on_decision_bar(bar)
        orch.finalize_day(trading_day)
        if day_idx == len(days) - 1:
            orch.finalize_dataset(trading_day)
        continuous_audit.append(orch.drain_audit_emissions())

    assert sum(len(day) for day in chained_audit) > 0
    for day_idx, (a, b) in enumerate(zip(chained_audit, continuous_audit)):
        assert len(a) == len(b), day_idx
        for x, y in zip(a, b):
            assert x.kind == y.kind and x.record == y.record

    # single total order per day: audit_seq strictly monotone, substep keys
    # unambiguous (a tie here is a contract failure).
    for day_audit in chained_audit:
        seqs = [e.record.stamp.audit_seq for e in day_audit]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        keys = [
            (
                e.record.stamp.source_step_ordinal,
                e.record.stamp.reducer_substep,
                e.record.stamp.reducer_substep_ordinal,
            )
            for e in day_audit
        ]
        assert len(set(keys)) == len(keys)


def test_plugin_fold_equals_run_day() -> None:
    from strategy_core.strategies.ifvg_smc.plugin import IfvgSmcPlugin

    class _Ctx:
        tick_size = 0.25
        point_value = 20.0

    section = default_ifvg_smc_section()
    by_tf = _three_days()[0]
    trading_day = _DAY0

    batch = run_day(by_tf, section=section, seed=None, trading_day=trading_day)
    batch_core = [e for e in batch.emissions if e.kind != "funnel"]

    plugin = IfvgSmcPlugin()
    plugin.configure(section, _Ctx())
    for tf, bars in by_tf.items():
        if tf == 60:
            continue
        for bar in bars:
            plugin.on_bar_closed(bar, _Ctx())
    for bar in by_tf[60]:
        plugin.on_bar_closed(bar, _Ctx())
    plugin_emissions = list(plugin.drain_emissions())
    plugin_emissions.extend(plugin.finalize_trading_day(trading_day))

    assert len(plugin_emissions) == len(batch_core)
    for a, b in zip(plugin_emissions, batch_core):
        assert a.kind == b.kind and a.record == b.record
