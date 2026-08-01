# IFVG deterministic context features

Status: implemented and verified locally on 2026-07-31; unpublished and not
consumer-pin aligned.

## Ownership and compatibility

Strategy-Core is the only owner of IFVG context formulas and state. The feature
set is additive measurement evidence and has no reducer feedback path. Enabling
it cannot change v2 setup, candidate, decision, trade, label, or seed identity,
and cannot change eligibility, execution ordering, positions, or orders.

Frozen identities:

- feature set: `ifvg_context_v1`;
- formula: `ifvg_context_formula_v1`;
- record schema: `1`;
- seed/dataset/report container: `3`;
- feature schema hash:
  `2283083597f0b72354ee05976be2dec90fb0404e04ddb853e7ec0c9d83e07181`;
- default context config hash:
  `94b2814108f4a436110666b4ddbda584a6bb055de41be49014e0fa9182b8d12e`;
- 240-minute anchor status: `experimental_q40_open`.

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

Local editable verification does not promote this source. Quant-Lab and
Trade-Lab must retain their existing Strategy-Core pins until this change is
committed, pushed, reviewed, and promoted through the Trade-Lab alignment
runbook. No model training, feature selection, tuning, or evaluation is part of
this implementation.
