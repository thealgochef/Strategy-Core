# IFVG deterministic context features

Source checked: 2026-09-08 against this repository. The identities below describe
the implemented context contract; consumer pins and deployment status require
separate consumer evidence.

## Ownership and compatibility

Strategy-Core is the only owner of IFVG context formulas and state. The feature
set is additive measurement evidence and has no reducer feedback path. Enabling
it cannot change v2 setup, candidate, decision, trade, label, or seed identity,
and cannot change eligibility, execution ordering, positions, or orders.

Frozen identities:

- feature set: `ifvg_context_v1`;
- formula: `ifvg_context_formula_v2`;
- record schema: `2`;
- Core context day-seed container: `3`;
- feature schema hash:
  `5e56063984841b7a8ada99cc36fbccf6c912a09b14b4d5dd50d0bcbf1294cda3`;
- default context config hash:
  `77f6edd45c73de6a2483cee2bc8ecd14654c1168e42f2409577c157f46bca9c3`;
- 240-minute anchor status: `experimental_q40_open`.

The versions, ordered feature registry, schema hash, and
`context_config_hash(ContextFeatureConfig())` are defined in
[`context_config.py`](../src/strategy_core/strategies/ifvg_smc/context_config.py).
The day-seed container version is defined in
[`state.py`](../src/strategy_core/strategies/ifvg_smc/state.py); consumer dataset
and report container versions are separate contracts. Observer capture and
seed validation are implemented in
[`context_features.py`](../src/strategy_core/strategies/ifvg_smc/context_features.py).

Legacy serialized swing, sweep, level-pool, inversion, and IFVG v2 records were
not widened. Confirmed swing evidence and every context record are companion
types. `StrategyStep.context_events` and `RuntimeUpdate.context_events` form a
typed channel separate from flat model features.

## Deterministic bar routing

`StrategyRuntime` constructs a time engine only for plugin-declared TIME
`BarSpec`s and routes by exact `(kind, size)`. Duplicate, empty, or unknown bar
labels fail closed. Tick engines retain their prior behavior.

For a trade that enters a later eligible time bucket:

1. the earlier time bucket is materialized without consuming the later trade;
2. completed TIME bars are ordered by
   `(availability_ts, -duration, bar_id)`;
3. due TIME callbacks run before `plugin.on_event(trade)`; and
4. the existing tick fold and tick callback order then continue unchanged.

This makes `240m -> 60m -> 30m -> 15m -> 10m -> 5m -> 3m -> 1m` the order at a
shared logical close and makes the 1-minute callback last. Batch and streaming
use the same bucket semantics, including maintenance and DST boundaries.

## Context observer

`IfvgContextObserver` has two explicit halves:

- `advance_step(due_htf_bars, bar_1m, new_fvgs)` advances confirmed structure,
  displacement, and equal-level state before the unchanged reducer; and
- `capture(emissions)` records post-reducer transition evidence and exact links.

The observer maintains confirmed structure for 1m, 3m, 5m, 10m, 15m, 30m,
60m, and 240m. The reducer still receives its former collapsed higher-timeframe
input; only the observer sees the complete ordered due-bar sequence.

The emitted records are `ContextStateSnapshot`, `IfvgContextCapture`, market
structure state/delta, displacement window, equal-level lifecycle/member/sweep
records, and validity/provenance evidence. Every record is point-in-time and
carries source availability, warmup status, missing reason, as-of timestamp and
cursor, source timestamps, and formula/config identity.

Displacement uses integer-tick candles and `(B0, end]` windows. Equal-level pools
use bounded same-timeframe membership, median-member representative ticks,
UUIDv5 identity, deterministic capacity eviction, tombstones, and strict shared
sweep/reclaim predicates. Candidate, decision, and executed-trade links use exact
IDs; the trade link is captured from the decision-time `trade_opened` emission.

Active displacement windows retain constant-space sufficient statistics and a
resumable standard SHA-256 compression state, not historical bars or FVG rows.
The optional native block compressor is only an accelerator; the pure-Python
path produces the same digest and remains the correctness fallback. Structure
and equal-level seeds use lossless compact internal projections and reconstruct
the public typed evidence envelope on resume. Equal-level matching, sweep probes,
and nearest-pool reads use derived indexes rebuilt from the canonical seed.

## Seeds, bounds, and consumers

`IfvgContextObserverSeed` wraps the unchanged v2 seed and round-trips all bounded
observer state. Context config/formula/schema mismatches fail closed. The approved
bounds are:

- observer state: at most 5 MiB;
- seed: at most 1 MiB;
- serialized transition: at most 32 KiB;
- completed 1-minute observer step p99: at most 2 ms;
- multi-timeframe callback p99: at most 10 ms; and
- replay slowdown: at most 25 percent.

Quant-Lab consumes the records through a separate v3 normalization path while
replaying v2 emissions solely for parity. Trade-Lab may construct a separate,
disabled-by-default shadow runtime. Neither consumer owns or reimplements a
formula.

## Release boundary

Local source verification does not establish consumer pin compatibility or
promote a deployment. Check each consumer's exact package pin, loaded source,
and compatibility evidence before changing its binding. This documentation
refresh does not assert current Trade-Lab activation or release status.
