"""``ifvg_smc`` — the IFVG/SMC strategy package (archetype 2).

Layout mirrors ``touch_reversal``: ``section`` (pydantic capture profile),
``records`` (typed research emissions — QL only serializes), ``reducer`` (the
deterministic one-setup FSM), ``labels`` (honest r-relative outcomes via the
shared kernel), ``state`` (cross-day seed), ``replay`` (the ``run_day`` batch
twin QL drives), ``plugin`` (the ``@register``-ed protocol shell).

Side-effect-free by design; import submodules directly. Registration happens
only when ``strategy_core.strategies.ifvg_smc.plugin`` is imported.
"""
