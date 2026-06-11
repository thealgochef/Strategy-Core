"""Strict, fail-closed loader for ``strategy.json`` contracts.

Ported from Trade-Lab's
``backend/src/trade_lab/domain/contracts/strategy_contract.py:183-217``
(the ``load_strategy_contract`` function), preserving the exact fail-closed flow:
every parse/validation failure surfaces as :class:`ContractError` (never a bare
``ValidationError``) so callers have a single exception type to fail closed on.

One addition over the canonical source: an optional ``expected_platform_version``
hook. When supplied, a contract whose ``platform_version`` does not match is
rejected *after* the contract-version check and *before* full model validation --
this is the fail-close-on-platform-mismatch binding Trade-Lab uses to refuse a
bundle built by a platform version it cannot reproduce (spec §6; the engine axis
renamed at E1, decision 9.3).

Contract v3 (E3) adds the opt-in ``validate_section_via_registry`` hook: after
envelope validation, the contract's raw ``section`` subtree is validated against
``get_strategy(contract.strategy_id).SectionModel`` (the §9.1 registry-time
SectionModel assertion is what makes this resolvable for every registered
plugin). THE CARRIER, precisely: the typed section instance is attached to the
returned contract as the private non-field attribute ``_section_model`` and read
via ``StrategyContract.section_model`` — the loader keeps its plain
single-return call shape (no ``(contract, section)`` tuple, no wrapper object),
and hookless callers are untouched (reading ``section_model`` without the hook
raises :class:`ContractError`). The ENVELOPE is validated ALWAYS; only the
section typing is opt-in. Callers own the plugin-registration import (the
registry is deliberately empty on a bare ``import strategy_core``, D-B3c).
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
    expected_platform_version: str | None = None,
    validate_section_via_registry: bool = False,
) -> StrategyContract:
    """Parse and validate a ``strategy.json`` from disk.

    Raises :class:`ContractError` (never a bare ``ValidationError``) on any parse
    failure, an unexpected ``contract_version``, a ``platform_version`` that does
    not match ``expected_platform_version`` (when supplied), a feature/class
    mismatch, or — when ``validate_section_via_registry`` is True — a
    ``strategy_id`` unknown to the registry or a ``section`` subtree the plugin's
    ``SectionModel`` rejects, so callers have a single exception type to fail
    closed on. With the section hook on, the typed section instance rides the
    returned contract via ``contract.section_model`` (see the module docstring
    for the exact carrier semantics).

    Ported from ``strategy_contract.py:183-217`` with the
    ``expected_platform_version`` fail-close hook added between the
    contract-version check and model validation, and the E3
    ``validate_section_via_registry`` hook after it.
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

    if expected_platform_version is not None:
        declared_platform = payload.get("platform_version")
        if declared_platform != expected_platform_version:
            raise ContractError(
                f"unsupported platform_version {declared_platform!r}; "
                f"expected {expected_platform_version!r}"
            )

    try:
        contract = StrategyContract.model_validate(payload)
    except ValueError as exc:
        raise ContractError(f"invalid strategy contract: {exc}") from exc

    if validate_section_via_registry:
        # Imported lazily: the loader stays import-light for hookless callers and
        # the registry chain stays out of a bare `import strategy_core`. Resolution
        # uses whatever plugins the CALLER registered (the explicit registration
        # import, D-B3c); get_strategy fail-closes on an unknown id.
        from strategy_core.strategies.registry import get_strategy

        plugin_cls = get_strategy(contract.strategy_id)
        try:
            typed_section = plugin_cls.SectionModel.model_validate(dict(contract.section))
        except ValueError as exc:
            raise ContractError(
                f"invalid strategy section for {contract.strategy_id!r}: {exc}"
            ) from exc
        contract._section_model = typed_section

    return contract
