"""Cross-cutting IFVG context acceptance gates (source tests 55--65)."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

# Reuse the repaired v2 characterization fixtures without copying strategy inputs.
sys.path.insert(0, str(Path(__file__).parent))
from test_ifvg_replay_parity import _DAY0, _three_days  # noqa: E402
from test_ifvg_v2_e2e_goldens import (  # noqa: E402
    _T0,
    _bar,
    _fvg,
    _reducer,
    _step,
)

from strategy_core.strategies.ifvg_smc.context_config import (  # noqa: E402
    ContextFeatureConfig,
    build_context_identity,
    build_feature_registry,
)
from strategy_core.strategies.ifvg_smc.context_features import (  # noqa: E402
    IfvgContextObserver,
    context_observer_seed_hash,
)
from strategy_core.strategies.ifvg_smc.context_records import CaptureKind  # noqa: E402
from strategy_core.strategies.ifvg_smc.records import IfvgEmission  # noqa: E402
from strategy_core.strategies.ifvg_smc.replay import (  # noqa: E402
    ContextReplayTape,
    IfvgContextDayResult,
    _runtime_scheme,
    run_day,
)
from strategy_core.strategies.ifvg_smc.section import (  # noqa: E402
    default_ifvg_smc_section,
    ifvg_profile_hash,
)
from strategy_core.strategies.ifvg_smc.state import seed_hash  # noqa: E402
from strategy_core.structures.context import canonical_json  # noqa: E402
from strategy_core.structures.fvg import FvgState, GapDirection  # noqa: E402
from strategy_core.types import Direction  # noqa: E402


def _context_replay(
    config: ContextFeatureConfig | None = None,
    *,
    tape: ContextReplayTape | None = None,
):
    section = default_ifvg_smc_section()
    core_seed = None
    context_seed = None
    results: list[IfvgContextDayResult] = []
    for day_index, bars in enumerate(_three_days()):
        result = run_day(
            bars,
            section=section,
            seed=core_seed,
            context_config=config or ContextFeatureConfig(),
            context_seed=context_seed,
            context_replay_tape=tape,
            trading_day=_DAY0 + timedelta(days=day_index),
        )
        assert isinstance(result, IfvgContextDayResult)
        results.append(result)
        core_seed = result.end_seed
        context_seed = result.end_context_seed
    return results


def test_context_replay_tape_matches_streaming_record_for_record() -> None:
    tape = ContextReplayTape()
    streaming = _context_replay(tape=tape)
    playback = _context_replay(tape=tape)

    assert [item.emissions for item in playback] == [
        item.emissions for item in streaming
    ]
    assert [item.context_events for item in playback] == [
        item.context_events for item in streaming
    ]
    assert [item.confirmed_swings for item in playback] == [
        item.confirmed_swings for item in streaming
    ]
    assert [item.pool_lifecycle_events for item in playback] == [
        item.pool_lifecycle_events for item in streaming
    ]
    assert [item.sweep_link_events for item in playback] == [
        item.sweep_link_events for item in streaming
    ]
    assert [context_observer_seed_hash(item.end_context_seed) for item in playback] == [
        context_observer_seed_hash(item.end_context_seed) for item in streaming
    ]
    assert all(item.performance_trace.observer_step_ns for item in playback)


def test_context_replay_tape_refuses_source_drift() -> None:
    tape = ContextReplayTape()
    _context_replay(tape=tape)
    bars = _three_days()[0]
    changed = dict(bars)
    changed[60] = (replace(changed[60][0], close_ticks=changed[60][0].close_ticks + 1),)

    with pytest.raises(ValueError, match="input drifted"):
        run_day(
            changed,
            section=default_ifvg_smc_section(),
            seed=None,
            context_config=ContextFeatureConfig(),
            context_seed=None,
            context_replay_tape=tape,
            trading_day=_DAY0,
        )


def _disabled_replay():
    section = default_ifvg_smc_section()
    seed = None
    results = []
    for day_index, bars in enumerate(_three_days()):
        result = run_day(
            bars,
            section=section,
            seed=seed,
            trading_day=_DAY0 + timedelta(days=day_index),
        )
        results.append(result)
        seed = result.end_seed
    return results


def _trade_fixture_events():
    htf = _fvg(
        3600,
        GapDirection.BULLISH,
        10000,
        10020,
        confirmed=_T0 - timedelta(hours=2),
        ident="context-long-htf",
    )
    parent = _fvg(
        300,
        GapDirection.BULLISH,
        10010,
        10018,
        confirmed=_bar(1, 10028, 10031, 10022, 10029).availability_ts_utc,
        ident="context-long-parent",
    )
    opposing = _fvg(
        60,
        GapDirection.BEARISH,
        10008,
        10012,
        confirmed=_bar(3, 10020, 10021, 9992, 9995).availability_ts_utc,
        ident="context-long-opposing",
    )
    entry = _fvg(
        60,
        GapDirection.BULLISH,
        10014,
        10015,
        confirmed=_bar(5, 10015, 10018, 10010, 10016).availability_ts_utc,
        ident="context-long-entry",
    )
    steps = (
        _step(
            _bar(0, 10030, 10032, 10015, 10028),
            htf_live=(FvgState(fvg=htf),),
        ),
        _step(
            _bar(1, 10028, 10031, 10022, 10029),
            new_fvgs={300: (parent,)},
        ),
        _step(_bar(2, 10024, 10026, 10016, 10022)),
        _step(
            _bar(3, 10020, 10021, 9992, 9995),
            new_fvgs={60: (opposing,)},
        ),
        _step(_bar(4, 10000, 10016, 9998, 10014)),
        _step(
            _bar(5, 10015, 10018, 10010, 10016),
            new_fvgs={60: (entry,)},
            session_doc="ny",
        ),
    )
    reducer = _reducer(Direction.LONG)
    observer = IfvgContextObserver(
        config=ContextFeatureConfig(),
        scheme=_runtime_scheme(default_ifvg_smc_section().session_scheme),
        symbol="NQ",
    )
    core: list[IfvgEmission] = []
    context = []
    for item in steps:
        observer.advance_step((), item.bar_1m, item.new_fvgs)
        emissions = reducer.step(item)
        core.extend(emissions)
        context.extend(observer.capture(emissions))
    return tuple(core), tuple(context), observer


def test_55_56_feature_enabled_core_stream_and_eligibility_are_unchanged() -> None:
    disabled = _disabled_replay()
    enabled = _context_replay()
    assert [item.emissions for item in enabled] == [item.emissions for item in disabled]
    assert [seed_hash(item.end_seed) for item in enabled] == [
        seed_hash(item.end_seed) for item in disabled
    ]


def test_57_entry_ordering_is_unchanged() -> None:
    disabled = _disabled_replay()
    enabled = _context_replay()

    def entries(results):
        return [
            emission.record.candidate_id
            for result in results
            for emission in result.emissions
            if emission.kind == "entry_candidate"
        ]

    assert entries(enabled) == entries(disabled)


def test_58_registry_and_payload_have_no_outcome_or_future_sources() -> None:
    forbidden = ("label", "mfe", "mae", "future_return", "realized", "resolution")
    names = [definition.feature_name.lower() for definition in build_feature_registry()]
    assert not any(token in name for token in forbidden for name in names)
    payload = canonical_json([event.to_dict() for result in _context_replay() for event in result.context_events]).lower()
    assert not any(f'"{token}"' in payload for token in forbidden)


def test_59_60_provenance_is_point_in_time() -> None:
    records = []
    for result in _context_replay():
        for event in result.context_events:
            records.extend(
                (
                    event.capture,
                    event.state,
                    event.state.mtf_snapshot,
                    *event.structure_states,
                    *event.structure_deltas,
                    *event.displacement_windows,
                    *event.pool_lifecycle_events,
                    *event.sweep_links,
                )
            )
        records.extend(result.confirmed_swings)
        records.extend(result.pool_lifecycle_events)
        records.extend(result.sweep_link_events)
    assert records
    for record in records:
        assert record.as_of_ts is not None
        if record.source_close_ts is not None:
            assert record.source_close_ts <= record.as_of_ts
        if record.source_confirmed_ts is not None:
            assert record.source_confirmed_ts <= record.as_of_ts


def test_61_missing_reasons_survive_event_serialization() -> None:
    event, record = next(
        (event, record)
        for result in _context_replay()
        for event in result.context_events
        for record in event.structure_states
        if record.missing_reason is not None
    )
    decoded = json.loads(json.dumps(event.to_dict()))
    row = next(
        item
        for item in decoded["structure_states"]
        if item["structure_state_id"] == str(record.structure_state_id)
    )
    assert row["missing_reason"] == record.missing_reason.value


def test_62_63_candidate_decision_and_trade_links_are_exact() -> None:
    _, events, observer = _trade_fixture_events()
    candidate = next(
        event for event in events if event.capture.capture_kind is CaptureKind.ENTRY_CANDIDATE
        and event.capture.candidate_id is not None
    )
    decision = next(
        event for event in events if event.capture.capture_kind is CaptureKind.ELIGIBLE_DECISION
    )
    trade = next(
        event for event in events if event.capture.capture_kind is CaptureKind.EXECUTED_TRADE_LINK
    )
    assert decision.capture.candidate_id == candidate.capture.candidate_id
    assert trade.capture.candidate_id == decision.capture.candidate_id
    assert trade.capture.decision_id == decision.capture.decision_id
    assert trade.capture.frozen_from_capture_id == decision.capture.context_capture_id
    core, _, _ = _trade_fixture_events()
    decision_record = next(item.record for item in core if item.kind == "eligible_decision")
    with pytest.raises(ValueError, match="exact candidate"):
        observer.capture(
            (
                IfvgEmission(
                    kind="eligible_decision",
                    record=replace(decision_record, candidate_id="crossed-candidate"),
                ),
            )
        )


def test_64_formula_identity_changes_without_changing_v2_identity() -> None:
    baseline_config = ContextFeatureConfig()
    changed_config = replace(
        baseline_config,
        feature_formula_version="ifvg_context_formula_v1_test_bump",
    )
    baseline_identity = build_context_identity(baseline_config, symbol="NQ")
    changed_identity = build_context_identity(changed_config, symbol="NQ")
    assert changed_identity.feature_schema_hash != baseline_identity.feature_schema_hash
    assert changed_identity.context_config_hash != baseline_identity.context_config_hash
    section = default_ifvg_smc_section()
    assert ifvg_profile_hash(section) == ifvg_profile_hash(section)
    assert [item.emissions for item in _context_replay(baseline_config)] == [
        item.emissions for item in _context_replay(changed_config)
    ]


def test_65_replay_seed_and_transport_are_deterministic_and_bounded() -> None:
    left = _context_replay()
    right = _context_replay()
    assert [canonical_json(item.context_events) for item in left] == [
        canonical_json(item.context_events) for item in right
    ]
    assert [context_observer_seed_hash(item.end_context_seed) for item in left] == [
        context_observer_seed_hash(item.end_context_seed) for item in right
    ]
    terminal = left[-1].end_context_seed
    assert len(canonical_json(terminal).encode("utf-8")) <= 838_860
    assert max(
        event.serialized_size()
        for result in left
        for event in result.context_events
    ) <= 26_214


def test_oversized_transport_elides_nulls_then_fragments_losslessly() -> None:
    event = next(
        event
        for result in _context_replay()
        for event in result.context_events
        if event.structure_states
    )
    nullable_state = next(
        state
        for state in event.structure_states
        if any(value is None for value in state.to_dict().values())
    )
    states = list(event.structure_states)
    while True:
        oversized = replace(event, structure_states=tuple(states))
        full_payload = oversized.to_dict()
        full_size = len(
            json.dumps(
                full_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
        transports = oversized.to_transport_dicts()
        if len(transports) > 1:
            break
        states.append(nullable_state)

    assert oversized.to_dict() == full_payload
    assert oversized.serialized_size() <= 26_214 < full_size
    assert len(transports) > 1
    assert all(
        transport["transport_fragment"]["context_capture_id"]
        == full_payload["capture"]["context_capture_id"]
        for transport in transports
    )
    assert [transport["transport_fragment"]["index"] for transport in transports] == [
        *range(len(transports))
    ]
    transported_states = [
        state
        for transport in transports
        for state in transport["structure_states"]
    ]
    assert len(transported_states) == len(full_payload["structure_states"])
    compact_state = transported_states[-1]
    for key, value in full_payload["structure_states"][-1].items():
        if value is not None:
            assert compact_state[key] == value


def test_67_synthetic_context_replay_stays_within_absolute_smoke_budget() -> None:
    started = time.perf_counter()
    results = _context_replay()
    elapsed = time.perf_counter() - started
    assert sum(len(item.context_events) for item in results) > 0
    assert elapsed < 2.0
