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

- **Active phase:** B — **S-B3a DONE** (the plugin owns the SOLE level fold + the first-touch dedup; the runtime's redundant copies are deleted). **Uncommitted, surfaced for review.** Phase B is complete once S-B3a commits; then Phase C.
- **Next step:** commit S-B3a after review, then C1 (repoint TL `model_registry` onto `strategy_core.contract`).
- **Drift-net status:** **S-B3a DONE (fold-collapse + dedup-into-plugin), byte-identical.** The runtime's `level_state`, `_zones_for_snapshot`, `_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` are DELETED; `RuntimeUpdate.levels` ← `plugin.on_event` return, snapshot/update `zones` ← `plugin.snapshot_zones`, snapshot `levels` ← `plugin.current_levels`, dedup = plugin-owned `_fired_keys`, touches flow back VERBATIM. Proven against the **FROZEN, UNTOUCHED** B3 digests: `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` **2 passed** (3,284,775 trades, 8 reset boundaries — every per-trade `to_dict()` + snapshot byte-identical). Full SC suite **144**; TL acceptance+replay **3**; decision-fn gates **2** (UNCHANGED); ruff clean. 5-agent adversarial verify: **5 PASS (all high confidence)**. Verified 2026-06-09 on the final tree.
- **Last-verified date:** 2026-06-09
- **Note (release, decision 9.6):** TL's SC SHA pin (`backend/pyproject.toml`, currently post-B3 `2fe99e5`) must be bumped again to a commit that includes S-B3a once it lands — TL constructs `StrategyRuntime` (collapsed internals) via `runtime/wiring.py`; the editable/working-tree install already resolves it.
- **B3-prep (PRE-FLIP soak):** the multi-day reset-bracketed real-data coverage authored as a soak (2026-06-09) is now **repurposed into the plugin-path regression** `test_b3_multiday_reset_plugin_regression` (9 days, 8 reset boundaries) vs the frozen digests — see the "Phase B — B3 deviations (flip+delete)" subsection.

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
  committed on TL branch `platform-refactor` (`242c606`). TL imports the NEW SC module
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

### Phase B — B3 PRE-FLIP soak coverage (PREP only; B3 still NOT STARTED — no flip, no deletion)

**Why (gap B2 left):** B2's go-live gate proved flag-ON == flag-OFF per trade on full real
days, but only WITHIN two single continuous streams. It never crossed a reset/restart
boundary — exactly where the W4 lifecycle propagation (`reset` / `set_static_levels` /
`load_prior_day_summary` → plugin) is load-bearing — and two days is thin breadth. Once
B3 deletes the hardwired touch block there is no flag-OFF path left to diff against, so
this proves BOTH the multi-day breadth AND the restart-cycle coverage BEFORE the flip.
This is PRE-FLIP coverage only: the default stays OFF, the hardwired `state.py` touch
block stays, and the redundant level fold (D-B2a) is NOT collapsed.

**New drift-net member:** `validation/test_b3_multiday_reset_parity.py`
(`test_b3_multiday_reset_bracketed_parity`). Reuses the go-live machinery verbatim —
`_read_trades` (real store `Trade-Dashboard/data/databento/NQ/<DATE>/mbp10.parquet`,
front-month, WIRE order) and `_build_runtime` (OFF = `{}` None path; ON = registered
`touch_reversal` plugin via `touch_reversal_kwargs()`). Skips cleanly if the store is
absent or fewer than 7 days resolve.

- **Dates (9 CONSECUTIVE trading days):** 2025-07-10, 2025-07-11, 2025-07-14, 2025-07-15,
  2025-07-16, 2025-07-17, 2025-07-18, 2025-07-21, 2025-07-22. Each day's calendar-prev
  file is present, so the Globex window [prev 18:00 ET, day 18:00 ET) is fully captured;
  the prior-day reseed is sourced from the PRECEDING processed day, which IS the real
  preceding trading day (weekend gaps correct: 07-11 Fri precedes 07-14 Mon).
- **Production-style day roll at EACH boundary (8 boundaries; day 1 is the cold start):**
  `reset()` BOTH runtimes, then reseed BOTH identically via `load_prior_day_summary`
  (PDH/PDL = the preceding processed day's high/low in ticks) + `set_static_levels` (a
  touchable `prior_session_mid` reference) — written through the runtime's lifecycle
  methods, which propagate to the plugin (W4). The bars right after each reset are
  serialized-cross-checked specifically.
- **Driven through `StrategyRuntime.process_event`:** per-trade `ua == ub` (≡
  `ua.to_dict() == ub.to_dict()`, the deterministic serialization) asserted THROUGHOUT,
  plus explicit `to_dict()` cross-checks on every touch-bearing update and on the first
  trade + first decision bar after each reset; per-day and final snapshot equality.
- **W4 across boundaries (white-box):** asserts the plugin's `self._levels` fingerprint ==
  the runtime's `level_state` fingerprint (`_trading_day`/`_day_high`/`_day_low`/`_ranges`/
  `_summaries`/`_static_levels`) right after every reset+reseed AND at each day's end — so
  `self._levels` stays byte-identical across resets, not only at a cold t0.
- **Result:** **2,638,675 trades/runtime (5,277,350 `process_event` calls); OFF==ON
  byte-identical on every trade; 42 touches firing on ALL 9 days (non-vacuous);** plugin
  `self._levels` == runtime `level_state` at all 8 boundaries and 9 day-ends; final
  snapshot equal. Per-day touches: 4/3/6/4/5/4/5/6/5; max zones/day up to 7.

**Flag-ON drift net run (all green, reported by name):**

- Full SC suite (`tests/`, incl. `test_b2_plugin_seam_parity`, `test_b2_wiring`, A3
  `test_touch_reversal_plugin`, the runtime/touch/zone/level golden suite): **145 passed**
  with `SC_PLUGIN_ROUTING=1`; **145 passed** flag-OFF (default) too.
- `tests/test_b2_plugin_seam_parity.py` + `tests/test_b2_wiring.py` +
  `validation/test_b2_golive_runtime_parity.py` + `validation/test_b3_multiday_reset_parity.py`:
  **7 passed** flag-ON.
- TL `tests/test_strategy_core_acceptance.py` + `tests/test_strategy_core_replay_integration.py`:
  **3 passed** flag-ON (routes TL's `StrategyCoreService` through the plugin) AND **3
  passed** flag-OFF.
- Decision-fn gates `validation/test_production_pair_parity.py` +
  `validation/test_decision_diff.py`: **2 passed** flag-ON.
- ruff clean: `ruff check src tests` → All checks passed (the project's lint scope); the
  new test file also passes `ruff check` on its own. (Pre-existing un-linted `validation/`
  harness files are unchanged.)

**Scope guard:** the only working-tree change is the ADDED file
`validation/test_b3_multiday_reset_parity.py`. No tracked source edited; `state.py`'s
hardwired touch block and the `SC_PLUGIN_ROUTING` default OFF are untouched. B3 (flip +
delete) remains the NEXT prompt.

### Phase B — B3 deviations / clarifications (the FLIP + DELETE — irreversible)

B3 made the plugin the SOLE path and deleted the flag-OFF/None path. Because that removes
the on-vs-off comparator, the order was: (1) run the full off-vs-on parity green ONE FINAL
TIME with both paths present (`test_b2_plugin_seam_parity` + `test_b2_wiring` flag-OFF +
go-live + the multi-day soak — **7 passed**); (2) FREEZE a compact regression digest of the
plugin path from that green run (canonical-correct because plugin == None there), off==on
cross-checked on **3,284,775 trades/path**; (3) only then remove.

- **D-B3a (plugin is mandatory; auto-attach).** `StrategyRuntime.__init__` now auto-attaches
  the registered `touch_reversal` plugin + its default section when `plugin is None` (PLAN §7
  B3: "plugin defaults to the registered touch plugin"). The `plugin`/`strategy_section`
  params remain (optional) for explicit injection (forward-looking Phase-E router + tests).
  A fail-LOUD `ValueError` guards the untested non-default-scheme case: the default section is
  `RESEARCH_SESSION_SCHEME`, so a runtime built with a different scheme MUST pass its own
  plugin+section (else `plugin._levels` could silently diverge from `level_state`). Verified
  ALL current call sites (the whole golden suite + production) use the default scheme, so none
  hit the guard. `reset`/`set_static_levels`/`load_prior_day_summary`/`on_event`/`configure`
  are now UNCONDITIONAL (no `if self._plugin is not None`).
- **D-B3b (off-vs-on tests → frozen-digest regressions).** The real-data gates lost their
  comparator, so they are repurposed into plugin-path REGRESSIONS that re-run the plugin path
  and assert against the frozen digests. New `validation/_b3_regression_util.py` (shared
  `SeqDigest` = order-sensitive sha256 over every per-trade `RuntimeUpdate.to_dict()` + touch
  count + final-snapshot sha) + `validation/_fixtures/b3_regression/{golive,multiday}.json`
  (the canonical digests). `test_b2_golive_runtime_parity.py` → `test_b3_golive_plugin_regression`
  (2 days); `test_b3_multiday_reset_parity.py` → `test_b3_multiday_reset_plugin_regression`
  (9 days, 8 reset boundaries, fails-loud if the chain is incomplete). The synthetic
  `test_b2_plugin_seam_parity` → a plugin-path cross-bar first-touch suppression test;
  `test_b2_wiring` keeps kwargs-attaches/auto-attach/lifecycle and RETIRES the
  resolver/kwargs-OFF/W2-empty-registry assertions. **Decision-fn gates
  (`test_production_pair_parity`, `test_decision_diff`) LEFT UNCHANGED** — flag-agnostic, the
  canonical anchor. (Cosmetic debt: the repurposed files keep their `test_b2_*`/`parity`
  filenames; contents/function-names/docstrings updated — a trivial rename is a follow-up.)
- **D-B3c (W2 migration guard retired).** "registry empty on bare `import strategy_core`" was
  a MIGRATION guard; the plugin is now the production strategy and registers when
  `runtime/wiring.py` is imported (runtime construction or TL import) — intended, not a leak.
  (Incidentally `strategy_core/__init__.py` still imports neither `wiring` nor the plugin, so a
  BARE `import strategy_core` leaves the registry empty — but it is no longer load-bearing.)
- **D-B3d (dead-helper removal; out-of-scope KEPT).** Removed `state.py`'s now-unused
  `detect_touches` import and the `_zones_for_detection` helper (exclusive to the deleted None
  block). KEPT exactly as-is (out of scope — they belong to S-B3a): the runtime's own
  `level_state.process_trade` fold, the snapshot premark `_zones_for_snapshot`, the
  `_touched_zone_keys` set + its placement/writes, `_touch_zone_key_from_touch`, `_zone_key`.
- **Cross-repo (TL).** `services/strategy_core_service.py` already constructed via
  `**touch_reversal_kwargs()`; only its stale flag comment was updated. No behavior change.
- **Verification.** A 6-agent adversarial workflow (read-only) checked: removal correctness,
  out-of-scope untouched, flag fully removed (no live-code refs in SC/TL/QL), plugin always
  non-None, regression non-vacuity, and completeness — **5 PASS (high) + 1 FAIL** whose sole
  finding was a stale `TYPE_CHECKING` comment in `state.py` (since fixed). PLAN unmodified.

**STOP point (resolved):** B3 was surfaced for review per the flip+delete prompt, re-verified
green on the final tree (full SC suite 144 + ruff clean + both real-data digest regressions),
and committed as SC `85cb7b6` on `platform-refactor`.

### Phase B — S-B3a deviations / clarifications (fold-collapse + dedup-into-plugin)

S-B3a deleted the runtime's redundant copies (exactly D-B3d's KEPT list) and made the
plugin the sole owner of levels, zones, and the first-touch dedup. Behavior-preservation
is anchored on the FROZEN, UNTOUCHED B3 digest fixtures: both regressions reproduce every
per-trade `RuntimeUpdate.to_dict()` and every snapshot byte-identically (3,284,775 trades,
8 reset boundaries). The decision-tf gate stays RUNTIME-owned (D-B2i untouched); the
auto-attach + fail-loud non-default-scheme guard is code-identical (D-B3a untouched);
`self._touches` (the snapshot's touch accumulator) stays RUNTIME-owned (not level/dedup
state — explicitly out of scope).

- **D-SB3a-a (D-B2b RESOLVED — dedup is PLUGIN-owned, owner-ratified).** The open
  placement decision from D-B2b is closed: the cross-bar dedup moved INTO the plugin as
  `TouchReversalPlugin._fired_keys` — initialized empty in `__init__`, pre-marked AND
  written inside `on_bar_closed` (keys recorded after `detect_touches` via the relocated
  key helper), read by `snapshot_zones`, cleared ONLY in `reset()`. That is the exact
  lifecycle the runtime's deleted `_touched_zone_keys` had: keys are day-scoped, so they
  accumulate across day rolls and clear only on reset; `configure()` deliberately does
  NOT clear them (the old runtime had no analogous re-configure path; configure runs only
  at construction). D-B2b's "FORCED runtime-owned because the snapshot pre-marks off the
  set" constraint is dissolved by D-SB3a-b's snapshot accessor.
- **D-SB3a-b (protocol temporarily carries touch vocabulary).** `StrategyPlugin` gained
  `current_levels() -> tuple[Level, ...]` (mirrors the deleted snapshot read
  `level_state.levels()`) and `snapshot_zones(trading_day: date | None) -> tuple[Zone, ...]`
  (faithful relocation of the deleted `_zones_for_snapshot`: zones from
  `StrategyLevelState.zones()` — the DEFAULT-proximity display derivation, deliberately
  NOT `on_bar_closed`'s section-driven DETECTION derivation; `trading_day is None` →
  unmarked; premark via the shared `zone_key`; returns a tuple where the old helper
  returned a list both call sites tupled — identical payload). Precedent:
  `StrategyStep.touches`/`zones` (D-B2d); the generic plugin-event payload that removes
  the typed `levels`/`zones` fields stays deferred per PLAN §2.1(5).
- **D-SB3a-c (`on_event` return-type change).** `on_event` now returns
  `tuple[Level, ...]` — for a `Trade`, the plugin's full post-fold level set (maps onto
  `RuntimeUpdate.levels` one-for-one with the deleted runtime fold's return,
  `level_state.process_trade`); `()` for a `Quote`. The §2.2 sketch's
  `tuple[SetupState, ...]` return was never consumed (the plugin returned `()` since A3).
- **D-SB3a-d (`already_fired_keys` RETIRED).** Removed from `StrategyPlugin.on_bar_closed`
  (protocol), the plugin implementation, the runtime call site, and both test callers.
  Side effect: direct `on_bar_closed` calls are no longer read-only on dedup state (they
  record into `_fired_keys`) — the intended production semantics; both unit-test callers
  use fresh single-call plugins, so their outputs are unchanged.
- **D-SB3a-e (relocated key helper; `dedup.py` stays).** `_touch_zone_key_from_touch`
  moved VERBATIM (including the defensive fallback tuple) from `StrategyRuntime` into the
  plugin as a `@staticmethod`; the only delta is calling the single-sourced `zone_key`
  directly instead of through the deleted `_zone_key` delegate (same function — I3
  preserved). `decisions/dedup.py` STAYS; its sole consumer is now the plugin (docstrings
  updated to past tense).
- **D-SB3a-f (test edits, enumerated — the complete list).** (1)
  `tests/test_touch_reversal_plugin.py`: the two `on_bar_closed` call sites dropped the
  retired `frozenset()` arg; every assertion unchanged. (2) `tests/test_b2_wiring.py`:
  `test_lifecycle_propagation_keeps_plugin_levels_in_lockstep` →
  `test_lifecycle_propagation_reaches_plugin_state` — the runtime-vs-plugin fingerprint
  lockstep lost its comparator (the runtime fold is deleted), so it now white-box-asserts
  the lifecycle WRITE-THROUGH (seeded summary + static level present in
  `plugin._levels`), `_fired_keys` non-empty after a fired touch, `reset()` clearing BOTH
  (levels cleared + `_fired_keys == set()`), and a re-seeded SAME-day replay re-firing
  (which would be suppressed had reset not cleared the day-scoped dedup). (3)
  `tests/test_runtime_touch_zones.py`: docstring/comment staleness only — no assertion
  changed. (4) `tests/test_b2_plugin_seam_parity.py`: UNCHANGED (drives the public API
  only). The golden runtime suite's observable-behavior assertions are untouched; NO
  non-test consumer needed re-pointing (TL backend + QL grep: zero references to any
  deleted member, public or private).
- **D-SB3a-g (staleness fixes riding the step).** `plugin.py` module docstring rewritten
  off the pre-B3 "registered but NOT constructed by any production path" world; every
  "mirrors state.py:NNN" cross-reference dropped (incl. a stale `(state.py:188)` line
  number); `protocols.py` module header de-staled (Phase-A "declaration-only / nothing
  imports it" framing); `wiring.py`/`section.py`/`dedup.py` docstrings updated off the
  deleted `level_state`/`_zones_for_detection`/shared-set language;
  `tests/test_runtime_touch_zones.py` docstring reworded; the stale untracked
  `__pycache__/config.cpython-313.pyc` deleted. The `test_b2_*` filenames are NOT renamed
  (separate follow-up, already logged in D-B3b).
- **Surfaced by the adversarial verify (recorded, deliberately NOT touched — out of the
  enumerated scope):** (i) `V3_COMPATIBILITY_MATRIX.md:11` is present-tense stale
  ("Runtime level state supports … via `StrategyLevelState`" — the level state is
  plugin-owned now). (ii) The `StrategyPlugin` Protocol does not declare
  `set_static_levels`/`load_prior_day_summary` although the runtime now depends on them
  as the SOLE seed path (gap pre-exists since D-B2j; a future non-touch plugin would
  AttributeError on the lifecycle calls) — protocol addition left to the architect.
  (iii) `StrategyLevelState` still physically lives at `runtime/levels.py` (now
  plugin-imported only; the physical move stays deferred per the ADDITIVE COROLLARY).
  (iv) Out-of-contract edge: an EXPLICIT `plugin=` passed WITHOUT `strategy_section`
  never gets `configure()`, so its level state stays at `__init__` defaults — no such
  call site exists; production always supplies the section (D-B3a guard unchanged).

**STOP point:** S-B3a is complete and green on the final tree but **NOT committed** —
surfaced for review per the S-B3a prompt. The commit SHA will be stamped here on commit.

---

## Status table

| Phase | Step | Goal (short) | Status | Date | Commit | Harnesses passed | Notes/deviations |
|---|---|---|---|---|---|---|---|
| A | A1 | Introduce the StrategyPlugin Protocol + BarSpec/SetupState/DecisionEvent/Barrier types in strategy_core, unused | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; full SC suite 140 passed | New submodule `strategies/protocols.py`; declaration-only, unimported by runtime. D-A1, D-A1b. |
| A | A2 | Introduce the registry (@register + get_strategy(strategy_id)) in strategy_core/strategies/registry.py, empty | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; unwired-invariant check green | §9.1 registry-time assertion (isinstance StrategyPlugin + BarSpec tuple + SectionModel BaseModel); fail-closed get_strategy. Registry stays empty on `import strategy_core`. |
| A | A3 | Author TouchReversalSection SectionModel + a TouchReversalPlugin that wraps the existing functions, registered but not yet wired into the runtime | DONE | 2026-06-08 | `68eef26` | test_touch_reversal_plugin (5 incl. equivalence) + golden suite (12) green | Wraps build_zones→detect_touches verbatim; plugin owns level state (R1); scheme←section (R2, D-A3a); decision tf as config (R3, D-A3b). D-A3c..f. |
| B | B1 | Add an optional plugin param to StrategyRuntime.__init__, defaulting to None; when None, run the exact current state.py:271-280 block | DONE | 2026-06-08 | `1491921` | full SC suite 140 passed (incl. test_runtime_state/touches/touch_zones/levels + A3 test_touch_reversal_plugin); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 passed vs branch SC); GATE test_production_pair_parity + test_duckdb_streaming_parity + test_decision_diff (3 passed, store+alpha_lab present) | None-path byte-identical (inner lines unchanged, +4 indent only); else = no-op `pass` (B2 placeholder); `plugin` added last (no param reorder); StrategyPlugin TYPE_CHECKING-only → registry stays empty. Only runtime/state.py changed. |
| B | B2 | Route _process_trade through plugin.on_bar_closed when a plugin is present, and construct StrategyRuntime with the registered TouchReversalPlugin in a feature-flagged path | DONE | 2026-06-08 | SC `7a5cc96`+`5061163`; TL `242c606` | full SC suite 145; test_b2_plugin_seam_parity (PART1); test_b2_wiring (resolver/W2/W4-lifecycle); GO-LIVE test_b2_golive_runtime_parity (real days 2025-07-15 339997 trades + 2025-07-07 306103 trades, OFF==ON per trade, 5 touches/6 zones); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 OFF + 3 ON); decision-fn gates test_production_pair_parity + test_decision_diff (2 passed); ruff clean | flag SC_PLUGIN_ROUTING default OFF via wiring.touch_reversal_kwargs(); TL StrategyCoreService wired; lifecycle propagation + plugin load_prior_day_summary hook; plugin internal decision-tf gate REMOVED (runtime gates). Deviations D-B2f..k. |
| B | B3 | Make the plugin path the default for strategy_id="touch_reversal"; remove the dead hardwired duplicate only after a full green soak | DONE | 2026-06-09 | `85cb7b6` | pre-removal off-vs-on parity 7 (FINAL green, both paths present); digests frozen (off==on on 3,284,775 trades/path); full SC suite 144; real-data plugin regressions vs frozen digests (golive + multiday) 2; TL acceptance+replay 3; decision-fn gates 2; ruff clean | flip+delete: None path + `SC_PLUGIN_ROUTING`/`config.py` removed; plugin auto-attached (D-B3a, fail-loud non-default-scheme guard); off-vs-on real-data tests repurposed to frozen-digest regressions + seam/wiring converted (D-B3b); W2 guard retired (D-B3c); dead `_zones_for_detection`+`detect_touches` import removed, level_state fold/snapshot/dedup KEPT (D-B3d); fold-collapse + dedup-move SPLIT to S-B3a. 6-agent adversarial verify 5 PASS + 1 stale-comment fixed. |
| (added) | S-B3a | Collapse the redundant runtime level fold (D-B2a) + move the once-per-day `_touched_zone_keys` dedup INTO the plugin + flow the raw `Touch` back onto `RuntimeUpdate.touches` | DONE | 2026-06-09 | pending (uncommitted; surfaced for review) | frozen-digest regressions `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` 2 (fixtures UNTOUCHED; 3,284,775 trades, 8 reset boundaries, byte-identical); full SC suite 144; TL acceptance+replay 3; decision-fn gates 2 (UNCHANGED); ruff clean | runtime `level_state`/`_zones_for_snapshot`/`_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` DELETED; plugin = sole owner (on_event returns the level fold; new `current_levels`/`snapshot_zones` accessors; plugin-owned `_fired_keys`; `already_fired_keys` retired; key helper relocated verbatim); raw `Touch` flow-back verbatim; D-B2b RESOLVED plugin-owned (owner-ratified); D-B2i gate + D-B3a guard untouched. Deviations D-SB3a-a..g. 5-agent adversarial verify 5 PASS (high). the LAST Phase-B tidy, before C; split out of B3's flip+delete prompt (added step, not in plan §7 — per deviation rule) |
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

- **2026-06-09** — Phase B Step **S-B3a landed → S-B3a DONE** (uncommitted, surfaced for review;
  the LAST Phase-B step). One behavior-preserving collapse: the plugin's level state is now the
  SOLE source of levels, zones, and the first-touch dedup — the runtime's redundant copies
  (`self.level_state` + its fold, the snapshot reads + `_zones_for_snapshot` premark,
  `_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` — exactly D-B3d's KEPT list) are
  DELETED. New wiring, each mirroring the exact deleted `StrategyLevelState` call:
  `RuntimeUpdate.levels` ← `plugin.on_event` return (`process_trade`); snapshot/update `zones` ←
  new `plugin.snapshot_zones(trading_day)` (`zones()` + premark, `None` → unmarked); snapshot
  `levels` ← new `plugin.current_levels()` (`levels()`); dedup = plugin-owned `_fired_keys`
  (premark + record inside `on_bar_closed`, cleared only on `reset()`; `already_fired_keys`
  RETIRED from the protocol; key helper relocated verbatim); raw `Touch` flow-back verbatim
  (no re-derivation/re-keying/filtering). D-B2b is RESOLVED plugin-owned (owner-ratified);
  D-B2i (runtime-owned decision-tf gate) and D-B3a (auto-attach + fail-loud guard) untouched;
  `decisions/dedup.py` stays (plugin-consumed only). Staleness fixes rode along (plugin/protocols/
  wiring/section/dedup docstrings, stale config `.pyc`). BYTE-IDENTITY proven on the final tree
  against the FROZEN, UNTOUCHED B3 digests: `test_b3_golive_plugin_regression` +
  `test_b3_multiday_reset_plugin_regression` **2 passed** (3,284,775 trades, 8 reset boundaries,
  every per-trade `to_dict()` + snapshot identical); full SC suite **144**; TL
  `test_strategy_core_acceptance` + `test_strategy_core_replay_integration` **3**; decision-fn
  gates **2** (UNCHANGED); ruff clean. Verified by a 5-agent read-only adversarial workflow
  (removal / sole-source / dedup-equivalence / non-vacuity / completeness — **5 PASS, all high
  confidence**). Deviations **D-SB3a-a..g** + surfaced-deferred items recorded above. PLAN
  unmodified.
- **2026-06-09** — Phase B Step B3 **FLIP + DELETE landed → B3 DONE** (IRREVERSIBLE; committed as
  SC `85cb7b6` on `platform-refactor` after review + a green re-verify of the final tree — full SC
  suite 144 + ruff clean + both real-data digest regressions). The touch strategy now runs ONLY
  through the registered `touch_reversal`
  plugin: deleted the `if self._plugin is None:` hardwired touch block in
  `runtime/state.py._process_trade` (plugin loop + `on_event` now unconditional), made the plugin
  mandatory (auto-attached when not supplied; fail-loud guard for a non-default scheme — D-B3a),
  deleted the `SC_PLUGIN_ROUTING` flag + `strategy_core/config.py` and made
  `runtime/wiring.touch_reversal_kwargs()` unconditional, and removed the dead
  `_zones_for_detection`/`detect_touches` import (D-B3d). The runtime's own `level_state` fold,
  the snapshot premark, and the `_touched_zone_keys` dedup are KEPT — the fold-collapse +
  dedup-into-plugin is split out to **S-B3a** (the last Phase-B tidy). ORDER (one-way door):
  ran the final off-vs-on parity green (**7 passed**) with both paths present, FROZE the canonical
  plugin-path digests from it (off==on cross-checked on **3,284,775 trades/path**), THEN removed;
  the off-vs-on real-data gates are repurposed to plugin-path regressions vs those frozen digests
  (D-B3b), seam→cross-bar, wiring resolver/W2 retired (D-B3c). Plugin-only drift net green: full
  SC suite **144**; `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression`
  **2**; TL `test_strategy_core_acceptance` + `test_strategy_core_replay_integration` **3**;
  decision-fn gates **2** (UNCHANGED); ruff clean. Verified by a 6-agent adversarial workflow
  (5 PASS high-confidence + 1 FAIL = a single stale comment, fixed). PLAN unmodified.
- **2026-06-09** — Phase B **B3 PRE-FLIP soak coverage added** (B3 still **NOT STARTED**;
  **no flip, no deletion** — default stays OFF, the hardwired touch block and the flag-OFF
  path both remain). New drift-net member `validation/test_b3_multiday_reset_parity.py`
  proves flag-ON == flag-OFF byte-identical across **9 consecutive real store days**
  (2025-07-10 → 2025-07-22) **AND 8 reset/restart boundaries** — the W4-across-boundaries
  breadth the 2-day, single-stream B2 go-live gate never reached. Reuses the go-live
  machinery (`_read_trades` + `_build_runtime` via `touch_reversal_kwargs()`, flag toggled
  OFF vs ON); rolls each day production-style (`reset()` + `load_prior_day_summary` PDH/PDL
  from the PRECEDING processed day + `set_static_levels` reference, all propagated to the
  plugin via W4); asserts `ua == ub` per trade through `StrategyRuntime.process_event` plus
  serialized cross-checks on every touch-bearing update and on the first trade/decision-bar
  after each reset; and white-box-asserts the plugin's `self._levels` == the runtime's
  `level_state` at every boundary and each day's end. **2,638,675 trades/runtime
  (5,277,350 process_event calls), 42 touches firing on all 9 days (non-vacuous), OFF==ON
  throughout.** Flag-ON drift net all green: full SC suite **145** (and 145 flag-OFF);
  `test_b2_plugin_seam_parity` + `test_b2_wiring` + go-live + this new test **7**; TL
  `test_strategy_core_acceptance` + `test_strategy_core_replay_integration` **3** ON (and 3
  OFF); decision-fn gates `test_production_pair_parity` + `test_decision_diff` **2**; ruff
  clean (`ruff check src tests`). Only an ADDED test file — no tracked source/plan edits.
- **2026-06-08** — Phase B Step B2 **PART 2 of 2 (WIRE-UP) landed → B2 DONE.** SC `5061163`
  on `platform-refactor`; Trade-Lab `242c606` on TL `platform-refactor`. Adds the SC-owned flag
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
