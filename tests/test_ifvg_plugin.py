"""``ifvg_smc`` plugin conformance + section identity tests.

Mirrors ``test_touch_reversal_plugin.py``'s shape: registration resolvable
through the fail-closed registry, declarations single-sourced from constants,
honest stubs return exactly ``()``, and the profile hash is stable/sensitive.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from strategy_core.constants import TIME_TF_SECONDS
from strategy_core.strategies.ifvg_smc.plugin import IfvgSmcPlugin
from strategy_core.strategies.ifvg_smc.section import (
    IfvgSmcSection,
    default_ifvg_smc_section,
    ifvg_profile_hash,
)
from strategy_core.strategies.registry import get_strategy
from strategy_core.types import BarKind


def test_registered_and_resolvable() -> None:
    assert get_strategy("ifvg_smc") is IfvgSmcPlugin


def test_required_bars_declares_all_eight_time_specs() -> None:
    specs = IfvgSmcPlugin.required_bars()
    assert len(specs) == 8
    assert all(spec.kind is BarKind.TIME for spec in specs)
    assert {spec.label: spec.size for spec in specs} == TIME_TF_SECONDS
    assert IfvgSmcPlugin.decision_bar_label() == "1m"


def test_honest_stubs_return_empty() -> None:
    plugin = IfvgSmcPlugin()
    assert plugin.current_levels() == ()
    assert plugin.snapshot_zones(None) == ()
    spec = plugin.feature_spec()
    assert spec.names == () and spec.interaction_features == ()


def test_label_policy_declares_r_relative_confirmation_close() -> None:
    policy = IfvgSmcPlugin().label_policy()
    assert policy.barrier_mode == "r_relative"
    assert policy.barrier.kind == "r_relative"
    assert policy.decision_offset_minutes == 0
    with pytest.raises(NotImplementedError):
        policy.barrier.stop_price(100.0, "long")


def test_section_forbids_unknown_keys() -> None:
    payload = default_ifvg_smc_section().model_dump()
    payload["mystery_knob"] = 1
    with pytest.raises(ValidationError):
        IfvgSmcSection(**payload)


def test_profile_hash_stable_and_sensitive() -> None:
    a = ifvg_profile_hash(default_ifvg_smc_section())
    b = ifvg_profile_hash(default_ifvg_smc_section())
    assert a == b
    changed = default_ifvg_smc_section().model_copy(update={"min_gap_ticks_capture": 2})
    assert ifvg_profile_hash(changed) != a


def test_timeframe_seconds_covers_all_eight() -> None:
    assert default_ifvg_smc_section().timeframe_seconds() == (
        60,
        180,
        300,
        600,
        900,
        1800,
        3600,
        14400,
    )
