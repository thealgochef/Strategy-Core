"""The single-sourced strategy registry (PLAN §2.3, decision 9.2).

A greppable, version-controlled, in-package ``{strategy_id: plugin_cls}`` table
populated by a ``@register`` decorator at import time, with a fail-closed
``get_strategy(strategy_id)`` lookup. Chosen over setuptools entry-points so the
SHA-pinned Trade-Lab and the (to-be-pinned) Quant-Lab resolve the SAME registry by
construction — entry-points would couple discovery to install state, which is exactly
the asymmetric-binding risk this design removes.

Phase A note (PLAN §7 / Step A2): the registry starts EMPTY and is imported by nothing
in the platform — no dispatch path consults it; the runtime's single fixed pipeline
still runs unconditionally and ``strategy_id`` remains the opaque label it is today. A
strategy lands in the table only when its plugin module is explicitly imported (the
``@register`` side-effect). It becomes a router in Phase E (``model_registry.activate``
gains ``get_strategy(contract.strategy_id)``).

Registry-time assertion (decision 9.1): because the plugin interface is a structural
``runtime_checkable`` Protocol (presence-only), ``register`` does the deeper checks AT
REGISTRATION so a malformed plugin fails at ``@register``, not in the hot path:
``isinstance(plugin_cls, StrategyPlugin)`` (the runtime_checkable presence check),
``required_bars()`` returns a non-empty tuple of ``BarSpec``, and ``SectionModel`` is a
pydantic ``BaseModel`` subclass.
"""

from __future__ import annotations

from pydantic import BaseModel

from strategy_core.contract.schema import ContractError
from strategy_core.strategies.protocols import BarSpec, StrategyPlugin

__all__ = ["register", "get_strategy"]

#: The single registry table. Keyed by ``plugin_cls.strategy_id``.
_REGISTRY: dict[str, type[StrategyPlugin]] = {}


def register(plugin_cls: type[StrategyPlugin]) -> type[StrategyPlugin]:
    """Register a strategy plugin under its ``strategy_id`` (decorator form, PLAN §2.3).

    Runs the §9.1 registry-time assertions BEFORE inserting, so a structurally-loose
    plugin (the trade-off of a ``runtime_checkable`` Protocol) is rejected at import,
    not at first hot-path call. Raises :class:`~strategy_core.contract.schema.ContractError`
    (the engine's single fail-closed contract exception) on any violation.

    Returns the class unchanged so it can be used as a ``@register`` decorator.
    """
    # §9.1 (presence): the class must structurally satisfy StrategyPlugin. isinstance
    # against a runtime_checkable Protocol checks that every required member name is
    # present on the class (methods + identity attrs), catching a plugin missing a hook.
    if not isinstance(plugin_cls, StrategyPlugin):
        raise ContractError(
            f"{plugin_cls!r} does not satisfy the StrategyPlugin protocol "
            f"(missing one or more required members)"
        )

    strategy_id = plugin_cls.strategy_id
    if not isinstance(strategy_id, str) or not strategy_id:
        raise ContractError(
            f"{plugin_cls.__name__} must declare a non-empty str strategy_id"
        )

    # §9.1: required_bars() must return a non-empty tuple of BarSpec.
    try:
        bars = plugin_cls.required_bars()
    except Exception as exc:  # noqa: BLE001 -- surface any declaration error as ContractError
        raise ContractError(
            f"{plugin_cls.__name__}.required_bars() raised at register time: {exc!r}"
        ) from exc
    if not isinstance(bars, tuple) or not bars or not all(isinstance(b, BarSpec) for b in bars):
        raise ContractError(
            f"{plugin_cls.__name__}.required_bars() must return a non-empty tuple of BarSpec"
        )

    # §9.1: SectionModel must be a pydantic BaseModel subclass.
    section_model = getattr(plugin_cls, "SectionModel", None)
    if not (isinstance(section_model, type) and issubclass(section_model, BaseModel)):
        raise ContractError(
            f"{plugin_cls.__name__}.SectionModel must be a pydantic BaseModel subclass"
        )

    existing = _REGISTRY.get(strategy_id)
    if existing is not None and existing is not plugin_cls:
        raise ContractError(
            f"strategy_id {strategy_id!r} is already registered to {existing.__name__}"
        )

    _REGISTRY[strategy_id] = plugin_cls
    return plugin_cls


def get_strategy(strategy_id: str) -> type[StrategyPlugin]:
    """Resolve a registered plugin class by ``strategy_id``; fail closed on unknown id.

    Raises :class:`~strategy_core.contract.schema.ContractError` (never ``KeyError``)
    listing the registered ids, so callers fail closed on a single exception type.
    """
    try:
        return _REGISTRY[strategy_id]
    except KeyError:
        raise ContractError(
            f"unknown strategy_id {strategy_id!r}; registered: {sorted(_REGISTRY)}"
        ) from None
