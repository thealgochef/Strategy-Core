"""Strict, fail-closed loader for ``strategy.json`` contracts.

Ported from Trade-Lab's
``backend/src/trade_lab/domain/contracts/strategy_contract.py:183-217``
(the ``load_strategy_contract`` function), preserving the exact fail-closed flow:
every parse/validation failure surfaces as :class:`ContractError` (never a bare
``ValidationError``) so callers have a single exception type to fail closed on.

One addition over the canonical source: an optional ``expected_engine_version``
hook. When supplied, a contract whose ``engine_version`` does not match is rejected
*after* the contract-version check and *before* full model validation -- this is the
fail-close-on-engine-mismatch binding Trade-Lab uses to refuse a bundle built by an
engine version it cannot reproduce (spec §6).
"""

from __future__ import annotations

import json
from pathlib import Path

from strategy_core import CONTRACT_VERSION

from strategy_core.contract.schema import ContractError, StrategyContract

__all__ = ["load_strategy_contract"]


def load_strategy_contract(
    path: Path | str,
    *,
    expected_engine_version: str | None = None,
) -> StrategyContract:
    """Parse and validate a ``strategy.json`` from disk.

    Raises :class:`ContractError` (never a bare ``ValidationError``) on any parse
    failure, an unexpected ``contract_version``, an ``engine_version`` that does not
    match ``expected_engine_version`` (when supplied), or a feature/class mismatch,
    so callers have a single exception type to fail closed on.

    Ported from ``strategy_contract.py:183-217`` with the ``expected_engine_version``
    fail-close hook added between the contract-version check and model validation.
    """

    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"strategy contract is unreadable: {path.name}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(f"strategy contract is not valid JSON: {path.name}") from exc

    if not isinstance(payload, dict):
        raise ContractError("strategy contract must be a JSON object")

    declared_version = payload.get("contract_version")
    if declared_version != CONTRACT_VERSION:
        raise ContractError(
            f"unsupported contract_version {declared_version!r}; expected {CONTRACT_VERSION!r}"
        )

    if expected_engine_version is not None:
        declared_engine = payload.get("engine_version")
        if declared_engine != expected_engine_version:
            raise ContractError(
                f"unsupported engine_version {declared_engine!r}; "
                f"expected {expected_engine_version!r}"
            )

    try:
        contract = StrategyContract.model_validate(payload)
    except ValueError as exc:
        raise ContractError(f"invalid strategy contract: {exc}") from exc

    return contract
