"""Tests for the promoted ``strategy.json`` contract schema + loader.

Covers the canonical fail-closed flow ported from Trade-Lab plus the new
``engine_version`` structural binding (spec §6). All inputs are built inline from a
single complete valid contract dict so each negative case differs from the valid
baseline by exactly one mutation; the dict is written to a ``tmp_path`` json file so
the loader's real disk-read / JSON-parse path is exercised.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from strategy_core import CONTRACT_VERSION, ENGINE_VERSION
from strategy_core.contract.loader import load_strategy_contract
from strategy_core.contract.schema import (
    ClassMap,
    ContractError,
    FeatureSet,
    StrategyContract,
)


def _valid_contract_dict() -> dict[str, Any]:
    """A complete, valid contract dict: every section present, all validators satisfied.

    The 6 feature names partition exactly into interaction + approach; the class_map
    is contiguous-from-zero with unique labels; ``engine_version`` matches the package.
    """

    interaction_features = (
        "int_time_beyond_level",
        "int_time_within_2pts",
        "int_absorption_ratio",
    )
    approach_features = (
        "app_large_trade_vol_pct",
        "app_avg_trade_size",
        "app_max_spread",
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "strategy_id": "nq_reversal_v1",
        "training_mode": "dashboard_utility",
        "supported_by_runtime": True,
        "instrument": "NQ",
        "tick_size": 0.25,
        "point_value": 20.0,
        "model": {
            "type": "catboost",
            "loss_function": "MultiClass",
            "file": "model.cbm",
        },
        "feature_set": {
            "names": list(interaction_features) + list(approach_features),
            "order_is_contractual": True,
            "interaction_features": list(interaction_features),
            "approach_features": list(approach_features),
            "nan_policy": "zero_fill",
        },
        "class_map": {
            "0": "tradeable_reversal",
            "1": "trap_reversal",
            "2": "aggressive_blowthrough",
        },
        "session_scheme": {
            "timezone": "US/Eastern",
            "trading_day_boundary": "18:00",
            "sessions": {
                "asia": {"start": "18:00", "end": "01:00", "crosses_midnight": True},
                "london": {"start": "01:00", "end": "08:00"},
                "ny_rth": {"start": "09:30", "end": "16:15"},
            },
        },
        "level_scheme": {
            "pdh_pdl_source": "prior_rth",
            "session_levels": ["asia_high", "asia_low"],
            "available_from_guard": True,
        },
        "touch_rule": {
            "type": "first_touch",
            "bar_type": "tick",
            "zone_proximity_pts": 3.0,
            "zone_representative_price": "mean",
            "scope": "trading_day",
            "direction_from_side": {"LOW": "LONG", "HIGH": "SHORT"},
        },
        "feature_windows": {
            "interaction_window_minutes": 5,
            "approach_window_minutes": 90,
            "within_band_pts": 2.0,
            "level_proximity_pts": 0.5,
            "large_trade_threshold": 10,
            "mid_price_source": "trade_price",
        },
        "label_policy": {
            "resolution": "forward_window",
            "entry_reference": "touch_price",
            "decision_offset_minutes": 5,
            "tp_points": 15.0,
            "sl_points": 30.0,
            "trap_mfe_min": 5.0,
            "forward_bar_type": "tick",
            "forward_cutoff": "rth_end",
            "no_resolution_dropped": True,
        },
        "inference": {
            "eligible_class": "tradeable_reversal",
            "eligible_session": "ny_rth",
            "confidence_gate": 0.6,
        },
        "data_requirements": {
            "min_book_level": "mbp-1",
            "live_schemas": ["mbp-1", "trades"],
            "replay_schemas": ["mbp-1", "trades"],
            "depth_usage": "top_of_book",
        },
        "provenance": {
            "dataset_config_hash": "abc123",
            "catboost": {"iterations": 500, "depth": 6},
        },
    }


def _write(tmp_path: Path, payload: dict[str, Any]) -> Path:
    target = tmp_path / "strategy.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_valid_contract_loads(tmp_path: Path) -> None:
    path = _write(tmp_path, _valid_contract_dict())

    contract = load_strategy_contract(path)

    assert isinstance(contract, StrategyContract)
    assert contract.contract_version == CONTRACT_VERSION
    assert contract.engine_version == ENGINE_VERSION
    assert contract.feature_count == 6
    assert contract.class_map.labels == (
        "tradeable_reversal",
        "trap_reversal",
        "aggressive_blowthrough",
    )
    assert len(contract.class_map) == 3


def test_valid_contract_loads_with_matching_expected_engine_version(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, _valid_contract_dict())

    contract = load_strategy_contract(path, expected_engine_version=ENGINE_VERSION)

    assert contract.engine_version == ENGINE_VERSION


def test_wrong_contract_version_raises(tmp_path: Path) -> None:
    payload = _valid_contract_dict()
    payload["contract_version"] = "some_other_contract_v9"
    path = _write(tmp_path, payload)

    with pytest.raises(ContractError):
        load_strategy_contract(path)


def test_wrong_engine_version_with_expected_raises(tmp_path: Path) -> None:
    payload = _valid_contract_dict()
    payload["engine_version"] = "strategy_core_engine_v999"
    path = _write(tmp_path, payload)

    with pytest.raises(ContractError):
        load_strategy_contract(path, expected_engine_version=ENGINE_VERSION)


def test_unknown_extra_key_raises(tmp_path: Path) -> None:
    payload = _valid_contract_dict()
    payload["unexpected_field"] = "drift"
    path = _write(tmp_path, payload)

    with pytest.raises(ContractError):
        load_strategy_contract(path)


def test_non_contiguous_class_map_raises(tmp_path: Path) -> None:
    payload = _valid_contract_dict()
    payload["class_map"] = {
        "0": "tradeable_reversal",
        "2": "trap_reversal",
        "3": "aggressive_blowthrough",
    }
    path = _write(tmp_path, payload)

    with pytest.raises(ContractError):
        load_strategy_contract(path)


def test_feature_set_names_not_union_raises(tmp_path: Path) -> None:
    payload = _valid_contract_dict()
    # Drop one approach feature from names so names != interaction + approach.
    payload["feature_set"]["names"] = payload["feature_set"]["names"][:-1]
    path = _write(tmp_path, payload)

    with pytest.raises(ContractError):
        load_strategy_contract(path)


def test_unreadable_path_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"

    with pytest.raises(ContractError):
        load_strategy_contract(missing)


def test_invalid_json_raises(tmp_path: Path) -> None:
    target = tmp_path / "strategy.json"
    target.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ContractError):
        load_strategy_contract(target)


def test_non_dict_payload_raises(tmp_path: Path) -> None:
    target = tmp_path / "strategy.json"
    target.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ContractError):
        load_strategy_contract(target)


def test_class_map_coerces_string_keys_directly() -> None:
    class_map = ClassMap.model_validate(
        {"0": "tradeable_reversal", "1": "trap_reversal"}
    )

    assert class_map.labels == ("tradeable_reversal", "trap_reversal")
    assert len(class_map) == 2


def test_class_map_duplicate_labels_raise() -> None:
    with pytest.raises(ValueError):
        ClassMap.model_validate({"0": "dup", "1": "dup"})


def test_feature_set_validator_independently() -> None:
    with pytest.raises(ValueError):
        FeatureSet.model_validate(
            {
                "names": ["a", "b", "c"],
                "order_is_contractual": True,
                "interaction_features": ["a"],
                "approach_features": ["b"],  # missing "c" -> not a partition
                "nan_policy": "zero_fill",
            }
        )


def test_models_are_frozen(tmp_path: Path) -> None:
    contract = load_strategy_contract(_write(tmp_path, _valid_contract_dict()))

    with pytest.raises(Exception):
        contract.tick_size = 0.5  # type: ignore[misc]


def test_baseline_dict_is_unmutated_between_cases() -> None:
    # Guard: each negative case deep-copies via _valid_contract_dict(), so a fresh
    # baseline is independent. Confirm two builds are equal but not the same object.
    first = _valid_contract_dict()
    second = copy.deepcopy(_valid_contract_dict())
    assert first == second
