# Platform + Strategy-Plugin SDK — Migration PROGRESS (execution log)

This is the **living execution log** for the migration specified in
`docs/PLATFORM_REFACTOR_PLAN.md`. The PLAN is the authoritative spec and must **NOT**
be edited. This PROGRESS doc tracks state, decisions-as-applied, clarifications, and
deviations.

---

## How to update (follow on EVERY step)

- Move each step's **Status** through `NOT STARTED → IN PROGRESS → DONE` (or `BLOCKED`).
- On completing a step, record: **date**, **commit SHA**, **files touched**, the
  **parity/golden harnesses you ACTUALLY RAN and that passed** (by name), and **any
  deviation** from the plan/decisions.
- **NEVER mark a step DONE** unless the harnesses REQUIRED FOR THAT STEP (per PLAN §7)
  are green AND were actually run. If any required harness is red OR could not be run
  (e.g. missing data), set the step **BLOCKED** with the reason and do not proceed.
  Do NOT claim a harness is green that you did not run.
- Keep the **"Current state"** line accurate. Record deviations and clarifications
  **HERE**, never by editing the plan.

---

## Current state

- **Active phase:** B in progress (B2 complete; B3 not started).
- **Next step:** B3.
- **Drift-net status:** B2 DONE. Flag `SC_PLUGIN_ROUTING` (default OFF) wired into the TL production construction via `wiring.touch_reversal_kwargs()`. Flag-ON proven byte-identical to flag-OFF on REAL data (GO-LIVE gate: 2025-07-15 + 2025-07-07, 646K trades, OFF==ON per trade; 5 touches / 6 zones each) AND on the tf=2 TL acceptance + replay (3 OFF + 3 ON); decision-fn gates 2 passed; full SC suite 145; ruff clean; W1–W5 verified by a 5-agent adversarial workflow (all pass, high confidence). Verified 2026-06-08.
- **Last-verified date:** 2026-06-08
- **Note (B3):** B3 flips the default ON after a green soak, deletes the hardwired touch block, and collapses the redundant level fold (D-B2a). Moving the once-per-day `_touched_zone_keys` dedup INTO the plugin + the raw-`Touch` flow-back onto `RuntimeUpdate.touches` is a SEPARATE later step (B3/E), gated by the multi-bar + go-live harnesses that now exist — NOT part of B2. **Release step (decision 9.6):** TL's SC SHA pin (`backend/pyproject.toml`) must be bumped to a commit that includes `strategy_core/runtime/wiring.py` before deploy — TL imports it at module load even flag-OFF; the editable/working-tree install already resolves it.

---

## Decisions ratified (record verbatim)

- **9.1** = Protocol (+registry-time assertion).
- **9.2** = in-package registry module.
- **9.3** = two-axis version (platform_version + per-plugin strategy_version).
- **9.4** = time-bars land in Phase F.
- **9.5** = keep `strategy_core` name, layout `strategy_core/strategies/<id>/`.
- **9.6** = declare+SHA-pin strategy-core in Quant-Lab.
- **9.7** = delete TL's local contract copy.
- **9.8** = Option A (Barrier abstraction + retire TL outcome tracker, lands in the C/D band).
- **9.9** = parameterize the session-name set.
- **9.10** = quote accessor on PlatformContext.

**§3 correction (already in the plan):** Direction (LONG/SHORT) stays PLATFORM; Side
(HIGH/LOW) → touch PLUGIN with Level/Touch; DIRECTION_FROM_SIDE moves to the plugin with
Side (QL emitter sources it from the plugin, not platform constants). Honored when the
move-map executes (Phase B+).

---

## Plan clarifications (authoritative resolutions — recorded here, not in the plan)

The plan has 3 internal inconsistencies; the owner ratified that **the §3.1 move-map
TABLE wins** wherever prose conflicts. These resolutions are authoritative for the
implementation:

- **R1 — LEVEL OWNERSHIP.** §3.1 is authoritative — `StrategyLevelState` is **PLUGIN-owned**,
  configured in `configure(section, ctx)`. §4.1's prose "the level fold stays on the
  PLATFORM side" is OVERRIDDEN. *(Applied: the touch plugin owns `self._levels` and folds
  trades into it via `on_event`.)*
- **R2 — PlatformContext SURFACE.** `PlatformContext` = EXACTLY §2.2 (`tick_size`,
  `point_value`, `closed_bars(label)`, `current_bar(label)`, `trade_price_at(ts)`,
  `session_at(ts)`) PLUS `quotes_in_window(...)` (§9.10). NO levels accessor and NO
  scheme attribute were added. The §4.2 sketch's `ctx.scheme` / `ctx.levels_for(...)` are
  ERRORS: the plugin gets the scheme from `section.session_scheme` and gets levels/zones
  from its OWN `self._levels`, never from `ctx`.
- **R3 — NO NEW CONTRACT FIELDS.** `TouchRule` has no `decision_tf` (verified §4.3 fields:
  type, bar_type, zone_proximity_pts, zone_representative_price, scope,
  direction_from_side). The §4.2 sketch's `touch_rule.decision_tf` is an ERROR. The
  decision timeframe is a construct/config value as today (`state.py:188`:
  `decision_timeframe = decision_timeframe or min(timeframes)`); `required_bars()` returns
  ONE TICK `BarSpec` at that value.
- **ADDITIVE COROLLARY.** Phase A does NOT physically move `StrategyLevelState` (or
  `build_zones`/`detect_touches`/`resolve_outcome`/features) out of their current modules
  — the move happens in the move-map execution (Phase B+). In Phase A the plugin IMPORTS
  the existing symbols from their current locations and instantiates/calls them.
- **Slotting:** 9.10 is implemented in A1 (`PlatformContext.quotes_in_window`). 9.9
  (data-drive the session-name set; drop hardcoded `"asia"`/`"london"` at `levels.py:49`)
  is an ADDED step NOT in PLAN §7 and is NOT part of Phase A (it modifies
  `StrategyLevelState`); it lands when `StrategyLevelState` becomes plugin-owned / as prep
  before Phase F.

### Phase A — additional deviations / clarifications (additive, behavior-preserving)

- **D-A1 (A1):** `StrategyStep` is a concrete `frozen` dataclass (default-constructible to
  an empty delta, per A1's explicit requirement), modelled on `RuntimeUpdate`; §2.2
  sketches it as a `Protocol`, but a Protocol is not constructible.
- **D-A1b (A1):** module is `strategy_core/strategies/protocols.py` (matching A1's stated
  example name); types live in the submodule, not the package `__init__`.
- **D-A3a (A3):** `configure()` converts the section's CONTRACT-form `SessionScheme`
  (string clock times) into the runtime `types.SessionScheme` (`datetime.time` objects)
  before constructing `StrategyLevelState`. The two `SessionScheme` types differ; the
  scheme still ORIGINATES from the section (R2) — only its representation is adapted.
- **D-A3b (A3):** the decision timeframe is held as a module constant
  `_DECISION_TIMEFRAME = DEFAULT_TICK_COUNT` (the engine default min tick-count per
  `state.py:188`), because `required_bars()`/`decision_bar_label()` are `@staticmethod`
  per §2.2; a per-instance configurable decision tf is deferred to wiring (Phase B).
- **D-A3c (A3):** `strategy_version = "1"` is a PLACEHOLDER — NOT load-bearing until
  Phase E splits the version axis (decision 9.3).
- **D-A3d (A3):** the cross-bar first-touch dedup (`_touched_zone_keys`) is NOT replicated
  in the plugin; it is runtime bookkeeping the seam carries in Phase B. A3's single-bar
  equivalence is unaffected (the wrapper mirrors the per-bar `build_zones → detect_touches`
  core exactly).
- **D-A3e (A3):** `touch_reversal/__init__.py` imports the plugin so importing the PACKAGE
  registers it (PLAN §5.2). `strategy_core/__init__.py` and `strategy_core/strategies/__init__.py`
  remain import-free, so NO `import strategy_core` path registers a plugin (verified).
- **D-A3f (A3):** the A3 test file adds 4 companion assertions beyond the required
  equivalence test (non-decision-bar → empty step; registry resolves + fails closed;
  section `extra="forbid"`; declarations match engine constants). As of B2 PART 1 the
  plugin has TWO importers: the A3 test and the B2 seam-parity test (no production path).

### Phase B — deviations / clarifications (B2 PART 1, additive)

- **D-B2a (3b keep-both-folds):** on the plugin path the runtime KEEPS its level fold
  (`level_state.process_trade`, feeding `RuntimeUpdate.levels` + the snapshot) AND adds the
  plugin's `on_event` fold into the plugin's OWN level state (feeding its detection).
  Redundant by design; B3 collapses it once the plugin owns the single fold.
- **D-B2b (dedup stays runtime-owned):** the cross-bar `_touched_zone_keys` set stays the
  RUNTIME's; the plugin only READS it (the new `already_fired_keys` param) to pre-mark its
  zones and never mutates it. FORCED because the end-of-`_process_trade` snapshot pre-marks
  off `_touched_zone_keys` (not only detection), so the platform must own the set. The final
  placement (runtime vs plugin) is the open architect decision (see b2_context.md).
- **D-B2c (single-sourced zone key, I3):** new `strategy_core/decisions/dedup.py` hoists the
  zone-identity key; `StrategyRuntime._zone_key` delegates to it and the plugin pre-marks
  with it, so the two cannot drift.
- **D-B2d:** `StrategyStep` gained `touches`/`zones` (both defaulted; still
  default-constructible); `StrategyPlugin.on_bar_closed` gained `already_fired_keys:
  AbstractSet[ZoneKey]`; new `strategy_core/runtime/context.py` `RuntimePlatformContext`
  (backed by live getters so it survives `reset()`); `StrategyRuntime.__init__` gained a
  trailing `strategy_section` param + builds an inert `self._ctx`. The A3 test's
  `on_bar_closed` calls now pass `frozenset()`. `AbstractSet` is imported as
  `collections.abc.Set as AbstractSet` (the spec's `collections.abc.AbstractSet` does not exist).
- **D-B2e (I4b precondition):** the seam harness pins `section.touch_rule.zone_proximity_pts
  == build_zones' default (ZONE_PROXIMITY_PTS)` — the byte-identity precondition between the
  plugin's section-driven zones and the runtime's default-proximity zones.

**PART 2 (wire) requirements surfaced by PART 1 (must land before flag-on):**

- `StrategyRuntime.reset()` does NOT call `self._plugin.reset()`, and
  `set_static_levels` / `load_prior_day_summary` write only to `self.level_state`, not the
  plugin's `self._plugin._levels`. PART 1's byte-identity is proven only for the no-reset
  streaming path (the seam test seeds the plugin manually). PART 2 MUST wire reset +
  level-seed propagation to the plugin, or the drift net diverges when the construction flag
  flips. (Completeness-critic minor.)
- PART 2 adds the feature flag, production/TL construction through the plugin, and the
  money-path GATE harnesses run flag-on. **→ ALL RESOLVED in PART 2 (below).**

### Phase B — deviations / clarifications (B2 PART 2, additive + cross-repo)

- **D-B2f (the flag — resolver):** `strategy_core/config.py` `plugin_routing_enabled()`,
  env `SC_PLUGIN_ROUTING`, default OFF, truthy `1`/`true`/`yes` (case-insensitive). ONE
  switch, TRANSIENT (deleted at B3). EVERY construction site reads it only through the single
  helper `strategy_core/runtime/wiring.py` `touch_reversal_kwargs()` — which lazily imports the
  plugin module ONLY on the flag-ON branch (so `import strategy_core` leaves the registry
  empty, W2).
- **D-B2g (production wiring):** the ONLY production `StrategyRuntime(` site is Trade-Lab
  `services/strategy_core_service.py` `StrategyCoreService.__init__` — wired via
  `**touch_reversal_kwargs()` (SC validation harnesses + Quant-Lab construct no runtime). Flag
  OFF (default) → `{}` → byte-identical None path (W1).
- **D-B2h (W5 — section matches the runtime):** the runtime's `level_state` uses
  `RESEARCH_SESSION_SCHEME` (default; no scheme passed) + `DEFAULT_TICK_SIZE` (default) + the
  hardcoded asia/london level set, with `decision_timeframe = min(display_timeframes) = 147`
  in production. `default_touch_reversal_section()` round-trips to `RESEARCH_SESSION_SCHEME`
  (via `_contract_scheme_from_runtime`, the inverse of the plugin's `_runtime_scheme_from_section`)
  and pins `touch_rule.zone_proximity_pts == ZONE_PROXIMITY_PTS`; the plugin's `configure` uses
  `ctx.tick_size == runtime.tick_size`. So `self._levels` is built identically to `level_state`.
- **D-B2i (decision-tf gate removal — refines D-A3b):** the plugin's `on_bar_closed` NO LONGER
  self-gates on its declared `_DECISION_TIMEFRAME` (147). The runtime's plugin-path `else` branch
  already gates on `self.decision_timeframe` ONE-FOR-ONE with the None branch, so re-gating on a
  hardcoded 147 would break byte-identity for ANY other `decision_timeframe` (e.g. the tf=2 TL
  acceptance harness). The decision-tf gate is now runtime-owned; `required_bars()` still DECLARES
  147 (advisory). The A3 `test_non_decision_bar` companion was repurposed to assert the new behavior.
- **D-B2j (W4 — lifecycle propagation):** `reset` / `set_static_levels` / `load_prior_day_summary`
  propagate to the plugin (each gated on `if self._plugin is not None:`); new plugin
  `load_prior_day_summary` hook. None path unchanged.
- **D-B2k (cross-repo — Trade-Lab modified):** Phase A's "do not touch TL" no longer applies — B2
  PART 2 wires production. TL `services/strategy_core_service.py` modified (import + `**touch_reversal_kwargs()`),
  committed on TL branch `platform-refactor` (`<b2p2-tl-sha>`). TL imports the NEW SC module
  `runtime/wiring.py` at load even flag-OFF, so TL's SC SHA pin must include it before deploy
  (release step, decision 9.6; the editable branch install resolves it today).

**Go-live gate mapping (reviewable, B2's DONE gate):** dates **2025-07-15** and **2025-07-07**;
harness `validation/test_b2_golive_runtime_parity.py`; **real-store** data
(`Trade-Dashboard/data/databento/NQ/<DATE>/mbp10.parquet`) front-month trades in WIRE order driven
**through `StrategyRuntime.process_event`**; off-vs-on runtimes built via `touch_reversal_kwargs()`
with the flag toggled; per-trade `ua == ub` (≡ `ua.to_dict() == ub.to_dict()`, the deterministic
serialization) + final-snapshot equality; **339,997 + 306,103 trades, OFF==ON throughout**, 5 touches
and 6 max zones/day (PDH/PDL via `load_prior_day_summary` + trade-built asia/london availability-gated
+ merged zones — the breadth the synthetic seam harness did not reach).

---

## Status table

| Phase | Step | Goal (short) | Status | Date | Commit | Harnesses passed | Notes/deviations |
|---|---|---|---|---|---|---|---|
| A | A1 | Introduce the StrategyPlugin Protocol + BarSpec/SetupState/DecisionEvent/Barrier types in strategy_core, unused | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; full SC suite 140 passed | New submodule `strategies/protocols.py`; declaration-only, unimported by runtime. D-A1, D-A1b. |
| A | A2 | Introduce the registry (@register + get_strategy(strategy_id)) in strategy_core/strategies/registry.py, empty | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; unwired-invariant check green | §9.1 registry-time assertion (isinstance StrategyPlugin + BarSpec tuple + SectionModel BaseModel); fail-closed get_strategy. Registry stays empty on `import strategy_core`. |
| A | A3 | Author TouchReversalSection SectionModel + a TouchReversalPlugin that wraps the existing functions, registered but not yet wired into the runtime | DONE | 2026-06-08 | `68eef26` | test_touch_reversal_plugin (5 incl. equivalence) + golden suite (12) green | Wraps build_zones→detect_touches verbatim; plugin owns level state (R1); scheme←section (R2, D-A3a); decision tf as config (R3, D-A3b). D-A3c..f. |
| B | B1 | Add an optional plugin param to StrategyRuntime.__init__, defaulting to None; when None, run the exact current state.py:271-280 block | DONE | 2026-06-08 | `1491921` | full SC suite 140 passed (incl. test_runtime_state/touches/touch_zones/levels + A3 test_touch_reversal_plugin); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 passed vs branch SC); GATE test_production_pair_parity + test_duckdb_streaming_parity + test_decision_diff (3 passed, store+alpha_lab present) | None-path byte-identical (inner lines unchanged, +4 indent only); else = no-op `pass` (B2 placeholder); `plugin` added last (no param reorder); StrategyPlugin TYPE_CHECKING-only → registry stays empty. Only runtime/state.py changed. |
| B | B2 | Route _process_trade through plugin.on_bar_closed when a plugin is present, and construct StrategyRuntime with the registered TouchReversalPlugin in a feature-flagged path | DONE | 2026-06-08 | SC `7a5cc96`+`<b2p2-sc-sha>`; TL `<b2p2-tl-sha>` | full SC suite 145; test_b2_plugin_seam_parity (PART1); test_b2_wiring (resolver/W2/W4-lifecycle); GO-LIVE test_b2_golive_runtime_parity (real days 2025-07-15 339997 trades + 2025-07-07 306103 trades, OFF==ON per trade, 5 touches/6 zones); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 OFF + 3 ON); decision-fn gates test_production_pair_parity + test_decision_diff (2 passed); ruff clean | flag SC_PLUGIN_ROUTING default OFF via wiring.touch_reversal_kwargs(); TL StrategyCoreService wired; lifecycle propagation + plugin load_prior_day_summary hook; plugin internal decision-tf gate REMOVED (runtime gates). Deviations D-B2f..k. |
| B | B3 | Make the plugin path the default for strategy_id="touch_reversal"; remove the dead hardwired duplicate only after a full green soak | NOT STARTED |  |  |  |  |
| C | C1 | Repoint TL model_registry import from the local contract copy to strategy_core.contract, keeping today's flat StrategyContract shape | NOT STARTED |  |  |  |  |
| C | C2 | Delete TL's local strategy_contract.py once nothing imports it | NOT STARTED |  |  |  |  |
| D | D1 | Retire TL's local outcome tracker in favor of the engine's honest decision-time fill | NOT STARTED |  |  |  |  |
| D | D2 | Confirm TL holds no local candle/session/level recompute, then assert it via test | NOT STARTED |  |  |  |  |
| E | E1 | Introduce platform_version alongside ENGINE_VERSION, both stamped, loader fail-closes on either | NOT STARTED |  |  |  |  |
| E | E2 | Add per-plugin strategy_version/strategy_id, fail-closed via registry-lookup equality; turn strategy_id into a router | NOT STARTED |  |  |  |  |
| E | E3 | Decompose the flat StrategyContract into StrategyEnvelope + typed SectionModel; emit from the plugin | NOT STARTED |  |  |  |  |
| F | F1 | Extend the candle data shape with a BarSpec/kind and add CloseReason.INTERVAL, with TICK behavior unchanged | NOT STARTED |  |  |  |  |
| F | F2 | Mirror the TIME close trigger into the vectorized batch path and pin it with a new parity test | NOT STARTED |  |  |  |  |
| F | F3 | Validate archetype 2 (HTF-FVG/iFVG) end-to-end on the same interface as a NEW plugin, behind its own strategy_id | NOT STARTED |  |  |  |  |
| (added) | S9.9 | data-drive session-name set in StrategyLevelState (drop hardcoded asia/london); behavior-preserving; feeds F | NOT STARTED |  |  |  | added step, not in plan §7 — per deviation rule |

---

## Change log (newest first)

- **2026-06-08** — Phase B Step B2 **PART 2 of 2 (WIRE-UP) landed → B2 DONE.** SC `<b2p2-sc-sha>`
  on `platform-refactor`; Trade-Lab `<b2p2-tl-sha>` on TL `platform-refactor`. Adds the SC-owned flag
  `SC_PLUGIN_ROUTING` (default OFF) via `strategy_core/config.py` + the single construction helper
  `strategy_core/runtime/wiring.py` `touch_reversal_kwargs()` (lazy plugin import on the ON branch only);
  wires TL `StrategyCoreService` to construct via `**touch_reversal_kwargs()`; adds `default_touch_reversal_section()`
  (round-trips to RESEARCH, W5); propagates `reset`/`set_static_levels`/`load_prior_day_summary` to the plugin
  (W4, + new plugin `load_prior_day_summary` hook); and REMOVES the plugin's internal decision-tf gate so the
  runtime is the sole gate authority (flag-ON byte-identical at any `decision_timeframe`). Harnesses: full SC
  suite 145; `test_b2_wiring` (resolver/W2/W4); GO-LIVE `test_b2_golive_runtime_parity` (real days 2025-07-15 +
  2025-07-07, 646K trades, OFF==ON through `StrategyRuntime.process_event`); TL `test_strategy_core_acceptance` +
  `test_strategy_core_replay_integration` 3 passed flag-OFF AND 3 passed flag-ON; decision-fn gates
  `test_production_pair_parity` + `test_decision_diff` 2 passed; ruff clean. Verified by a 5-agent adversarial
  workflow (W1–W5 + TL/completeness, all pass, high confidence; one W4 test-strength nit fixed). Default stays OFF;
  the hardwired block is NOT deleted (that is B3).
- **2026-06-08** — Phase B Step B2 **PART 1 of 2 (the plugin SEAM)** landed on `platform-refactor`,
  commit `7a5cc96`. Routes `_process_trade` through `self._plugin.on_bar_closed(bar, ctx,
  already_fired_keys)` when a plugin is present (else branch), folds each trade into the plugin via
  `on_event`, and builds an inert `RuntimePlatformContext`. New `decisions/dedup.py` single-sources the
  cross-bar zone key (I3); `protocols.py` `StrategyStep` += `touches`/`zones` and `on_bar_closed` +=
  `already_fired_keys`; new `runtime/context.py`. Production/TL construction is UNCHANGED (plugin-less →
  None path); the plugin path is reachable only from `tests/test_b2_plugin_seam_parity.py`. None-path
  byte-identical to B1 (I1); registry empty on `import strategy_core` (I2). Harnesses: full SC suite 141
  passed; the multi-bar seam-parity test proves plugin-path == None-path incl. cross-bar first-touch
  suppression (a zone fires once across 3 re-straddling bars); ruff clean. Verified by a 5-agent
  adversarial workflow (I1/I2/I3/I4 + completeness — all pass, high confidence; I4 empirically falsified:
  1 touch with premark vs 3 without). B2 stays IN PROGRESS — PART 2 (wire-up) pending.
- **2026-06-08** — Phase B Step B1 landed on `platform-refactor`, commit `1491921`. Additive
  keyword-only `plugin: StrategyPlugin | None = None` on `StrategyRuntime.__init__` (stored as
  `self._plugin`); the hardwired touch fold in `_process_trade` is wrapped in `if self._plugin is None:`
  (verbatim block, +4 indentation only) with an `else: pass` B2 placeholder. `StrategyPlugin` imported
  TYPE_CHECKING-only so `import strategy_core` still leaves the registry empty. ONLY `runtime/state.py`
  changed. Harnesses: full SC suite 140 passed; None-path tests (test_runtime_state/touches/touch_zones/levels)
  green; TL test_strategy_core_acceptance + test_strategy_core_replay_integration 3 passed vs branch SC;
  GATE test_production_pair_parity + test_duckdb_streaming_parity + test_decision_diff 3 passed (data present);
  ruff clean. Verified by a 4-agent adversarial workflow (all pass, high confidence).
- **2026-06-08** — Phase A (A1–A3) landed on branch `platform-refactor`, commit `68eef26`.
  Additive + unwired plugin SDK: `strategies/protocols.py` (StrategyPlugin/PlatformContext/
  BarSpec/SetupState/DecisionEvent/Barrier/StrategyStep/FeatureSpec/LabelPolicySpec/
  EventTypeSpec), `strategies/registry.py` (@register + get_strategy with the §9.1
  registry-time assertion), `strategies/touch_reversal/` (TouchReversalSection +
  TouchReversalPlugin wrapping build_zones→detect_touches), and `tests/test_touch_reversal_plugin.py`.
  Golden suite (test_runtime_state, test_runtime_touches, test_runtime_touch_zones,
  test_runtime_levels, test_touch, test_zones, test_outcomes, test_features, test_sessions,
  test_honest_entry, test_candle_parity, test_contract) + the A3 equivalence test all green;
  full SC suite 140 passed; ruff clean; unwired-invariant verified (`import strategy_core`
  leaves the registry empty). No protected file modified (state.py:271-280 untouched).
