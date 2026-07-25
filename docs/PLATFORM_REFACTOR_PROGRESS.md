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

- **Active phase:** **Phase E COMPLETE and PUSHED (E1+E2 at the E greenlight; E3 at the E3 greenlight — see the dated bullets below); Phase D COMPLETE and PUSHED** (D1b greenlit 2026-06-10: SC pushed to `2cb27dc`, TL pin chore `5ede158` pushed; decision 9.6 pin convention honored). D-window record: **D1b (flip + delete)** (SC `945f381` + TL `94610ff`): the dashboard now SERVES the streaming honest resolver — resolutions adapt to served `Outcome`s (entry = the real trade print, NEW `entry_price` field; TL-side correctness; SC ZERO-BASED `bars_to_resolution`; `resolved_ts` from the new SC `StreamResolution.resolved_ts_utc`), drops surface explicitly (`prediction.dropped` WS frame + snapshot `dropped` ring + `RuntimeUpdate.dropped` + IntelligencePanel badge w/ reason, NO chart marker), and the legacy `OutcomeTracker` + its 16 tests + the gate-B characterization harness are DELETED; `ResolutionType.SESSION_END`/`NO_RESOLUTION` REMOVED (grep-proven zero refs). Gates: TL suite **419** (= 420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin); seam-by-name **4** (acceptance 3 incl. the D2 guard + replay 1); TL ruff clean; frontend typecheck + vitest **142** + build green; SC suite **152** + ruff + frozen b3 regressions **2** (fixtures untouched). 6-agent adversarial verify on the exact commits: **5 PASS (high) + 1 finding REPAIRED in-window** (the `_track_outcomes` per-item swallow guard). Prior D-window state (D1a DARK SC `c7564fd` + TL `c7f2a84`; D2 TL `73aa7df`) unchanged beneath. Decision 9.6 unchanged (pin DECLARED c615e40; enforcement DEFERRED; QL cold-install debt open).
- **E-WINDOW (E1+E2) DONE and PUSHED at the E greenlight 2026-06-10** (SC `8e5c017` + QL `baecf66` + TL `9b00eb5` on `platform-refactor`, followed by the greenlight chore commits QL `e10d226` + TL `ef8a189` — pin bumps to SC `8e5c017` + CI branch filters — and the SC greenlight doc commit): two-axis versioning live end-to-end. `ENGINE_VERSION` → `PLATFORM_VERSION` (`"strategy_core_platform_v1"`, clean rename, no alias); `CONTRACT_VERSION` → `"trade_lab_contract_v2"` (shape break); contract field `engine_version` → `platform_version` + NEW required `strategy_version`; `strategy_id` re-pointed to the REGISTRY ROUTER KEY. QL emits via `get_strategy` (unknown id fail-closes EMISSION), flips `supported_by_runtime=True` (full contract), and MIGRATED the deployed store in place (3 v3 bundles → v2 w/ backups; the 3 legacy/v1/v2-engine bundles deliberately NOT migrated — see D-E-c); TL gates BOTH registry entries on the platform hook + the 4-check strategy gate (resolve / version-equality / servable-flag / serving-id guard), and `Prediction.contract_id` re-sources to the active bundle id (values byte-compatible). QL CI rider pays the 9.6 debt (cold-install workflow authored; **ENFORCED pending its first green run post-push**); QL tooling aligned py313. REAL-BUNDLE GATE: exactly the 3 migrated bundles discoverable; all 3 activate incl. hot-swap; un-migrated .bak copy rejected on contract_version. Gates: SC **154** + ruff + b3 regressions **2** (fixtures untouched) + decision-fn **2** UNCHANGED; QL **740** (739+1) + ruff (src/tests clean; 13 pre-existing scratch findings stand); TL **424** (419+5) + seam-by-name **4** + ruff + frontend untouched.
- **E3 DONE and PUSHED at the E3 greenlight 2026-06-10** — SC `dc14652` (code) + `06be823` (record) + QL `523ff98` + TL `3d79bc4` on `platform-refactor`, followed by the greenlight chore commits QL `77c5870` + TL `e855aa3` (both pins → SC `dc14652`) and this SC greenlight doc commit. Contract v3 envelope/section split per the ratified consumer classification; loader section hook; QL emits the section from the plugin's SectionModel + migration #2 executed on the real store (3 MIGRATED + 3 SKIP); TL validates the section at both registry entries, threads the typed section to its two section reads, and closes ALL FOUR D-E-h ledger items. 7-lens adversarial verify 7/7 PASS (high; journal `wf_a678b991-e95`), zero in-window repairs. See the E3 deviations (D-E3-a..j) and the status row.
- **Window history (SUPERSEDED as a current-window pointer by the DOC-SYNC STATUS line in §Status, 2026-07-25; retained verbatim as the record of its moment — PROP-SIM, PRESETS and INGEST have all since closed and pushed):** **PROP-SIM** — the barrier-options walker: eval pass-probability from equity paths, TopStep 50K as preset one; QL-side (`alpha_lab.propsim` pure module + CLI, model selection is the first consumer; TL Performance-page presets are a later follow-up) + the OOS-writer per-row outcome columns (max_mfe_pts / max_mae_pts / entry_price / resolution_type on fresh saves); SC receives doc-ops only. (Prior windows QL-UI-PARITY → SEED → WARM-FIX → REPORT → EXEC → COCKPIT → COCKPIT-FIX are ALL GREENLIT + PUSHED — see the POST-E3 records and the pushed annotations; ENV-FIX executed, its QL commit `f247046` rides the PROP-SIM greenlight.) Prior window **QL-UI-PARITY** — make the ML Training Workbench able to train the D-036 bundle (pin-features multiselect, explicit RFECV control, fold-scheme controls); QL-only, UI-wiring only — the training/save core is UNTOUCHED. (The TL visibility half of worklist item 2 was delivered by the W3b land — markers/warm-up/viewport — per the deleted BACKLOG entry rationale.) **2026-07-06: IMPLEMENTED locally (QL `e3ea980`+`44b1327`+`0b4a2e8`); acceptance REQUIRED 4/4 green vs `NQ_W3_20260617T220752Z`, TARGET sha adjudicated as CatBoost run-metadata (model_guid + train_finish_time; 40/2,140,184 bytes) — see §QL-UI-PARITY under POST-E3; NOT pushed.** **Prior window W3 DONE** (PROVE; split **W3a** bundle-build / **W3b** parity gate + falsification) — **W3a bundle REBUILT on the validated vectorized reader (`NQ_W3_20260617T220752Z`, D-036 config); W3b DONE on REDUCED, stress-weighted coverage (D-P-16): 30-day journal base 92/92 + dense 7-day set {12-18, 12-23, 01-20, 01-29, 02-03, 02-12, 02-13} 29/29 at workers=2 AND 4 (per-day rows identical) + 2-day bench 8/8 — HARD-GREEN everywhere, 0 mismatches on every axis, watchdog silent; 12-18 root-caused (harness/runtime terminalization livelock, fixed + regression-tested at both layers — TL `_drive`/`run_window`, SC `f9a1f63`) and 02-12 GREEN on the seeded regen (QL `098e354` guard); the 73-day 236/236 run remains STALE-READER CONSISTENCY evidence only. Reader ADOPTED (D-P-16); land (SC `f9a1f63` + record + TL fix clusters ×3 + pin chores → `f9a1f63`) PUSHED at the 2026-07-06 W3b-land greenlight.** (W2 COMPLETE and PUSHED; pins previously held `256020c`; CI ×3 green; W2-FIX SC `32e9cc0`+`ecbc15e`, TL `df6b2c4` + lint `5a8d28a` recorded.) See POST-E3 §W3b CLOSE. S9.9/F parked.
- **Drift-net status:** **S-B3a DONE (fold-collapse + dedup-into-plugin), byte-identical.** The runtime's `level_state`, `_zones_for_snapshot`, `_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` are DELETED; `RuntimeUpdate.levels` ← `plugin.on_event` return, snapshot/update `zones` ← `plugin.snapshot_zones`, snapshot `levels` ← `plugin.current_levels`, dedup = plugin-owned `_fired_keys`, touches flow back VERBATIM. Proven against the **FROZEN, UNTOUCHED** B3 digests: `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` **2 passed** (3,284,775 trades, 8 reset boundaries — every per-trade `to_dict()` + snapshot byte-identical). Full SC suite **144**; TL acceptance+replay **3**; decision-fn gates **2** (UNCHANGED); ruff clean. 5-agent adversarial verify: **5 PASS (all high confidence)**. Verified 2026-06-09 on the final tree.
- **Last-verified date:** 2026-06-17
- **Note (release, decision 9.6) — AMENDED 2026-06-10 (E3 greenlight):** BOTH consumers pin SC at `dc14652` (the E3 code commit; the E3 doc commits do not move pins). Pin history: TL `cbf9b99 → c615e40` (`0e1c7ce`, C-window) `→ c7564fd` (`4bb9290`, D-window) `→ 945f381` (`5ede158`, D1b greenlight) `→ 8e5c017` (`ef8a189`, E greenlight) `→ dc14652` (`e855aa3`, E3 greenlight); QL `c615e40` (`9b8e798`, declared) `→ 8e5c017` (`e10d226`, E greenlight) `→ dc14652` (`77c5870`, E3 greenlight). PIN CONVENTION unchanged: the pin tracks the latest SC commit with CONSUMER-FACING content; doc-only SC commits do not move it. **STATUS: 9.6 ENFORCED — witnessed 2026-06-10**: QL `ci` run #1 GREEN in 1m27s (cold install 52s resolving the pin anonymously + ruff + 740 tests on a fresh runner) and TL `backend-ci` run #2 GREEN in 51s (cold install 36s + 424 tests). The former NAMED DEBT (QL cold-install resolution check) is CLOSED. **W1 addendum:** both pins `dc14652 → 256020c` at the W1 greenlight (one-surface ingestion — consumer-facing). **W3b-land addendum (2026-07-03; PUSHED at the 2026-07-06 greenlight):** both pins `256020c → f9a1f63` — the W3b-land SC consumer-facing tip: the vectorized reader (`332ad3e` + `37359ae`, the commits this bump finally serves to consumers) plus the `f9a1f63` runtime terminalization liveness fix; the land's SC doc commits do NOT move the pin, per this convention. CI witness: the greenlight `ci`/`backend-ci` runs on the pushed tips (ids at the next doc op — PAID: the SEED greenlight runs on tips containing the land, ids in the SEED close record). **SEED/EXEC addenda (recorded 2026-07-10, COCKPIT P0 doc-op):** both pins `f9a1f63 → 1650327` at the SEED greenlight (2026-07-06; consumer-facing — TL imports `strategy_core.data.prior_day`; ids in the SEED close record) and `1650327 → 3d4193e` at the EXEC greenlight (2026-07-10; the OpenSetupView accessor is consumer-facing — TL `runtime.open_setup_views()` requires `StreamingHonestResolver.open_setups()`; the EXEC SC doc commits do not move the pin). EXEC greenlight CI ids + resolution witness: see the EXEC pushed annotation at the end of this file.
- **B3-prep (PRE-FLIP soak):** the multi-day reset-bracketed real-data coverage authored as a soak (2026-06-09) is now **repurposed into the plugin-path regression** `test_b3_multiday_reset_plugin_regression` (9 days, 8 reset boundaries) vs the frozen digests — see the "Phase B — B3 deviations (flip+delete)" subsection.

---

## Decisions ratified (record verbatim)

- **9.1** = Protocol (+registry-time assertion).
- **9.2** = in-package registry module.
- **9.3** = two-axis version (platform_version + per-plugin strategy_version).
- **9.4** = time-bars land in Phase F.
- **9.5** = keep `strategy_core` name, layout `strategy_core/strategies/<id>/`.
- **9.6** = declare+SHA-pin strategy-core in Quant-Lab. Pin DECLARED 2026-06-09 (QL `9b8e798`, `c615e40…`, byte-identical to TL's pin form; `requires-python` rider `>=3.14` → `>=3.13`, see D-9.6a); enforcement deferred at declaration — dev resolves SC via the editable install. **AMENDED 2026-06-10 (E3 greenlight): ENFORCED — witnessed 2026-06-10.** QL's cold-install workflow (`.github/workflows/ci.yml`, the E-window rider, D-E-f) paid the named debt and its first run is GREEN (run #1, 1m27s: cold install 52s resolving the pin anonymously + ruff + 740 tests on a fresh runner); TL `backend-ci` run #2 GREEN (51s: cold install 36s + 424 tests). See the dated release note in Current state for the full pin history (now → `dc14652`, E3 greenlight).
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
  harness files are unchanged.) [scope note 2026-06-13: clean under `ruff check src tests`; repo-root config-faithful run shows 47 errors confined to validation/ (audit F32); resolution rides W2's CI work.]

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

**STOP point (resolved):** S-B3a was surfaced for review per the S-B3a prompt, greenlit
against the exact reviewed bytes (byte-identical diff comparison at commit time), and
committed as SC `f6e9be8` on `platform-refactor`.

### Post-Phase-B tidy — S-B3b deviations (protocol seed path + drift-net renames + doc de-stale)

S-B3b closes three recorded debts: S-B3a adversarial-verify items (i) and (ii), and
D-B3b's cosmetic filename debt. No runtime/plugin behavior change; the frozen digest
fixtures are untouched. TL/QL untouched — the TL pin bump is deliberately DEFERRED to C1
(S-B3b has no TL-facing change; the editable install resolves the working tree).

- **D-SB3b-a (protocol declares the seed path — closes verify item ii).** `StrategyPlugin`
  gained `set_static_levels(levels)` and `load_prior_day_summary(trading_day, *,
  high_ticks, low_ticks)` in the lifecycle section, mirroring the touch plugin's
  signatures exactly — the SOLE level-seed path since S-B3a (W4/D-B2j). Because the
  Protocol is `@runtime_checkable`, the §9.1 registry-time assertion now also requires
  these methods at registration — deliberate strengthening: a future plugin missing the
  seed hooks fails at `@register`, not with an `AttributeError` mid-session. The touch
  plugin already implements both (since B2 PART 2 / D-B2j).
- **D-SB3b-b (drift-net renames — closes D-B3b's cosmetic debt).** `git mv`, contents/
  function names/assertions UNCHANGED:
  `tests/test_b2_wiring.py` → `tests/test_plugin_wiring.py`;
  `tests/test_b2_plugin_seam_parity.py` → `tests/test_plugin_cross_bar_suppression.py`;
  `validation/test_b2_golive_runtime_parity.py` → `validation/test_b3_golive_plugin_regression.py`;
  `validation/test_b3_multiday_reset_parity.py` → `validation/test_b3_multiday_reset_plugin_regression.py`.
  Living references updated (the complete set, from a 3-repo grep): the `Run:/pytest:`
  docstring self-hints in both renamed validation files, and the multiday file's LIVE
  cross-import (`from test_b3_golive_plugin_regression import DATA_DIR, TICK_SIZE,
  _build_runtime, _read_trades` — previously the old golive module name). Historical
  PROGRESS/change-log mentions left untouched (they are the record); TL's untracked
  `test.md` scratch note left untouched; QL has zero references; no CI/script references
  exist in any repo.
- **D-SB3b-c (V3 matrix de-stale — closes verify item i).** `V3_COMPATIBILITY_MATRIX.md`
  PDH/PDL row reworded to the post-S-B3a reality: level state is plugin-owned
  (`StrategyLevelState` under the `touch_reversal` plugin); the runtime seeds it through
  its lifecycle methods and reads levels/zones back via the plugin accessors.

### Phase C — C1+C2 deviations / clarifications (cross-repo) + decision 9.6 implementation

C1 and C2 landed as ONE TL commit (`0e1c7ce`): the C2 deletion is safe only with C1's
repoint in place, and the C1 tree was never meant to exist with the local copy still
importable. SC CODE is untouched this window (record-only commit). Engine gate semantics
were the load-bearing recon fact: SC's loader performs NO engine check on a bare call
(opt-in `expected_engine_version` hook, checked after `contract_version`, BEFORE
`model_validate`), whereas TL's deleted local loader bound inline whenever the field was
present and loaded legacy no-field contracts "unbound" with a warning.

- **D-C1a (hook at BOTH loader entries — refines the prompt's call-shape).** The task named
  `model_registry._load_contract` (activation) as the hook site; recon found `model_registry`
  has TWO loader entries into contracts — `_describe_bundle` (DISCOVERY, :135) and
  `_load_contract` (activation, :286) — and the real-store v2-class bundle
  (`NQ_20260602_232808`, `engine_version='strategy_core_engine_v2'`) is SCHEMA-VALID under SC,
  so a hookless discovery would have LISTED it (the old local loader engine-bound inside
  discovery too). The hook is wired at BOTH entries:
  `load_strategy_contract(..., expected_engine_version=ENGINE_VERSION)` with `ENGINE_VERSION`
  imported from `strategy_core` (single-sourced, no literal). Adversarial bypass hunt: zero
  other paths in `backend/src` turn strategy.json bytes into a `StrategyContract`.
- **D-C1b (legacy loads-unbound RETIRED — owner-ratified).** A contract with ABSENT
  engine_version now fails closed twice over: the hook rejects it
  (`unsupported engine_version None; expected 'strategy_core_engine_v3'`) and SC's schema
  requires the field anyway. Real-store effect (proven through the registry): the legacy
  `NQ_20260405_…iterations800_depth4` bundle — the ONLY previously-activatable one — is now
  rejected; discovery yields EXACTLY the 3 v3 bundles (`NQ_20260603_233847`,
  `NQ_20260604_012623`, `NQ_20260604_015413`), all 3 activate end-to-end (CatBoost load +
  feature-name validation + hot-swap; checksum step no-op — no sidecars exist in the store),
  and v1/v2/legacy fail with `ModelValidationError` wrapping the engine-hook `ContractError`.
- **D-C1c (import surface).** Package-root imports everywhere: `from strategy_core import
  CONTRACT_VERSION / ENGINE_VERSION / ContractError / StrategyContract /
  load_strategy_contract` (all root-exported; SC `CONTRACT_VERSION` is the SAME string
  `"trade_lab_contract_v1"` TL's local copy used, so no fixture version change). No submodule
  fallback was needed: TL imports neither `LabelPolicy` nor `DECISION_OFFSET_MINUTES` (the
  only names not root-exported). `feature_functions.py`'s TYPE_CHECKING deep import
  (`trade_lab.domain.contracts.strategy_contract`) likewise → package root.
- **D-C1d (test/assertion edits — the complete list).** (1)
  `tests/test_engine_version_binding.py` REWRITTEN to the hook call shape (the registry's
  exact production shape): `test_matching_engine_version_loads` passes
  `expected_engine_version=strategy_core.ENGINE_VERSION` (assertions unchanged);
  `test_mismatched_engine_version_fails_closed` uses the v2-style literal
  `"strategy_core_engine_v2"` (was `"strategy_core_engine_v0_does_not_match"`) + the hook
  (assertion unchanged: `ContractError` match `"engine_version"`);
  `test_legacy_bundle_without_engine_version_still_loads` (asserted loads + `engine_version is
  None`) → `test_absent_engine_version_fails_closed` (asserts `ContractError` match
  `"engine_version"` via the hook) — the loads-unbound regression is retired WITH the behavior.
  Module docstring rewritten. (2) `tests/test_strategy_contract.py`: import repoint ONLY —
  ZERO assertion changes; all error-string matches (`unsupported contract_version`,
  `invalid strategy contract`, `not valid JSON`) hold verbatim because SC's loader was ported
  from TL's (run-verified, not assumed). (3) `test_inference_engine.py` /
  `test_outcome_tracker.py` / `test_feature_functions.py`: import repoints only; nothing else
  forced. Suite count integrity: 435 passed + 1 skip BEFORE and AFTER (the skip =
  `test_benchmark_smoke.py:35`, requires `--run-benchmark`, pre-existing).
- **D-C1e (fixture regeneration — minimal).** `backend/tests/fixtures/strategy.json` gained
  EXACTLY two keys (git diff: +2/−0): top-level `"engine_version": "strategy_core_engine_v3"`
  and `label_policy.decision_offset_minutes: 5` (= SC `constants.DECISION_OFFSET_MINUTES`,
  itself `DEFAULT_INTERACTION_WINDOW_MINUTES`). Validation forced nothing else
  (`research_session_experiment` is Optional; `contract_version` unchanged per D-C1c).
- **D-C1f (before-state CORRECTION — probe-verified, amended 2026-06-09).** The C-window
  recon's framing of "3 activatable v3 bundles (pre-C1)" was WRONG. Probe (temporary TL
  worktree at `be90af3`, the pre-C1 LOCAL loader
  `trade_lab.domain.contracts.strategy_contract.load_strategy_contract`, real store, run
  2026-06-09): all 3 v3 bundles FAIL with `ContractError` → pydantic `extra_forbidden` on
  `label_policy.decision_offset_minutes` (the old schema lacks the field, `extra="forbid"`);
  legacy `NQ_20260405_…iterations800_depth4` loads UNBOUND ("strategy contract has no
  engine_version; loading unbound against strategy_core_engine_v3" warning); v1
  `NQ_20260602_184719` rejected on the engine binding (`unsupported engine_version
  'strategy_core_engine_v1'`); v2 `NQ_20260602_232808` rejected on SCHEMA
  (`decision_offset_minutes` extra_forbidden — the old loader ran `model_validate` BEFORE its
  engine bind, so v2 never reached the engine check). The exact set TL could serve at
  `be90af3` = **{legacy, UNBOUND}** only. TRUE C1 behavior change: the served set **FLIPPED**
  {legacy-unbound} → {3× v3} — it was NOT trimmed from a v3-capable superset. (D-C1b's "the
  ONLY previously-activatable one" phrasing is consistent and now probe-proven.)
- **D-C2a (deletion).** `git rm` of `domain/contracts/strategy_contract.py` + `__init__.py`;
  emptied directory (+ gitignored `__pycache__`) removed from disk. Full-repo grep
  (`domain.contracts` / `domain/contracts` / `strategy_contract`, all import/path forms):
  ZERO live hits — remaining mentions are historical docs/plans prose
  (`docs/inference-integration-plan.md`, `docs/SESSION-HANDOFF-2026-05-30.md`, `plans/*.md`)
  + the untracked `BASELINE_REPORT.md`/`test.md`, left as record.
- **D-9.6a (QL pin implementation detail).** QL `pyproject.toml` `[project].dependencies` +=
  the pin line byte-identical to TL's form (HTTPS git URL + full 40-char SHA `c615e40e…`);
  setuptools accepts direct references without extra config (TL needed
  `hatch.metadata.allow-direct-references`; QL does not). The editable/`PYTHONPATH=src`
  resolution STAYS for dev — the pin is the cold-install declaration. RIDER:
  `requires-python` `">=3.14"` → `">=3.13"` (the working interpreter is 3.13.1; `py --list`
  shows NO 3.14 on the machine). QL-side debt recorded, deliberately NOT touched (outside the
  enumerated scope): the two script `sys.path` hacks (`scripts/phase8_1_golden.py:32-36`,
  `scripts/run_databento_acceptance.py:147-149`), and — surfaced by the adversarial verify —
  `[tool.ruff] target-version = "py314"` + `[tool.mypy] python_version = "3.14"` now lag the
  relaxed `requires-python`, and QL's `.python-version` file still says `3.14.5`. AMENDED
  2026-06-09: the pin is DECLARED, not ENFORCED — nothing currently exercises it; NAMED DEBT:
  QL cold-install resolution check (the analog of TL's cold-install CI) — required to make
  9.6 enforced rather than declared. [stale claim — superseded by E-window CI work]
- **Surfaced by the adversarial verify (recorded, deliberately NOT touched):** (i)
  `test_inference_engine.py:451` bare-loads a real bundle's strategy.json — safe ONLY because
  the same test activates that bundle through the gated registry first; if the activation step
  were removed, the bare load would accept an engine-drifted bundle. (ii) TL
  `backend/pyproject.toml:14` declares `httpx2>=2.3` (pre-existing, unusual package name —
  flagged for the owner, possibly intended `httpx`). **AMENDED (D-window probe): RESOLVED —
  correct AND load-bearing.** Cold CI resolves starlette 1.x whose testclient imports
  `httpx2 as httpx` (verified against the starlette 1.2.1 wheel + the passing cold-CI run);
  zero direct imports anywhere in TL; sole consumers are the 5 TestClient test files; the
  local env is stale (starlette 0.52.1 + plain httpx), so local probes mislead. Moved to the
  dev extra in the D2 commit (CI installs `.[dev]`, backend-ci.yml:37).

### Phase D — D1a deviations / clarifications (streaming honest resolver, DARK)

Ratified design implemented exactly: live scoring adopts batch honest semantics (entry =
realistic trade print at the decision instant; registration drops {flatten, cutoff}; {no_fill,
no_forward}; unresolved-at-cutoff → no_resolution drop). SESSION_END classification dies at
D1b, NOT this window — zero WS/DTO/frontend changes. bars_to_resolution: the new path is SC
batch 0-based; gate A compares raw, gate B normalizes the tracker's 1-based count.

- **D-D1a-a (output shapes).** `StreamDrop.reason ∈ {flatten, cutoff, no_fill, no_forward,
  no_resolution}` — the four `HonestEntryDrop` arms PLUS the streaming terminal arm; the
  no_resolution drop carries the 4dp extremes + `bars_to_resolution=-1`, mirroring the batch
  `OutcomeResult` no_resolution arm byte-for-byte. Resolutions are emitted as
  `StreamResolution` envelopes (key + decision_ts + ENTRY price + the intact kernel
  `OutcomeResult`) — the serving consumer and both gates need the fill the excursions were
  anchored on. Root-exported: `StreamingHonestResolver`, `StreamResolution`, `StreamDrop`.
- **D-D1a-b (caller contract).** `register()` MUST be invoked at-or-after the setup's decision
  instant (the ring only holds what has printed). Production satisfies this STRUCTURALLY:
  predictions register at observation expiry (= touch + the same 5-minute window); the gate-A
  harness registers a pending touch on the first trade at/after its decision instant, with
  post-loop registration for decisions landing in the 17:00–18:00 print-less halt (those drop
  flatten/cutoff identically to batch — no entry query reached). [CORRECTION 2026-06-13: overstated — equality of contract offset and config window was enforced by a log warning only (audit F13); the W1 refusal gate now refuses the mismatch.]
- **D-D1a-c (bar-inclusion rule — gate-A arbitrated).** Every closed bar of the forward
  timeframe the caller feeds is a candidate — INCLUDING END_OF_DAY partials — exactly as the
  batch path consumes its `day_bars` list; membership is decided ONLY by the strict
  `(decision_ts, trading-day 17:00 ET)` close-instant bounds. On the real store partials are
  unreachable in practice (they freeze at the 18:00 ET roll, after the cutoff that
  strictly upper-bounds every window). Documented in the module docstring.
- **D-D1a-d (cutoff signal).** Prints halt AT the 17:00 ET cutoff, so the finalizing signal
  can never arrive as a same-trading-day forward bar close: a bar closing at/after a setup's
  cutoff finalizes it WITHOUT contributing its range (batch bound is strictly
  `close < cutoff`), and the explicit `flush(now_ts)` finalizes by absolute cutoff instant —
  TL live relies on the next session's bars crossing the ABSOLUTE cutoff datetime; the gate-A
  harness flushes at each day's 18:00 ET window end (asserts `open_count == 0` after).
- **D-D1a-e (ring/accessor).** `StrategyRuntime` keeps a bounded `(ts, price>0)` deque fed in
  `_process_trade` — retention 2× the 30-min lookback, the EXACT 30-min bound enforced at
  query time (never by eviction); cleared on `reset()`. `price>0` is the ratified live
  analogue of the reference query's `bid/ask>0` parquet row-validity predicate
  (`decision_diff_harness.py:594-616`). `RuntimePlatformContext.trade_price_at` is now backed
  by the ring via a live getter; **`quotes_in_window` STAYS a stub** (§9.10 retention window
  open — named debt). The b3 frozen digests reproduce byte-identically on the
  ring-instrumented runtime (the ring touches no emitted value).
- **D-D1a-f (TL forced test adaptation — enumerated).** 5 pre-existing tests
  (`test_inference_api.py` ×2 via `_runtime_app_with_active_model`,
  `test_inference_engine.py` ×3 via `_runtime_with_engine`) activated the REAL 147t contract
  on `tick_timeframes=(2,)` — exactly the silent-never-resolve hole the new fail-loud
  activation validation closes, so they now fail loud by design. Helpers changed to
  `(2, 147)`; the 2t decision bar still drives their touch flow (decision timeframe pins to
  `min()`); ZERO assertion changes. [CORRECTION 2026-06-13: overstated — the failure 500s after the registry swap; torn state, not a rejection (audit F12); atomic activation scheduled in W2.]
- **D-D1a-g (gate-A reference).** The batch `trade_price_at` reference is implemented over the
  SAME front-month print set `_read_trades` feeds the runtime (most recent `ts <= as_of`
  within 30 min, binary-searched) — isolating the mechanism comparison (incremental ring vs
  whole-day random access); the bid/ask>0 ≙ price>0 mapping is documented in the gate file.
  Params both sides = the engine constants (tp 15 / sl 30 / trap 5 / offset 5).
- **D-D1a-h (gate-B scope).** Trades-only, live-like CONTINUOUS replay (no per-day reset) with
  the real bundle `NQ_20260604_015413` (label_policy tp15/sl15/trap5/147t/17:00) activated
  through the registry: quote-dependent approach features are NaN (model_native policy), and
  the no-reset level evolution yields 29 predictions vs the reset-bracketed gate-A roll's 42
  touches — both counts honest, different configurations. HEADLINES: 29/29 resolved on both
  paths (zero SESSION_END this window); entry Δ (trade print − level price) mean −20.5 ticks,
  mean |Δ| **55.6 ticks**, max |Δ| 226; **6 label changes** (5× old sl_hit → new
  tradeable_reversal; 1× tp_hit → blowthrough; 1× tp_hit→trap; net old 15 tp/14 sl → new 18
  tradeable/8 blowthrough/3 trap); **5/29 correctness flips**; bars_to_resolution deltas
  spread −72..+12 (entry anchor changes when barriers trip).
- **D-D1a-i (rider).** The gate-B harness file's lint debt (unused noqa / int cast / long
  lines) was fixed in the D2 commit — TL's ruff project scope includes `validation/`, missed
  at the D1a commit.
- **D-D1a-j (post-review terminal-path unit coverage — greenlight addendum).** New SC
  `tests/test_streaming_resolver.py` (synthetic, 7 tests) pins exactly the arms the gate-A
  window never exercised: registration cutoff drop at the NON-STRICT 17:00 ET boundary
  (flatten pushed aside, mirroring `test_honest_entry`'s cutoff arm); flatten at the EXACT
  16:40:00 ET boundary (non-strict); no_fill; no_forward via `flush` (entry carried);
  no_resolution via `flush` (4dp extremes + `bars_to_resolution=-1`); no_resolution via
  `on_bar` where the finalizing bar closes at the cutoff with a both-barriers range —
  asserting that bar contributed NOTHING to the extremes (the strict `close < cutoff`
  window); and the StrategyRuntime trade-ring edges (30-min lookback bound exact; a print
  beyond the 60-min retention is EVICTED — a query that would have matched it inside its
  own lookback returns None). NOTE for D1b: TL's dark wiring imports the private
  `_parse_bar_type` from `outcome_tracker` — that helper needs a new home when D1b deletes
  the tracker.

### Phase D — D2 deviations / clarifications (shadow-engine deletion + guard)

- **D-D2-a (deleted inventory).** `domain/candles.py`: `CandleEngine` (:103-192),
  `_MutableCandle` (:35-94, incl. the already-dead `from_trade`), `CandleUpdate` (:97-100)
  DELETED; KEPT `Candle`, `CandleCloseReason`, `make_bar_id` (live importers:
  runtime/service/seed/dto/outcome_tracker). `domain/levels.py`: `SessionLevelEngine`
  (:118-311), `_SessionRange`, `_DaySummary`, `LevelUpdate`, `SESSION_LEVELS`, `LEVEL_ORIGIN`
  DELETED; KEPT `LevelKind`, `LevelDirection`, `DisplayLevel`, `TouchEvent` (live importers:
  observations/service/runtime/dto). `domain/sessions.py` NOT deleted — production-reached
  via `seed.py` (named debt below). Deleted TESTS (24 collected): `test_benchmark_smoke.py`
  whole file (2 — orphans the `--run-benchmark` conftest hook, harmless; removes the suite's
  standing 1-skip); `test_prices_sessions_candles.py` 6 CandleEngine tests (14 engine-free
  survive); `test_levels_observations.py` 14 SessionLevelEngine tests (the
  ObservationEngine-guard test survives); `test_seed.py` 2 (bar-id collision +
  vectorized-builder-vs-engine parity).
- **D-D2-b (guard strengthening).** New
  `test_deleted_shadow_engines_stay_deleted_across_backend_src`: bans the six deleted names
  across ALL of `backend/src` (any reintroduction fails), confines `SessionClassifier` to
  `sessions.py` + the `seed.py` carve-out, and pins `domain/candles` + `domain/levels` to
  their DTO-only public surface. Carve-outs documented IN the test docstring: `seed.py`
  warm-up builder (display-only; Chicago-clock divergence = named debt), the tracker's
  cutoff math (dies at D1b), `strategy_core_service.py:316-325` display-flag re-derivation.
  The stale `SessionLevelEngine` comment in `adapters/synthetic_replay.py:58` was reworded
  (it would have tripped the token scan); the kept modules' docstrings deliberately avoid
  the literal engine names for the same reason.
- **D-D2-c (oracle losses — recorded).** Deleting the engines removed (1) the ONLY parity
  cross-check of the production seed builder `build_tick_bars_from_frame` (the engine WAS
  its oracle — `test_vectorized_builder_matches_candle_engine`) and (2) the live-side
  generator of the seed bar-id non-collision check. The builder keeps its 6 functional
  tests; re-anchoring it against SC's batch builder (engine-locked by
  `test_candle_parity`) is a candidate follow-up, NOT done this window (scope).
- **NAMED DEBTS (Phase D):** (1) `seed.py` Chicago-clock session math diverges from SC's ET
  scheme (18:00 CT vs 18:00 ET trading-day boundary) — display-only warm-up, guard
  carve-out; (2) the `Barrier` Protocol cannot reach `trap_mfe_min` (kind + 2 price methods
  only) — fix at E3; (3) §9.10 `quotes_in_window` retention window open (stub stays); (4)
  the orphaned `--run-benchmark` conftest hook; (5) QL cold-install resolution check
  (carried from the C-window, unchanged). INFORMATIONAL: the repo test fixture keeps the
  synthetic policy (tp15/**sl30**/16:15) while the deployed bundle carries
  tp15/**sl15**/17:00 — tests deliberately keep the synthetic policy; recorded, not changed.
  **AMENDED at D1b:** the D2 guard's `outcome_tracker.py` docstring carve-out (the
  tracker's cutoff wall-clock math, "dies WITH the tracker at D1b") is **RETIRED on
  schedule** — the tracker is deleted and the bullet removed; the guard's scan code never
  carved the tracker out, so no code change.

### Phase D — D1b deviations / clarifications (flip + delete: serve the honest resolver, retire the tracker)

Ratified semantics implemented exactly: full honest alignment — the dashboard serves the
D1a streaming resolver's outcomes; drops are surfaced explicitly with reasons;
SESSION_END classification retires; entry is the real trade print. The legacy
`OutcomeTracker` is DELETED. SC PART 1 (`945f381`) is additive; TL PART 2 (`94610ff`) is
the flip.

- **D-D1b-a (SC `resolved_ts_utc` + the documented asymmetry).** `StreamResolution`
  gained `resolved_ts_utc` (the RESOLVING bar's `close_ts_utc`, stamped in `on_bar`).
  DELIBERATE ASYMMETRY, documented in the `StreamResolution` docstring: the kernel batch
  `OutcomeResult` carries NO timestamp (a batch caller indexes `bars_to_resolution` into
  the `day_bars` list it already holds; the timestamp is the envelope's concern). Gate A
  cannot arbitrate the field against batch, so it is PINNED in
  `tests/test_streaming_resolver.py`. CLARIFICATION vs the prompt's "extend the
  resolution-path test": that file had NO resolution-path test (gate A owned resolutions;
  the D-D1a-j tests pin terminal arms only), so one was **ADDED**
  (`test_resolution_carries_the_resolving_bars_close_instant` — also pins
  label/entry/decision_ts/zero-based bars on the same emission). Gate A verified
  field-read-only (never constructs `StreamResolution`, never compares whole dataclasses);
  no other construction site exists in SC/TL/QL.
- **D-D1b-b (the adapter + `parse_bar_type`'s new home).** NEW
  `services/inference/resolution_adapter.py` (TL) — placed in `services/inference/` rather
  than beside `outcome_to_dto` (api/dto.py) because the runtime consumes it to build
  DOMAIN objects; api/ importing into the hot path would invert layering. Mapping table
  (ratified): `tradeable_reversal → TP_HIT`; `aggressive_blowthrough → SL_HIT`;
  `trap_reversal → SL_HIT`; an unmapped label fails LOUD (`ValueError`), so a future
  4th engine label must be mapped deliberately. `correct = (result.label ==
  prediction.predicted_class)` computed TL-side (SC stays correctness-free).
  `_parse_bar_type` RELOCATED here VERBATIM (regex + strip().lower() + ValueError message
  intact) as **public `parse_bar_type`** — its sole src consumer is the resolver build
  (`runtime._build_honest_resolver`); parse unit tests kept alive in
  `tests/test_resolution_adapter.py` (2 accept forms + 5 reject cases).
- **D-D1b-c (bars semantics + entry price — SERVED SHAPE CHANGE).** `bars_to_resolution`
  is now the SC ZERO-BASED index of the resolving bar within the forward window; the
  retired tracker served a 1-based bar count (gate B normalized old−1 for comparison —
  same fact, now documented in `domain/outcomes.py` + the adapter). `Outcome`/`OutcomeDTO`
  gained `entry_price` (ADDITIVE) — the honest decision-time fill the excursions were
  anchored on, replacing the tracker's level-price anchor (which was never surfaced).
- **D-D1b-d (the drop surface).** New domain `DroppedPrediction` {prediction_id,
  touch_id, reason, decision_ts_utc, entry_price?} + `DroppedPredictionDTO`; WS frame
  `prediction.dropped` with payload `{"dropped": {…}}` (mirrors `prediction.resolved`'s
  `{"outcome": {…}}` wrapper); snapshot gains a `dropped` ring beside `outcomes` (SAME
  cap, `outcome_limit=500`); `RuntimeUpdate.dropped` (+ `has_deltas`); replay
  `_coalesce_replay_updates` accumulates it event-style (the audit-#N4 rule). Reason
  vocabulary = the SC `StreamDrop.reason` arms verbatim: registration {flatten, cutoff,
  no_fill} (entry None — never queried/no fill) + terminal {no_forward, no_resolution}
  (entry carried). Frontend: `MessageType` + DTO + `normalizeDropped` + store ring (cap
  100, de-dupe by prediction id, cleared on reset/clear) + per-prediction annotation
  (`prediction.dropped`, parallel to `prediction.outcome`) + IntelligencePanel `dropped`
  badge with the reason; drops NEVER enter `prediction.outcome`, so
  `normalizeOutcomeMarkers` produces no chart marker by construction.
- **D-D1b-e (runtime rewiring).** `_track_outcomes` serves resolver emissions through the
  adapter (resolutions → outcomes ring + `prediction.resolved`; terminal drops → dropped
  ring + `prediction.dropped`); registration-time drops from `_register_prediction` (ex
  `_register_dark` — same touch anchors, same fail-loud missing-anchor ValueError, same
  swallow-on-exception posture) ride the same `RuntimeUpdate`. New `_open_predictions`
  map (prediction_id → `Prediction`) correlates resolver keys back to predictions —
  populated on live registration, popped on emission, cleared in LOCKSTEP with
  `resolver.reset()` (reset / hot-swap / clear_predictions); an emission with no open
  prediction logs a warning and is skipped (lifecycle-bug guard, hot path never breaks).
  The dark ring, `dark_outcomes` property, `_append_dark`, and `_build_outcome_tracker`
  are DELETED — the resolver IS the serving path. **VERIFY-DRIVEN REPAIR (in-window):**
  the first cut guarded only `resolver.on_bar`, leaving the per-emission consumption
  (pop → adapt → ring-append) unguarded — a failing adaptation (e.g. the adapter's
  deliberate fail-loud arm, or a stale-pin AttributeError on a cold install) would have
  escaped the hot path and orphaned same-loop ring-appended drops off the
  `RuntimeUpdate`, contradicting the docstring's swallow invariant. Repaired with a
  PER-ITEM guard (a failing adaptation loses only that emission, logged; the bar's other
  emissions, the drops already collected, and the trade event all survive) and PINNED by
  `test_failing_adaptation_never_breaks_the_hot_path` (monkeypatched adapter raise →
  nothing propagates, loss logged, subsequent trades process).
- **D-D1b-f (ResolutionType TRIM — REMOVED).** `SESSION_END` and `NO_RESOLUTION` members
  REMOVED. Grep proof (backend/src + backend/tests + frontend/src, post-flip): zero
  references — the producers/consumers were exactly the deleted tracker, its deleted
  tests, and the deleted gate-B harness. Surviving string hits are unrelated: the contract
  key `label_policy.no_resolution_dropped` (fixture), the `StreamDrop.reason`
  "no_resolution" vocabulary (a drop reason, not a resolution type), and the adapter
  test's use of "session_end" as an example UNMAPPED label.
- **D-D1b-g (gate-B harness RETIRED — deleted).** `validation/d1_characterization_harness.py`
  deleted: its comparison subject (the tracker) is gone, and a single-path repoint would
  count resolver events while characterizing nothing. `backend/D1_CHARACTERIZATION.md`
  (untracked export) + git history are the record. `backend/validation/` is now empty and
  gone; TL's ruff invocation drops it from scope.
- **D-D1b-h (test accounting — the complete assertion-change enumeration).**
  (1) `tests/test_outcome_tracker.py` DELETED (−16) — every assertion tested the retired
  tracker/classification. (2) `tests/test_dark_honest_resolver.py` → git mv →
  `tests/test_honest_resolver_serving.py` (7 → 7, rewritten to the served surfaces):
  dark-ring assertions → outcomes/dropped ring + `RuntimeUpdate`/snapshot assertions;
  tracker-parallel assertions dropped WITH the tracker; the isolation test now asserts the
  dark surfaces are GONE + served streams stay domain-typed; includes the drop-frame
  END-TO-END test (flatten registration drop → `prediction.dropped` WS envelope) and the
  0-BASED-BARS-SERVED pin (first in-window bar resolves at index 0; the tracker would have
  served 1). (3) NEW `tests/test_resolution_adapter.py` (+13): mapping table ×3 labels,
  correctness both directions, fail-loud unmapped label, outcome-id uniqueness, drop
  mapping ×2, `parse_bar_type` ×2 accept + 5 reject. (4) `tests/test_inference_api.py`:
  the synthesized `Outcome` gains `entry_price` (construction would fail without it); the
  resolved-payload test ADDS a full key-set pin incl. `entry_price` (the old test asserted
  DTO round-trip equality only); NEW `test_dropped_prediction_envelope_validates` (+1).
  (5) `tests/test_api_contract.py`: both snapshot key-set assertions + the empty-snapshot
  key-set gain `"dropped"`; new `dropped == []` empty assertion. (6)
  `tests/test_strategy_core_acceptance.py`: docstring bullet removal ONLY — zero assertion
  changes. (7) Frontend: fixture builders gain the new required fields
  (`entryPrice`/`entry_price`, `dropped: null`) in viewModels/ChartWorkspace/
  IntelligencePanel/stores/client/normalize tests; `normalize.test.ts`'s full-equality
  `normalizeOutcome` expectation gains `entryPrice`; +5 new tests (store annotate/cap ×2,
  client route ×1, panel badge ×1, normalize ×1); the clear-test also asserts `dropped`
  clears. (8) +1 NEW `test_failing_adaptation_never_breaks_the_hot_path` (the
  verify-driven swallow pin, D-D1b-e). **Suite math: TL 420 → 419 = −16 +13 +1 +1 (dark
  file 7→8); frontend 137 → 142.**
- **D-D1b-i (adversarial-verify record + informational findings).** 6-agent read-only
  verify on the exact local commits: flip-correctness **FAIL → REPAIRED in-window**
  (the per-item guard, D-D1b-e — the other 5 lenses and the FAIL's own sweep verified
  registration semantics, lockstep, no-double-serve, caps, surfaces, deletion totality,
  adapter fidelity, frontend, and scope all clean at high confidence). INFORMATIONAL
  (recorded, deliberately NOT changed): (i) `StreamingHonestResolver.flush()` has no TL
  src caller — setups still open at a replay day-end / session shutdown are cleared by
  `reset()` without emitting their `no_forward`/`no_resolution` drops; LIVE continuity is
  unaffected (the next session's bars cross the ABSOLUTE cutoff and finalize via
  `on_bar`, exactly D-D1a-d's design), so this is an end-of-stream drop-GENERATION gap,
  not a transport gap — candidate flush hook at replay completion, future window. (ii)
  The frontend snapshot-with-drops seeding path is code-verified but not test-covered
  (the only snapshot fixture omits `dropped`; reconnect-to-older-backend clears stale
  drops via `?? []` — verified by reading). (iii) The cold-install pin reachability is
  the PIN NOTE above.

### Phase E — E1/E2 deviations / clarifications (two-axis versioning + registry router gate; cross-repo, 3 commits)

Ratified design implemented: CONTRACT v2 shape break; `ENGINE_VERSION` →
`PLATFORM_VERSION` (clean rename, no alias); contract `engine_version` →
`platform_version` + NEW required `strategy_version`; `strategy_id` = the registry
ROUTER KEY; `supported_by_runtime` becomes meaningful (QL writes True, TL refuses
False); deployed-bundle migration in scope; `contract_id` stamping re-sourced.

- **D-E-a (the axis rename, SC `8e5c017`).** `PLATFORM_VERSION = "strategy_core_platform_v1"`
  (the engine v1/v2/v3 lineage recorded as superseded history in the doc-comment);
  `CONTRACT_VERSION = "trade_lab_contract_v2"`; schema field renamed (same constraints) +
  `strategy_version: str` (1..64) required; loader hook `expected_engine_version` →
  `expected_platform_version` (same position/None-skip; error strings name the platform
  axis); plugin `strategy_version = "1"` UNCHANGED in value, its placeholder comment
  rewritten to load-bearing (stamped by QL, equality-checked by TL). Every recon-enumerated
  reference updated (tests, validation banners, doc-comments). +2 SC negatives (v1
  contract_version rejected at the FIRST check; missing strategy_version rejected).
- **D-E-b (QL emitter routes through the registry).** `build_strategy_contract` resolves
  `strategy_version = get_strategy(strategy_id).strategy_version` — an unknown id
  fail-closes EMISSION (an unroutable contract is never written); the explicit
  `strategy_core.strategies.touch_reversal` registration import precedes it (the registry
  is deliberately empty on a bare `import strategy_core`, D-B3c). The caller
  (`ml_training_tab.py`) passes `"touch_reversal"`, NOT `output_dir.name`; the dir name
  stays the bundle identity everywhere else. `dataset_config_hash` input renames
  `engine_version=` → `platform_version=` — cache tags ROLL by design (the axis is a hash
  input). FLAG SCOPE CLARIFICATION: `supported_by_runtime=True` applies to the FULL
  contract; the minimal non-`dashboard_utility` record stays `False` (schema-incomplete by
  design — it cannot load, so it must not advertise servability).
- **D-E-c (deployed-store migration — DELIBERATE NARROWING, the window's one design
  correction).** `scripts/migrate_contracts_v2.py` (idempotent, in-place,
  `strategy.json.pre_v2.bak` backups, sidecar regeneration branch — no-op, no sidecars
  exist) EXECUTED against the real store. The store held **6** bundles, not 3: legacy
  (no engine_version), engine-v1, engine-v2, and the 3 engine-v3. The prompt's rewrite
  spec (stamp `platform_v1` on every bundle) would have FORGED the structural binding for
  the v1/v2-engine bundles — the v2-engine bundle is SC-schema-valid (D-C1a) and would
  have ACTIVATED under semantics it was not built with, and discovery would have listed
  >3 (breaking the real-bundle gate's own acceptance). The first run did exactly that;
  it was caught, all 6 restored from backups, and the script corrected: ONLY
  `engine_version == "strategy_core_engine_v3"` bundles migrate (the platform axis
  RENAMES engine v3); non-v3 bundles stay at contract v1, fail-closed at the loader's
  first check — the same rejection class they had pre-E. Final run: 3 MIGRATED
  {v2, platform_v1, touch_reversal, strategy_version "1"} + 3 SKIP(not-migratable);
  re-run: 6 SKIP (idempotent). Per-bundle before/after output in the window report.
  NOTE: all 6 on-disk bundles carried `supported_by_runtime: true` pre-migration
  (including the never-True-emitting era — the A3 recon's "patched outside QL code"
  observation re-confirmed); migration left the flag as-is per spec.
  `models/NQ_20260603_233847/strategy.json` is git-TRACKED in QL (pre-dates the
  `models/` gitignore) — its migration is committed (`git add -f`); the other two live
  untracked on disk.
- **D-E-d (TL router gate, `9b00eb5`).** Both `model_registry` entries pass
  `expected_platform_version=PLATFORM_VERSION` (the D-C1a both-entries precedent). NEW
  shared `_strategy_binding_error`: (i) `get_strategy(contract.strategy_id)` — TL's first,
  intended import of the SC strategy registry (explicit registration import alongside);
  (ii) `plugin.strategy_version == contract.strategy_version`; (iii)
  `supported_by_runtime is True`. Discovery skips with a precise warning; activation
  raises `ModelValidationError` between contract load and model load. Check (iv): NEW
  `ModelRegistry(serving_strategy_id=…)` ctor param — production `app.py` passes the
  runtime service's wired plugin id (NEW `StrategyCoreService.plugin_strategy_id`/
  `plugin_strategy_version` properties); a registry-valid contract routed to another
  strategy is refused. The hardcoded wiring stays, now guarded.
- **D-E-e (stamping source).** `Prediction.contract_id` = `active.model_id` (the bundle
  dir name), not `contract.strategy_id` (now the shared router key). Byte-compatible with
  pre-E observed values (the contract previously restated the bundle name); pinned by
  test. UI-VISIBLE VALUE CHANGE (shape unchanged): `ModelStatus`/`ModelBundle`
  `strategy_id` DTO values become `"touch_reversal"` for migrated bundles (previously the
  dir name); per-bundle identity remains `model_id`. Report-key rename:
  `strategy_core_engine_version` → `strategy_core_platform_version` (both
  `strategy_core_service` sites: snapshot metadata + the feed-status mapper);
  `StrategyCoreService.engine_version` property → `platform_version`.
- **D-E-f (QL CI rider — 9.6 status change).** NEW `.github/workflows/ci.yml` mirroring
  TL's `backend-ci.yml` (py3.13, cold `pip install -e ".[dev]"` resolving the SC pin
  anonymously, `ruff check src tests`, `pytest -q`). 9.6: **DECLARED → ENFORCED pending
  the first green run**, which structurally requires the greenlight pin bump + push (the
  committed pin `c615e40` predates `PLATFORM_VERSION`; stated in the workflow file).
  Tooling alignment riders: ruff `py314`→`py313`, mypy `3.14`→`3.13`, `.python-version`
  → `3.13.1`. The two recorded `sys.path` debt items deliberately untouched.
- **D-E-g (test churn, enumerated — the complete list).** SC: `test_contract.py` fixture
  + assertions to the new axes, 2 renamed tests (matching/mismatch → platform), +2 new
  negatives; `test_databento_live_source.py` asserts the platform prefix. QL:
  `nodrift` — structural map gains `platform_version` (constant) + `strategy_version`
  (registry-sourced), fixture id → `touch_reversal`, `test_engine_version_is_stamped` →
  `test_platform_version_is_stamped`, `test_engine_version_is_v3` →
  `test_platform_version_is_v1_and_strategy_axis_is_registry_sourced` (+ flag True), NEW
  `test_unknown_strategy_id_fails_emission_closed`, loader round-trip + mismatch tests →
  the platform hook, the axis-boundary test now uses the RETIRED engine literal as the
  mismatch case; `repoint` — ids → `touch_reversal`,
  `…advertises_runtime_activation_blocked` → `…advertises_runtime_servable` (False→True;
  minimal record stays False with the rationale in-test), stamp/round-trip → platform;
  `acceptance_cli` — fixture → v2 shape, summary keys
  (`engine_version`→`platform_version` + new id/version keys), the flag-rejection test
  INVERTS (False now rejected, match string `supported_by_runtime=true`). TL:
  `test_engine_version_binding.py` → git mv `test_platform_version_binding.py`, 3 tests
  re-axised + 5 NEW negatives (v1-rejected, unknown-id at discovery AND activation,
  version-mismatch at both, unservable at both, serving-guard); `test_strategy_contract`
  unsupported-version literal v2→v1 (v2 is now the supported shape);
  `test_inference_engine` contract_id pin `startswith("NQ_")` → `== "good-model"`;
  `test_strategy_core_dependency` → PLATFORM_VERSION; `tests/fixtures/strategy.json` →
  v2 shape incl. the recon-flagged `mid_price_source` drift fix (`top_of_book` →
  `trade_price`, the emitter's value). **Suite math: SC 152→154 (+2); QL 739→740 (+1);
  TL 419→424 (+5).**
- **D-E-h (RECORDED-NOT-CHANGED — assigned to the E3 ledger).** (i) activation never
  consults discovery's `validation_ok` (covered near-equivalently by the model-binary
  feature check); (ii) checksum verification is sidecar-optional (silently skipped when
  absent — and the store has none); (iii) `ModelStatus.validation_ok` is hardcoded True
  for any active model; (iv) the section-default `forward_bar_type="tick"`
  (`section.py:131,153`) vs TL's `^(\d+)t$` `parse_bar_type` would REJECT a
  section-defaulted contract — plus the `closed_window` contract↔runtime scheme
  round-trip gap (`section.py:91-93`). All four are E3-band hardening items.
  **AMENDED at E3: ALL FOUR CLOSED** — see D-E3-g below.

### Phase E — E3 deviations / clarifications (envelope/section split, contract v3; cross-repo, 3 commits)

Ratified design implemented: classification by CONSUMER — platform-consumed fields
stay flat on the ENVELOPE (`contract_version`/`platform_version`/`strategy_id`/
`strategy_version`/`training_mode`/`supported_by_runtime`/`instrument`/`tick_size`/
`point_value`/`model`/`class_map`/`feature_set` SHELL (names/order_is_contractual/
nan_policy)/`label_policy` (+ NEW `barrier_mode`)/`inference`/`data_requirements`/
`provenance`); plugin-consumed fields move into ONE `section` subtree typed by the
plugin's `SectionModel` (`session_scheme`/`level_scheme`/`touch_rule`/
`feature_windows`/`research_session_experiment` + the interaction/approach feature
partition MOVED out of `feature_set`). `CONTRACT_VERSION` → `"trade_lab_contract_v3"`
(shape break #2, same fail-closed-at-first-check + in-place-migration pattern as v2).
E3 is BEHAVIOR-PRESERVING: the runtime still configures from wiring constants
(`default_touch_reversal_section()`); bundle sections are consumed only where their
fields were consumed before; the E2 serving guard (check iv) stays.

- **D-E3-a (the classification table as applied).** Envelope/section assignment is
  exactly the ratified list above. `label_policy` and `inference` are ENVELOPE
  (TL's resolver build `runtime.py:_build_honest_resolver` and the inference gate
  consume them — platform reads), so `TouchReversalSection` LOST its Phase-A
  `label_policy`/`inference` fields and GAINED `interaction_features`/
  `approach_features`. The partition validator moved with the partition: the
  section-LOCAL check (disjoint + duplicate-free) is a `model_validator` on
  `TouchReversalSection`; the envelope cross-check (partition == `feature_set.names`)
  is the new single-sourced `validate_feature_partition` helper, run at the TWO
  validation sites — QL emission and TL activation.
- **D-E3-b (the loader carrier, defined precisely).** New opt-in loader kwarg
  `validate_section_via_registry: bool = False`. When True, after envelope
  validation: `get_strategy(contract.strategy_id)` (fail-closed; the §9.1
  registry-time SectionModel assertion is now LOAD-BEARING) →
  `SectionModel.model_validate(section)` → the typed instance is attached to the
  returned contract as the private NON-FIELD attribute `_section_model`
  (`PrivateAttr`, settable on the frozen model) and read via the
  `StrategyContract.section_model` property. A `(contract, typed_section)` tuple
  return was ratified OUT; the loader keeps its plain single-return call shape, and
  reading `section_model` on a hooklessly loaded contract raises `ContractError`
  (fail closed — an unvalidated section is never handed back as typed). The
  registry import is LAZY inside the hook branch (the loader stays import-light;
  callers own the plugin-registration import, D-B3c).
- **D-E3-c (closed_window placement — interpretation recorded).** The prompt's
  "contract SessionWindow gains OPTIONAL closed_window" is implemented as the
  contract **SessionScheme** gaining `closed_window: SessionWindow | None = None`
  (the start/end PAIR is carried AS a SessionWindow; `crosses_midnight` is not
  meaningful for it and stays False) — the runtime `types.SessionScheme.closed_window`
  is scheme-level, so a per-window field could not express the CT scheme.
  `_contract_scheme_from_runtime` / `_runtime_scheme_from_section` are now
  drop-nothing BOTH directions; the `TRADE_LAB_CT_SESSION_SCHEME` round-trip
  (16:00–18:00 closed window) is pinned by `test_session_scheme_round_trips_drop_nothing`.
- **D-E3-d (the forward_bar_type landmine death — refines the prompt's wording).**
  `label_policy` left the section, so the section default no longer carries ANY
  `forward_bar_type` — the D-E-h(iv) landmine died by the MOVE, not by an edit. The
  surviving `"tick"` literal in the section default (`touch_rule.bar_type`) was
  fixed to the canonical production bar literal `f"{DEFAULT_TICK_COUNT}t"` ("147t",
  constant-sourced). The envelope's `forward_bar_type` has no SC-side default at
  all: the QL emitter sources it per-run (`du.bar_type`, production "147t").
- **D-E3-e (emission re-sourcing + recorded wire-shape facts).** QL's emitter
  builds a configured `TouchReversalSection` INSTANCE (`_build_touch_reversal_section`):
  the plugin's `default_touch_reversal_section()` supplies every structural value;
  ONLY per-run config is overridden (`du.bar_type`, the two windows,
  `level_proximity_pts`, the selected feature partition, the session-experiment
  scope); `section_instance.model_dump(mode="json", exclude_none=True)` IS the
  emitted subtree, and `barrier_mode` is sourced from the PLUGIN's `label_policy()`
  declaration. Two recorded projections: (1) `direction_from_side` keeps the shipped
  lowercase `low->long/high->short` form (still sourced from `DIRECTION_FROM_SIDE`;
  the plugin default's uppercase enum-value form is a cosmetic divergence,
  unconsumed by the plugin); (2) newly-emitted session blocks carry
  `crosses_midnight` ALWAYS (model_dump), while pre-E3 emission omitted it when
  False and MIGRATED bundles keep their old block shape verbatim — all three forms
  are SectionModel-identical after validation. [OVERTURNED 2026-06-13 by cold audit: §3 was violated on both halves — map in platform constants, emitter re-deriving and discarding the plugin value. Original text preserved above per supersession rules. REPAIRED in W1 P2c/P4c: constant removed, plugin owns the lowercase wire vocabulary, emitter ships it verbatim.]
- **D-E3-f (migration #2).** `scripts/migrate_contracts_v3.py`, same proven
  pattern, with D-E-c's narrowing applied UP FRONT: ONLY
  `contract_version == "trade_lab_contract_v2"` bundles migrate; the store's
  legacy/v1 bundles SKIP with precise reasons and stay fail-closed at the loader's
  first check. Backups `strategy.json.pre_v3.bak` (never overwritten); restructure
  preserves kept fields byte-for-byte (five section fields + the feature_set
  partition moved verbatim; `barrier_mode: "fixed_points"` injected after
  `resolution`; `section` appended last); idempotent. EXECUTED against the real
  store: **3 MIGRATED** (`NQ_20260603_233847`/`NQ_20260604_012623`/`NQ_20260604_015413`)
  **+ 3 SKIP** (not migratable); re-run **6 SKIP**. All 3 migrated bundles re-load
  through the SC loader WITH the section hook + partition cross-check. The
  git-tracked `NQ_20260603_233847/strategy.json` migration is committed.
- **D-E3-g (the four D-E-h ledger items CLOSED).** (a) TL activation now runs the
  metadata cross-check FAIL-CLOSED (`_validate_against_metadata` → raise
  `ModelValidationError` on mismatch); (b) checksum sidecar ABSENT →
  `logger.warning` (was silent; fired visibly on all 3 real-store activations —
  the store still has no sidecars); (c) `ModelStatus.validation_ok`/`_detail` =
  the active bundle's REAL activation-time result carried on `ActiveModel` (no
  longer hardcoded True); (iv) closed by D-E3-c + D-E3-d. NOTE on the Phase-D
  Barrier debt: `barrier_mode` gives the CONTRACT a binding for the barrier
  interpretation ("fixed_points"|"r_relative", enum-constrained, default
  fixed_points; sourced from the plugin's declaration at emission) — the
  PROTOCOL-level gap (the `Barrier` Protocol cannot reach `trap_mfe_min`) is NOT
  in E3 scope and stays a named debt. [CORRECTION 2026-06-13: the field bound nothing — no consumer read it (audit F20); the W1 gate refuses non-fixed_points until a real consumer exists.]
- **D-E3-h (KNOWN TL COUPLING — recorded, deliberately accepted).** Generic TL
  code duck-types touch-section attributes: `model_registry` imports the touch
  section's `validate_feature_partition`; `inference_engine._direction_from_section`
  reads `section.touch_rule.direction_from_side`; `feature_functions` reads
  `section.feature_windows`. Acceptable single-strategy behavior; the F-era cleanup
  moves these reads into the plugin.
- **D-E3-i (test churn, enumerated — the complete list).** SC: `test_contract.py`
  fixture → v3 envelope+section (strategy_id = the real router key); v1-rejection
  test re-targeted v2; RETIRED `test_feature_set_names_not_union_raises` (the
  FeatureSet validator moved); `test_feature_set_validator_independently` →
  `test_section_partition_duplicates_rejected`; +8 new (missing-section, hook
  positive carrier, section_model-without-hook fails, section unknown-key rejected
  + hookless still loads, section missing-group rejected, unknown strategy_id at
  the hook, partition cross-check, barrier_mode enum); `test_touch_reversal_plugin.py`
  section fixture drops label_policy/inference + gains the partition; +1 round-trip
  pin. **SC 154 → 162.** QL: `nodrift` — structural map drops the section-bound
  leaves + gains plugin-sourced `label_policy.barrier_mode`; allowlist drops the 7
  section-bound entries; coverage guard gains the `_PLUGIN_SECTION_FIELDS` source
  (+ stale/pairwise-disjoint checks); section-bound reads → `contract["section"]`;
  loader round-trips run the section hook and read `section_model`; +2 new
  (section-sourcing honesty incl. the partition cross-check; emission fail-closed
  on partition mismatch). `repoint` — section-bound reads repointed; round-trip
  reads `section_model`. `acceptance_cli` — `bar_type` + research-scope reads →
  the section subtree; fixture hand-migrated v3. **QL 740 → 742.** TL: fixture
  hand-migrated v3 (values byte-preserved; `barrier_mode` added;
  `forward_bar_type` stays "147t"); `test_strategy_contract` — the
  all-sections parse test loads hook-on and reads `section_model`; unsupported
  literal v1 → v2; the feature_set partition-mismatch loader negative →
  the section-hook rejection; `test_feature_functions` — fixture loads hook-on,
  section threaded through `LevelContext.from_contract`/`build_feature_vector`
  (signature change: both now take the typed section);
  `test_platform_version_binding` +4 new (invalid section at discovery AND
  activation; partition cross-check mismatch at activation; metadata mismatch
  rejected at activation; missing sidecar warns on the real activation path);
  `test_inference_engine` +1 (typed section + real validation result on
  ActiveModel). **TL 424 → 429.**
- **D-E3-j (REAL-BUNDLE GATE, post-migration — verbatim in the window report).**
  Discovery lists EXACTLY the 3 migrated bundles (the legacy/v1 bundles skip on
  contract_version v1, the v2-era backup-shaped contract on v2); all 3 ACTIVATE
  sequentially (= hot-swap) with typed `TouchReversalSection`s (bar_type 147t;
  per-bundle partitions 2+3 / 3+3 / 3+2), real validation results, and the new
  sidecar-absent warnings; an un-migrated v2 `.bak` copy (temp-dir probe) is
  skipped at discovery and REJECTED at activation on
  `unsupported contract_version 'trade_lab_contract_v2'`.

**Ledger additions (recorded at the E3 greenlight):** (i) F-era SC touch
candidate — normalize the section default's `direction_from_side` to the
lowercase wire form, killing the last emitter restatement (the recorded
cosmetic divergence, D-E3-e). (ii) Maintenance note — GitHub's Node-20
deprecation on `actions/checkout@v4` + `setup-python@v5` in BOTH CI workflows;
bump majors when available, non-urgent.

## Status table

| Phase | Step | Goal (short) | Status | Date | Commit | Harnesses passed | Notes/deviations |
|---|---|---|---|---|---|---|---|
| A | A1 | Introduce the StrategyPlugin Protocol + BarSpec/SetupState/DecisionEvent/Barrier types in strategy_core, unused | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; full SC suite 140 passed | New submodule `strategies/protocols.py`; declaration-only, unimported by runtime. D-A1, D-A1b. |
| A | A2 | Introduce the registry (@register + get_strategy(strategy_id)) in strategy_core/strategies/registry.py, empty | DONE | 2026-06-08 | `68eef26` | golden suite (12) + A3 test all green; unwired-invariant check green | §9.1 registry-time assertion (isinstance StrategyPlugin + BarSpec tuple + SectionModel BaseModel); fail-closed get_strategy. Registry stays empty on `import strategy_core`. |
| A | A3 | Author TouchReversalSection SectionModel + a TouchReversalPlugin that wraps the existing functions, registered but not yet wired into the runtime | DONE | 2026-06-08 | `68eef26` | test_touch_reversal_plugin (5 incl. equivalence) + golden suite (12) green | Wraps build_zones→detect_touches verbatim; plugin owns level state (R1); scheme←section (R2, D-A3a); decision tf as config (R3, D-A3b). D-A3c..f. |
| B | B1 | Add an optional plugin param to StrategyRuntime.__init__, defaulting to None; when None, run the exact current state.py:271-280 block | DONE | 2026-06-08 | `1491921` | full SC suite 140 passed (incl. test_runtime_state/touches/touch_zones/levels + A3 test_touch_reversal_plugin); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 passed vs branch SC); GATE test_production_pair_parity + test_duckdb_streaming_parity + test_decision_diff (3 passed, store+alpha_lab present) | None-path byte-identical (inner lines unchanged, +4 indent only); else = no-op `pass` (B2 placeholder); `plugin` added last (no param reorder); StrategyPlugin TYPE_CHECKING-only → registry stays empty. Only runtime/state.py changed. |
| B | B2 | Route _process_trade through plugin.on_bar_closed when a plugin is present, and construct StrategyRuntime with the registered TouchReversalPlugin in a feature-flagged path | DONE | 2026-06-08 | SC `7a5cc96`+`5061163`; TL `242c606` | full SC suite 145; test_b2_plugin_seam_parity (PART1); test_b2_wiring (resolver/W2/W4-lifecycle); GO-LIVE test_b2_golive_runtime_parity (real days 2025-07-15 339997 trades + 2025-07-07 306103 trades, OFF==ON per trade, 5 touches/6 zones); TL test_strategy_core_acceptance + test_strategy_core_replay_integration (3 OFF + 3 ON); decision-fn gates test_production_pair_parity + test_decision_diff (2 passed); ruff clean | flag SC_PLUGIN_ROUTING default OFF via wiring.touch_reversal_kwargs(); TL StrategyCoreService wired; lifecycle propagation + plugin load_prior_day_summary hook; plugin internal decision-tf gate REMOVED (runtime gates). Deviations D-B2f..k. |
| B | B3 | Make the plugin path the default for strategy_id="touch_reversal"; remove the dead hardwired duplicate only after a full green soak | DONE | 2026-06-09 | `85cb7b6` | pre-removal off-vs-on parity 7 (FINAL green, both paths present); digests frozen (off==on on 3,284,775 trades/path); full SC suite 144; real-data plugin regressions vs frozen digests (golive + multiday) 2; TL acceptance+replay 3; decision-fn gates 2; ruff clean | flip+delete: None path + `SC_PLUGIN_ROUTING`/`config.py` removed; plugin auto-attached (D-B3a, fail-loud non-default-scheme guard); off-vs-on real-data tests repurposed to frozen-digest regressions + seam/wiring converted (D-B3b); W2 guard retired (D-B3c); dead `_zones_for_detection`+`detect_touches` import removed, level_state fold/snapshot/dedup KEPT (D-B3d); fold-collapse + dedup-move SPLIT to S-B3a. 6-agent adversarial verify 5 PASS + 1 stale-comment fixed. |
| (added) | S-B3a | Collapse the redundant runtime level fold (D-B2a) + move the once-per-day `_touched_zone_keys` dedup INTO the plugin + flow the raw `Touch` back onto `RuntimeUpdate.touches` | DONE | 2026-06-09 | `f6e9be8` | frozen-digest regressions `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` 2 (fixtures UNTOUCHED; 3,284,775 trades, 8 reset boundaries, byte-identical); full SC suite 144; TL acceptance+replay 3; decision-fn gates 2 (UNCHANGED); ruff clean | runtime `level_state`/`_zones_for_snapshot`/`_touched_zone_keys`/`_zone_key`/`_touch_zone_key_from_touch` DELETED; plugin = sole owner (on_event returns the level fold; new `current_levels`/`snapshot_zones` accessors; plugin-owned `_fired_keys`; `already_fired_keys` retired; key helper relocated verbatim); raw `Touch` flow-back verbatim; D-B2b RESOLVED plugin-owned (owner-ratified); D-B2i gate + D-B3a guard untouched. Deviations D-SB3a-a..g. 5-agent adversarial verify 5 PASS (high). the LAST Phase-B tidy, before C; split out of B3's flip+delete prompt (added step, not in plan §7 — per deviation rule) |
| (added) | S-B3b | Tidy: declare the plugin seed path (`set_static_levels`/`load_prior_day_summary`) in the StrategyPlugin Protocol; rename the repurposed drift-net files off their `test_b2_*`/`parity` names; de-stale the V3 matrix PDH/PDL row | DONE | 2026-06-09 | `19c64da` | full SC suite 144 (same tests, new paths); digest regressions under the NEW filenames `test_b3_golive_plugin_regression` + `test_b3_multiday_reset_plugin_regression` 2 (fixtures untouched); ruff clean | closes S-B3a verify items (i)+(ii) and D-B3b's filename debt. §9.1 registry assertion now requires the seed hooks (deliberate strengthening). Living refs updated incl. the multiday file's live cross-import; historical PROGRESS mentions left as record. Deviations D-SB3b-a..c. TL pin bump DEFERRED to C1 (no TL-facing change). added step, not in plan §7 — per deviation rule |
| C | C1 | Repoint TL model_registry import from the local contract copy to strategy_core.contract, keeping today's flat StrategyContract shape | DONE | 2026-06-09 | TL `0e1c7ce` | TL full suite 435 passed + 1 skip (benchmark, flag-gated); real-bundle registry gate (exactly 3 v3 discoverable; all 3 activate end-to-end incl. hot-swap; legacy/v1/v2 rejected fail-closed); TL seam test_strategy_core_acceptance + test_strategy_core_replay_integration 3; QL suite 739 (incl. nodrift 9 + repoint 11); TL ruff clean; QL ruff unchanged (13 pre-existing, scratch files) | ALL 9 import sites (4 prod + 5 test) → strategy_core package root; engine hook at BOTH registry loader entries (D-C1a); legacy loads-unbound RETIRED, owner-ratified (D-C1b); fixture → minimal valid SC-v3, +2 keys only (D-C1e); binding tests → hook call shape (D-C1d); TL pin cbf9b99→c615e40 rode this commit (deferred S-B3b bump). 6-agent adversarial verify 6 PASS (high). Deviations D-C1a..e |
| C | C2 | Delete TL's local strategy_contract.py once nothing imports it | DONE | 2026-06-09 | TL `0e1c7ce` (same commit as C1) | full-repo grep: zero live importers (D-C2a); TL full suite 435 + 1 skip post-deletion; ruff clean | `domain/contracts/strategy_contract.py` + `__init__.py` git rm'd; emptied dir removed; only historical docs/plans prose + untracked BASELINE_REPORT.md/test.md still mention it (left as record) |
| D | D1 | Retire TL's local outcome tracker in favor of the engine's honest decision-time fill | DONE (pushed at the D1b greenlight — D1a DARK + D1b flip+delete) | 2026-06-10 | D1a: SC `c7564fd` + TL `c7f2a84`; D1b: SC `945f381` + TL `94610ff` (pushed at the D1b greenlight) | D1a: GATE A `test_d1_streaming_vs_batch_parity` EXACT per-touch parity (9 days, 42 touches/35 resolved, drops {flatten: 7}); GATE B characterization (29 preds; mean abs entry delta 55.6 ticks; 6 label changes; 5/29 correctness flips). D1b: SC suite 152 + ruff + b3 frozen-digest regressions 2 (fixtures untouched); TL suite 419 (= 420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin; dark file 7→8) + ruff; seam-by-name 4 (acceptance 3 incl. D2 guard + replay 1); frontend typecheck + vitest 142 (+5) + build green; 6-agent adversarial verify 5 PASS + 1 repaired | D1a: SC streaming resolver + trade ring + fail-loud activation validation; TL DARK seat (D-D1a-a..i). D1b: resolver SERVES via the new resolution adapter (TP/SL mapping, TL-side correctness, 0-BASED bars, additive `entry_price`, `resolved_ts` from new SC `StreamResolution.resolved_ts_utc`); drops surfaced (`prediction.dropped` + snapshot ring + RuntimeUpdate + frontend badge w/ reason, no chart marker); tracker + 16 tests + gate-B harness DELETED; ResolutionType SESSION_END/NO_RESOLUTION REMOVED (grep-proven); `parse_bar_type` relocated public; D2-guard tracker carve-out retired (D-D1b-a..i) |
| D | D2 | Confirm TL holds no local candle/session/level recompute, then assert it via test | DONE (pushed at the D1b greenlight) | 2026-06-10 | TL `73aa7df` | TL suite 420 passed 0 skipped (443 collected − 24 deleted engine tests + 1 new guard); strengthened guard + seam green; src-wide grep zero engine names; ruff clean | CandleEngine/_MutableCandle/CandleUpdate + SessionLevelEngine/_SessionRange/_DaySummary/LevelUpdate/SESSION_LEVELS/LEVEL_ORIGIN deleted, DTO types kept; guard = src-wide reintroduction ban + SessionClassifier confinement + DTO-surface pin with documented carve-outs; sessions.py NOT deleted (seed.py debt); httpx2→dev rider. Deviations D-D2-a..c + named debts |
| E | E1 | Introduce platform_version alongside ENGINE_VERSION, both stamped, loader fail-closes on either | DONE (pushed at the E greenlight) | 2026-06-10 | SC `8e5c017` + QL `baecf66` + TL `9b00eb5` | SC suite 154 (+2 negatives) + ruff + frozen b3 regressions 2 (fixtures untouched) + decision-fn gates 2 UNCHANGED; QL suite 740 + ruff; TL suite 424 + seam 4 + ruff | RATIFIED DEVIATION from the step wording: not "alongside" — a CLEAN RENAME (ENGINE_VERSION → PLATFORM_VERSION "strategy_core_platform_v1", no alias) + contract v2 shape break (engine_version→platform_version field, + required strategy_version); deployed store migrated in place w/ backups (3 v3 bundles; non-v3 deliberately not migratable — D-E-c). D-E-a..c,f |
| E | E2 | Add per-plugin strategy_version/strategy_id, fail-closed via registry-lookup equality; turn strategy_id into a router | DONE (pushed at the E greenlight) | 2026-06-10 | same window/commits as E1 | TL suite 424 (incl. 5 new gate negatives, both-entry coverage); REAL-BUNDLE GATE: exactly 3 migrated bundles discoverable, all 3 activate incl. hot-swap via the serving-guard registry, un-migrated .bak copy rejected on contract_version | strategy_id = registry ROUTER KEY end-to-end: QL emission resolves get_strategy (unknown id refuses to EMIT), TL gates both registry entries (resolve / version-equality / servable-flag / serving-id guard); contract_id stamping re-sourced to the active bundle id (byte-compatible); supported_by_runtime meaningful (QL True, TL refuses False, QL acceptance flipped). D-E-b,d,e,g,h |
| E | E3 | Decompose the flat StrategyContract into StrategyEnvelope + typed SectionModel; emit from the plugin | DONE (pushed at the E3 greenlight) | 2026-06-10 | SC `dc14652` + QL `523ff98` + TL `3d79bc4` | SC suite 162 (+8 contract-v3 negatives, +1 round-trip pin, −1 retired FeatureSet validator test) + frozen b3 digest regressions 2 (fixtures untouched) + decision-fn gates 2 UNCHANGED + ruff; QL suite 742 (740+2) + ruff; TL suite 429 (424+5) + seam-by-name 4 + ruff + frontend untouched; migration #2 on the real store (3 MIGRATED + 3 SKIP, idempotent re-run 6 SKIP); REAL-BUNDLE GATE: exactly 3 discoverable, all 3 activate incl. hot-swap w/ typed sections, v2 .bak copy rejected on contract_version | CONTRACT v3 (shape break #2): envelope = platform-consumed flat keys (+ label_policy.barrier_mode, + SessionScheme.closed_window); ONE "section" subtree typed by the plugin's SectionModel via the loader's opt-in validate_section_via_registry hook (non-field section_model carrier); partition + its validator moved to TouchReversalSection + the validate_feature_partition cross-check at the two validation sites; QL emits the section FROM a configured plugin SectionModel instance; TL validates the section at BOTH registry entries + threads ActiveModel.section to the two read paths; D-E-h ledger items (a)(b)(c)(iv) ALL CLOSED. Deviations D-E3-a..j. |
| F | F1 | Extend the candle data shape with a BarSpec/kind and add CloseReason.INTERVAL, with TICK behavior unchanged | NOT STARTED |  |  |  |  |
| F | F2 | Mirror the TIME close trigger into the vectorized batch path and pin it with a new parity test | NOT STARTED |  |  |  |  |
| F | F3 | Validate archetype 2 (HTF-FVG/iFVG) end-to-end on the same interface as a NEW plugin, behind its own strategy_id | NOT STARTED |  |  |  |  |
| (added) | S9.9 | data-drive session-name set in StrategyLevelState (drop hardcoded asia/london); behavior-preserving; feeds F | NOT STARTED |  |  |  | added step, not in plan §7 — per deviation rule |

---

## Change log (newest first)

- **2026-06-10** — **E3 GREENLIGHT executed and PUSHED (all three repos)** after
  the 7-lens adversarial verify (7/7 PASS high; journal `wf_a678b991-e95`) and
  owner review of the exported diffs. No reviewed commit amended (SC `dc14652` +
  `06be823`, QL `523ff98`, TL `3d79bc4`); greenlight work = new commits:
  (1) QL `77c5870` `chore: pin strategy-core @ E3` — pin `8e5c017 → dc14652`
  (the E3 consumer-facing SC code commit; doc commits do not move pins); QL
  suite **742** + ruff green on the bumped tree. (2) TL `e855aa3` (same chore
  shape) — pin `8e5c017 → dc14652`; TL suite **429** + seam-by-name **4** + ruff
  green on the bumped tree. (3) This SC doc commit — E3 status row stripped of
  the LOCAL qualifier; **9.6 FINAL FLIP: ENFORCED — witnessed 2026-06-10** (QL
  `ci` run #1 GREEN in 1m27s: cold install 52s resolving the pin anonymously +
  ruff + 740 tests on a fresh runner; TL `backend-ci` run #2 GREEN in 51s: cold
  install 36s + 424 tests — the former named debt is CLOSED); ledger additions
  recorded (the F-era `direction_from_side` lowercase normalization candidate;
  the Node-20 deprecation note on `actions/checkout@v4`/`setup-python@v5` in
  both CI workflows). Safety asserts (4 reviewed shas exist unchanged +
  ancestry + clean trees + branch) ran before the pushes. Both CI workflows
  fire on these pushes (branch filters include `platform-refactor`); the owner
  relays the run results. PLAN unmodified.
- **2026-06-10** — **E3 (contract v3 — envelope/section split + emission from the
  plugin + the D-E-h ledger) landed as LOCAL commits across all THREE repos → E3
  DONE locally — FULL STOP before push** (SC `dc14652` + QL `523ff98` + TL
  `3d79bc4` on `platform-refactor`; diffs exported as `E3_SC_DIFF.txt` /
  `E3_QL_DIFF.txt` / `E3_TL_DIFF.txt`). SC: `StrategyContract` becomes the
  platform ENVELOPE + ONE raw `section` subtree; the five plugin-consumed groups
  + the feature partition move into `TouchReversalSection` (partition validator
  with them; new `validate_feature_partition` cross-check for the two validation
  sites); loader gains the opt-in `validate_section_via_registry` hook with the
  NON-FIELD `section_model` carrier (single-return shape preserved, hookless
  access fails closed); `LabelPolicy.barrier_mode`
  (`fixed_points|r_relative`, default fixed_points); contract `SessionScheme`
  gains the optional `closed_window` pair — scheme adapters now round-trip
  drop-nothing BOTH directions (CT scheme pinned); the section-default
  `touch_rule.bar_type` "tick" → constant-sourced "147t" and the
  `forward_bar_type` landmine died with `label_policy`'s move to the envelope;
  `CONTRACT_VERSION` → v3 (shape break #2). QL: the emitter builds a configured
  `TouchReversalSection` INSTANCE (plugin default + per-run overrides) and
  `model_dump()`s it as the section subtree; `barrier_mode` sourced from the
  plugin's `label_policy()` declaration; the partition cross-check runs AT
  EMISSION; `scripts/migrate_contracts_v3.py` EXECUTED on the real store —
  **3 MIGRATED + 3 SKIP (not migratable), idempotent re-run 6 SKIP**, backups
  `strategy.json.pre_v3.bak`, the tracked bundle's migration committed. TL: BOTH
  `model_registry` entries load with the section hook (discovery
  skips-with-warning, activation raises); `ActiveModel` carries the TYPED
  `section` + the REAL metadata cross-check result; the partition cross-check
  runs at ACTIVATION; LEDGER (a) metadata cross-check FAIL-CLOSED at activation,
  (b) absent checksum sidecar now WARNS, (c) `ModelStatus.validation_ok` is the
  real result, (iv) closed SC-side; the two section read paths
  (`inference_engine` direction map, `feature_functions` windows/bands) thread
  `ActiveModel.section` (the duck-typed touch coupling recorded, D-E3-h).
  REAL-BUNDLE GATE (post-migration): exactly the 3 migrated bundles
  discoverable; all 3 activate incl. hot-swap with typed sections; an
  un-migrated v2 `.bak` copy rejected on contract_version. Gates on the final
  trees: SC **162** + ruff + frozen b3 digest regressions **2** (fixtures
  untouched) + decision-fn gates **2** UNCHANGED; QL **742** (740+2) + ruff; TL
  **429** (424+5) + seam-by-name **4** + ruff + frontend UNTOUCHED. Deviations
  **D-E3-a..j**. PLAN unmodified. PIN NOTE: SC `dc14652` is CONSUMER-FACING for
  BOTH consumers (the loader hook kwarg, the section model reshape, and the
  v3 CONTRACT_VERSION are all consumer-imported) — both pins bump to the final
  pushed SC sha AT GREENLIGHT as chore commits, per the standing pin convention.
- **2026-06-10** — **E GREENLIGHT executed and PUSHED (all three repos)** after the
  6-lens adversarial verify (6/6 PASS high; journal `wf_a70536bc-ba9`) and owner review
  of the exported diffs. No reviewed commit amended; greenlight work = new commits:
  (1) QL `e10d226` `chore: pin strategy-core @ E1 + CI branch filter` — pin
  `c615e40 → 8e5c017` (the LONG-DEFERRED 9.6 bump) + `ci.yml` `on.push.branches` +=
  `platform-refactor` (without it the 9.6-enforcing run could not fire before merge
  day); QL suite **740** + ruff green on the bumped tree. (2) TL `ef8a189` (same chore
  shape) — pin `945f381 → 8e5c017` + `backend-ci.yml` push trigger was main-only, +=
  `platform-refactor`; TL suite **424** + ruff green on the bumped tree. (3) This SC
  doc commit — status rows D1/D2/E1/E2 stripped of LOCAL qualifiers (D pushed at the
  D1b greenlight; E pushed at this one); 9.6 re-statused **ENFORCED pending the first
  green CI run** with the full pin history recorded; PLUS the axis-presentation pass on
  the four stale top-level docs the E verify flagged (README / MIGRATION /
  V3_COMPATIBILITY_MATRIX / validation README: ENGINE_VERSION → the PLATFORM_VERSION
  presentation). Safety asserts (4 reviewed shas exist unchanged + ancestry + clean
  trees + branch) ran before the pushes. PLAN unmodified.
- **2026-06-10** — **E-WINDOW (E1 two-axis versioning + E2 registry router gate) landed
  as LOCAL commits across all THREE repos → E1/E2 DONE locally — FULL STOP before push**
  (SC `8e5c017` + QL `baecf66` + TL `9b00eb5` on `platform-refactor`; diffs exported as
  `E_SC_DIFF.txt`/`E_QL_DIFF.txt`/`E_TL_DIFF.txt`). SC: `ENGINE_VERSION` →
  `PLATFORM_VERSION` ("strategy_core_platform_v1", clean rename, no alias);
  `CONTRACT_VERSION` → v2 (shape break); contract field `engine_version` →
  `platform_version` + NEW required `strategy_version`; loader hook →
  `expected_platform_version`; `strategy_id` re-documented as the REGISTRY ROUTER KEY;
  the plugin's `strategy_version="1"` is now LOAD-BEARING. QL: the emitter resolves
  `strategy_version` via `get_strategy` (unknown id fail-closes EMISSION), stamps the
  router id (caller passes "touch_reversal", not the dir name), flips
  `supported_by_runtime=True` (full contract; minimal stays False — schema-incomplete by
  design); `dataset_config_hash` input renamed (cache tags roll);
  `scripts/migrate_contracts_v2.py` EXECUTED against the real store — 3 v3-engine bundles
  migrated in place w/ `.pre_v2.bak` backups, idempotent; the prompt's blanket
  platform_v1 stamp was NARROWED to engine-v3-only after the first run exposed that it
  would FORGE the binding for the store's legacy/v1/v2-engine bundles (caught, restored
  from backups, corrected — D-E-c); acceptance gate flips to assert the flag True; NEW
  `.github/workflows/ci.yml` cold-install CI (9.6: DECLARED → **ENFORCED pending the
  first green run**, which requires the greenlight pin bump + push); tooling aligned
  py313. TL: BOTH `model_registry` entries pass the platform hook + the NEW 4-check
  strategy gate — get_strategy resolve / strategy_version equality / servable-flag /
  serving-id guard (`ModelRegistry(serving_strategy_id=…)` fed by the new
  `StrategyCoreService.plugin_strategy_id`); `Prediction.contract_id` re-sourced to the
  active bundle id (byte-compatible; UI-visible: bundle `strategy_id` DTO values become
  "touch_reversal"); report keys → `strategy_core_platform_version`; fixture → v2 (+ the
  recon-flagged `mid_price_source` drift fix); `test_engine_version_binding` → git mv
  `test_platform_version_binding` + 5 new negatives. REAL-BUNDLE GATE (post-migration):
  exactly the 3 migrated bundles discoverable; all 3 activate end-to-end incl. hot-swap;
  an un-migrated `.bak` copy rejected on contract_version. Gates on the final trees: SC
  **154** + ruff + frozen b3 regressions **2** (fixtures untouched) + decision-fn gates
  **2** UNCHANGED; QL **740** (739+1) + ruff src/tests clean (the 13 pre-existing
  scratch findings stand); TL **424** (419+5) + seam-by-name **4** + ruff + frontend
  UNTOUCHED. Deviations **D-E-a..h**. PLAN unmodified. PIN NOTE: SC `8e5c017` is
  CONSUMER-FACING for BOTH consumers — both pins (TL from `945f381`; QL's long-deferred
  from `c615e40`) bump to the final pushed SC sha at greenlight as chore commits.
- **2026-06-10** — **D1b GREENLIGHT executed and PUSHED** (SC `77015de..2cb27dc`, TL
  `4bb9290..5ede158` fast-forward to origin; QL untouched): the stale pre-amend sha in
  the D-D1b header fixed (SC `2cb27dc`); TL pin bumped to the pushed D1b SC sha
  `945f381` (TL `5ede158`, suite 419 + ruff green on the bumped tree); safety asserts
  (commit existence + ancestry + clean trees) passed before push.
- **2026-06-10** — **D1b (flip + delete: SERVE the honest resolver, RETIRE the tracker)
  landed as LOCAL commits → D1 DONE locally — FULL STOP before push** (SC `945f381` + TL
  `94610ff` on `platform-refactor`; QL untouched at `9b8e798`; diffs exported as
  `D1B_SC_DIFF.txt` / `D1B_TL_DIFF.txt` for owner review). SC PART 1 (additive):
  `StreamResolution.resolved_ts_utc` = the resolving bar's `close_ts_utc`, stamped in
  `on_bar`; the batch `OutcomeResult` deliberately stays timestamp-free (caller concern) —
  asymmetry documented in the `StreamResolution` docstring; gate A cannot arbitrate the
  field, so it is pinned by a NEW resolution-path unit test (the file had none — gate A
  owned resolutions; D-D1b-a). TL PART 2 (the flip): NEW
  `services/inference/resolution_adapter.py` maps `StreamResolution`+`Prediction` → served
  `Outcome` (tradeable_reversal→TP_HIT, blowthrough/trap→SL_HIT, fail-loud unmapped;
  correct computed TL-side; ZERO-BASED bars — the tracker was 1-based; NEW additive
  `entry_price` = the honest fill) and `StreamDrop`+`Prediction` → NEW `DroppedPrediction`;
  drops broadcast as `prediction.dropped`, ride the snapshot (`dropped` ring, same cap) +
  `RuntimeUpdate.dropped` + replay coalesce, and render in IntelligencePanel as a distinct
  badge with reason (no chart marker — drops never enter `prediction.outcome`);
  `ApplicationRuntime` serves resolver emissions through the adapter with the new
  `_open_predictions` correlation map (lockstep clear with `resolver.reset()`); the DARK
  ring + `dark_outcomes` + gate-B plumbing DELETED; `outcome_tracker.py` + its 16 tests
  DELETED (`parse_bar_type` relocated VERBATIM, now public in the adapter module);
  `ResolutionType.SESSION_END`/`NO_RESOLUTION` REMOVED (grep proof: zero post-flip refs);
  `validation/d1_characterization_harness.py` RETIRED (deleted — comparison subject gone;
  the md artifact + git history are the record); the D2 guard's tracker carve-out bullet
  removed ON SCHEDULE. Gates on the final trees: SC suite **152** + ruff + frozen b3
  digest regressions **2** (fixtures untouched); TL suite **419** (accounted exactly:
  420 − 16 tracker + 13 adapter + 1 dropped-frame + 1 swallow pin; dark file 7→8
  adapted); seam-by-name **4**; TL ruff clean; frontend typecheck clean + vitest **142**
  (137 + 5 new) + vite build green. Assertion changes enumerated in D-D1b-h. 6-agent
  read-only adversarial verify on the exact local commits: **5 PASS (high) + 1 FAIL
  REPAIRED in-window** (the `_track_outcomes` per-emission consumption was unguarded
  vs the docstring's hot-path swallow invariant → per-item guard + pinning test;
  D-D1b-e/D-D1b-i; informational findings recorded in D-D1b-i). Deviations
  **D-D1b-a..i**. PLAN unmodified. PIN NOTE: SC `945f381` is CONSUMER-FACING — TL's
  adapter reads `resolved_ts_utc`, so a cold install from the current `c7564fd` pin would
  AttributeError on the first resolution (dev editable masks it); the pin bump to the
  final pushed SC sha rides the greenlight as a NEW chore commit (same flow as
  `4bb9290`).
- **2026-06-10** — **D-WINDOW: D1a (streaming honest resolver, DARK) + D2 (shadow-engine
  deletion + guard) landed as LOCAL commits — FULL STOP before push** (SC `c7564fd`, TL
  `c7f2a84` + `73aa7df`; QL untouched; pushes + the TL pin amend await explicit owner
  greenlight after diff review — the SC D1a commit is consumer-facing, so per the pin
  convention TL's pin bumps to the final pushed SC sha AT GREENLIGHT). D1a: SC
  `decisions/streaming.py` `StreamingHonestResolver` (incremental `resolve_honest_outcome`
  over the outcomes kernel: register-at-decision with the exact flatten→cutoff→no_fill
  firing order; strict-window per-bar excursions; cutoff → no_forward/no_resolution drops),
  runtime trade ring + `trade_price_at` (price>0 ≙ the reference's row-validity; 30-min
  query bound; ctx stub backed; quotes_in_window stays a §9.10 stub), fail-loud
  forward-timeframe activation validation [CORRECTION 2026-06-13: overstated — the failure 500s after the registry swap; torn state, not a rejection (audit F12); atomic activation scheduled in W2.]; TL runs the resolver DARK alongside the tracker
  (touch-anchored registration off the observation chain, same closed-bars hook, parallel
  500-cap dark ring, zero WS/DTO/frontend change; offset-mismatch warning once at
  activation). **GATE A: EXACT streaming==batch per-touch parity** over the 9 real store
  days (42 touches: 35 resolved {tradeable 25, blowthrough 7, trap 3} + drops {flatten 7};
  every drop-vs-outcome/reason/label/mfe/mae/bars/entry equal). **GATE B characterization**
  (real bundle through the registry, trades-only, live-like): 29 predictions, 29/29
  resolved both paths, mean |entry Δ| 55.6 ticks (max 226), 6 label changes, 5/29
  correctness flips, zero SESSION_END — `D1_CHARACTERIZATION.md` exported. Forced test
  adaptation (D-D1a-f): 5 pre-existing TL tests activated the 147t contract on
  (2,)-timeframes (the very hole the validation closes) → helpers now (2, 147). D2: the
  dormant `CandleEngine`/`SessionLevelEngine` shadow engines + 24 engine tests deleted (DTO
  types kept; oracle losses recorded D-D2-c), acceptance guard strengthened to an src-wide
  reintroduction ban + SessionClassifier confinement + DTO-surface pins (carve-outs
  documented in-test), httpx2 → dev extra (probe verdict: correct + load-bearing via the
  starlette-1.x cold-CI testclient; C-window verify item (ii) RESOLVED). Gates on the final
  trees: SC suite **144** + ruff; b3 frozen-digest regressions **2** (fixtures untouched);
  decision-fn gates **2**; gate A **1**; TL suite **442+1skip** at D1a and **420/0** after
  D2 (collection fully accounted); seam **3** (+ the new guard); TL ruff clean. Deviations
  **D-D1a-a..i, D-D2-a..c** + Phase-D named debts. PLAN unmodified. D1b = the flip+delete
  (serve the resolver, retire the tracker + SESSION_END + the WS surface), NEXT, pending
  greenlight.
- **2026-06-09** — **POST-C AMENDMENT (doc-only):** (1) **9.6 re-statused: pin DECLARED
  (c615e40), enforcement DEFERRED** — dev resolves SC via the editable install; nothing
  currently exercises the pin; NAMED DEBT added: **QL cold-install resolution check** (the
  analog of TL's cold-install CI), required to make 9.6 enforced rather than declared. [stale claim — superseded by E-window CI work] The
  C-window record's "9.6 IMPLEMENTED" headlines are amended accordingly (Current state, the
  9.6 decision line, D-9.6a, the C-window entry below). (2) **Before-state CORRECTION
  (D-C1f), probe-verified:** through a temporary TL worktree at `be90af3` running the pre-C1
  LOCAL loader against the real store, the pre-C1 servable set was **{legacy
  `NQ_20260405_…iterations800_depth4`, UNBOUND}** only — all 3 v3 bundles failed
  `extra_forbidden` on `label_policy.decision_offset_minutes`, v1 failed the engine bind, v2
  failed SCHEMA (never reached the old loader's engine check). C1 therefore **FLIPPED** the
  served set {legacy-unbound} → {3× v3}; the recon's "3 activatable v3 bundles (pre-C1)"
  framing was wrong. Worktree removed after the probe; TL/QL untouched; PLAN unmodified.
- **2026-06-09** — **Phase C (C1+C2) landed → Phase C COMPLETE; 9.6 pin DECLARED
  (headline amended 2026-06-09: enforcement DEFERRED — see the POST-C AMENDMENT entry above)**
  (TL `0e1c7ce` + QL `9b8e798`, both on `platform-refactor`; SC CODE untouched — this record
  commit only). C1: all 9 TL import sites (4 production incl. the TYPE_CHECKING deep import +
  5 tests) repointed onto the `strategy_core` package root; the fail-closed engine gate is
  preserved single-sourced via SC's opt-in hook — `load_strategy_contract(...,
  expected_engine_version=ENGINE_VERSION)` at BOTH `model_registry` loader entries (discovery
  `_describe_bundle` AND activation `_load_contract` — the v2-class store bundle is SC-schema-
  valid, so a hookless discovery would have listed it; D-C1a). Legacy loads-unbound RETIRED,
  owner-ratified (D-C1b). Fixture regenerated as a minimal valid SC-v3 contract (+2 keys
  exactly; D-C1e); `test_engine_version_binding` rewritten to the hook call shape
  (matching loads / mismatched-v2 fails / absent fails; D-C1d). C2: local copy
  `trade_lab/domain/contracts/` DELETED with zero live importers by full-repo grep (D-C2a).
  9.6: QL declares + SHA-pins strategy-core byte-identically to TL's pin form at `c615e40`;
  TL's pin bumped cbf9b99 → c615e40 in the same TL commit (the deferred S-B3b bump);
  `requires-python` rider `>=3.14` → `>=3.13` (D-9.6a; editable stays for dev; QL `sys.path`
  script hacks recorded as debt). PIN CONVENTION: the pin tracks the latest SC commit with
  consumer-facing content; doc-only SC commits do not move it. Gates on the final trees:
  real-bundle gate THROUGH the repointed registry (exactly the 3 v3 bundles discoverable —
  `NQ_20260603_233847`/`NQ_20260604_012623`/`NQ_20260604_015413`; all 3 activated end-to-end
  incl. hot-swap; legacy/v1/v2 rejected with the unsupported-engine_version `ContractError`);
  TL full suite **435 passed + 1 skip** (benchmark, flag-gated, pre-existing); TL seam gates
  **3**; QL suite **739** (= pre-change baseline; incl. `test_strategy_contract_nodrift` 9 +
  `test_strategy_contract_repoint` 11); TL ruff clean; QL ruff unchanged vs baseline (13
  pre-existing findings in root scratch files); pin reachability `ls-remote` +
  `merge-base --is-ancestor` PIN-REACHABLE. Verified by a 6-agent read-only adversarial
  workflow (repoint-completeness / call-shape / gate-preservation / fixture-validity / scope /
  pin-correctness — **6 PASS, all high confidence**). Deviations **D-C1a..e, D-C2a, D-9.6a**.
  PLAN unmodified.
- **2026-06-09** — **S-B3b tidy landed → S-B3b DONE** (committed as SC `19c64da` on
  `platform-refactor`; post-Phase-B, pre-C1). Three recorded
  debts closed in one doc/declaration-only pass (no runtime/plugin behavior change; frozen
  digest fixtures untouched): (1) `StrategyPlugin` now DECLARES the seed path —
  `set_static_levels` + `load_prior_day_summary` — so the §9.1 registry-time assertion
  fail-closes a plugin missing the hooks at `@register` instead of an `AttributeError`
  mid-session (closes S-B3a verify item ii); (2) the repurposed drift-net files renamed off
  their stale `test_b2_*`/`parity` names via `git mv` (contents/function names/assertions
  unchanged; living refs updated incl. the multiday gate's live cross-import; map in
  D-SB3b-b — closes D-B3b's cosmetic debt); (3) the V3 compatibility matrix PDH/PDL row
  reworded to plugin-owned level state (closes S-B3a verify item i). Harnesses on the final
  tree: full SC suite **144** (same tests, new paths); digest regressions under the NEW
  filenames **2 passed** (fixtures untouched); ruff clean. TL/QL untouched; TL pin bump
  deferred to C1. Deviations **D-SB3b-a..c**. PLAN unmodified.
- **2026-06-09** — Phase B Step **S-B3a landed → S-B3a DONE, Phase B COMPLETE** (committed as SC
  `f6e9be8` on `platform-refactor` after review + a byte-identical diff comparison against the
  reviewed export; the LAST Phase-B step). One behavior-preserving collapse: the plugin's level state is now the
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

---

## POST-E3: COLD AUDIT, CONVERGENCE RULINGS, AND THE W-PLAN (2026-06-10 → 2026-06-13)

### Audit record
Three independent docs-blind audits ran against SC/TL/QL @ platform-refactor tips (SC 0c1cc62 · TL e855aa3 · QL 77c5870): GPT-5.5 v1, GPT-5.5 v2, and a CC/Fable multi-agent audit (journals wf_207898e6-873, wf_39fa019c-fa5, wf_64f69c57-296; 50 adversarial verdicts — 39 confirmed, 11 adjusted, 0 refuted). Full report with 243-finding annex: COLD_WIRING_AUDIT_REPORT.md (job-tmp original is volatile; owner holds a safe copy). A targeted verification (Q1–Q4) followed with per-feature and per-mechanism verdicts.

Headline: three serving-path BLOCKERs invisible to every existing gate (all proofs stop at the SC engine boundary): F1 dwell features served from quote mids vs trade-print training; F2 PDH/PDL structurally unreachable live; F3 200k buffer cap evicts feature windows during NY RTH. Load-bearing DEFECTs include F5 (replay day = UTC file slice, 147t grid phase shift — root cause of the e2e touch/entry deltas, confirmed by Q2), F6/F7 (research-side: bar-close session attribution leaks prints into level values; zones built once from final levels = lookahead serving cannot replicate), F9/F18 (entry tie-break + float ns decode), F10 (resolver flush() has zero callers), F17 (day-context-free 16:40 compare embargoes the evening half of every trading day from the label universe), F22/F27 (8-vs-3 feature vocabulary ungated; acceptance cannot run — no bundle has oos_predictions.parquet because the writer is conditional on a non-empty frame). Q3 verdict: the live drift net (b3 digests, duckdb-streaming parity, decision-diff, d1 streaming-vs-batch) is GREEN at HEAD; red harnesses are rot reaching for never-committed symbols, scheduled for deletion per D-P-02. The doc never claimed research↔serving parity — the BLOCKERs lived in the gap the record did not cover. This section closes that gap.

### Ratified rulings (owner; FINAL unless superseded by labeled block)
- D-P-01 — Tracer-dye policy: zero effort rehabilitating pre-convergence models; not retrained, not performance-chased, not test baselines. Acceptance runs on a FRESH model trained through the converged pipeline.
- D-P-02 — Legacy QL artifacts are untrusted and not tested against. Disposition is deletion, not repair: parity_harness.py / parity_harness_v2.py, phase8_1 golden + captures, audit_lookahead.py (W2 cargo); the legacy reader/level/zone stages left the production path in W1 (moved to ml/legacy_decision.py, parity-tests-only); the QL dashboard stack remains a superseded POC, removal deferred.
- D-P-03 — Data-availability parity (L1-consumption invariant): live is MBP-1; research and replay consume ONLY the L1 projection (trades + TOB-change-deduped quotes) of the mbp-10 parquets, through one canonical SC reader. Parquets remain the sole research/replay source (including >1-year regimes); the Databento historical API exists solely for the live warm-start slice. The two routes are shape-checked against each other once (route-seam check, W2).
- D-P-04 — Flatten policy: flat by NY futures close, daily; FLATTEN_TIME = 16:40 ET (= 15:40 CT), anchored to the decision's OWN trading day. The prior day-context-free compare was the defect (F17), not the time. The 15:55 executor literal is deprecated with its legacy stack.
- D-P-05 — F6/F7 research-causality fixes ride the convergence; the resulting change to future training data is accepted.
- D-P-06 — Live warm-start: at startup and on reconnect, the engine is fed the trading day's events from 18:00 ET (Databento live replay-start or historical API) before going real-time; the Chicago display seed is retired. (W2)
- D-P-07 — Prediction journaling: append-only record of predictions/outcomes/drops so serving evidence survives restarts (soak prerequisite). (W2)
- D-P-08 — Repo visibility: private flip deferred indefinitely; whenever chosen, an authenticated token mechanism lands and proves green in CI BEFORE the flip.
- D-P-09 — platform-refactor is never squash-merged (pinned-SHA orphan risk).
- D-P-10 — Roadmap: S9.9 and Phase F are PARKED behind the W-plan below. The interim "P-window" framing is superseded.

### The W-plan
- W1 — ONE SURFACE: COMPLETE (record below).
- W2 — OPERATE: warm-start + reconnect recovery; flush() wired at replay-end/live-stop/hot-swap; atomic activation preserving loop-atomicity; typed frontend reset; named-feature failure visibility; journaling; sidecar writer; unconditional OOS writer (+ root-cause of historically empty frames); acceptance via the registry section hook; SC CI with validation tests in the suite; TL live-adapter integer-ns decode; D-P-02 deletions (parity_harness*, phase8_1 golden + captures incl. engine.json, audit_lookahead); verify organic PDH banking's weekend-gap lookup (Friday→Monday) in the level-state emission.
- W3 — PROVE: batch-vs-stream parity gate on canonical input, hard-green with fault-injection sensitivity tests (gate expectations must include the preserved research `<5-interaction-print` drop rule — a known, deliberate serving asymmetry); fresh train → emit → discover → activate → replay acceptance; then live with journaling and a ≥7-trading-day soak before any number is trusted. Quote-pass vectorization in stream labeling precedes any multi-day training run. Doc/decision reconciliation residue (incl. whether test_decision_repoint_parity retires) rides this greenlight.
Discipline: strictly serial with full hunk review between windows; tests only for created/changed code during a window, one full suite+lint pass per repo at window close; review-tier conventions unchanged.

### W1 record (2026-06-12, greenlit after full three-repo hunk review)
Scope landed: SC canonical ingestion (day-mode for_trading_day [prev 18:00 ET, day 18:00 ET) with UTC-midnight file partition, post-merge TOB L1 dedup, count-based front month with larger-id tie-break, bytes-tolerant decode, row-group pruning); F17 day-anchored flatten (batch + streaming, evening setups label/serve against their own day); PDH/PDL organic banking at the day roll (explicit seed wins); DIRECTION_FROM_SIDE repaired per §3 (platform constant removed; typed engine default in decisions/touch.py; plugin owns the lowercase wire vocabulary; QL emitter ships it verbatim). TL: adapter = thin shim over the SC source (−1,403 lines; no-dedup quote path and float-ns decode deleted; date-directory replay sources play the canonical trading day); contract-driven retention (approach+interaction+10 — corrected from the spec's max()) with 6M safety ceiling and time-governed eviction; the six features call SC formulas over trade prints with the exact zone representative price threaded touch→observation→inference; serving_compatibility_error — one fail-closed 8-check activation gate, a negative test per check; chimera fixture made producible (v3 scheme, prior_day_full). QL: production labeling = batch drive of the SC runtime over the canonical stream (process_single_date_stream; half-open [start,end) feature windows matching serving; wire-last 30-min-bounded entry; <5-print research drop preserved; deduped quotes feed app_max_spread); legacy stages → ml/legacy_decision.py (parity-tests-only, verified by a sys.modules call-graph assertion); dataset_config_hash folds decision_pipeline=sc_runtime_stream_v1 (pre-W1 caches invalidate); use_engine=False raises.
Commits: SC 2beb022..256020c (6) · TL e855aa3..0ffc9ff (5, landed ff-only from worktree-w1-migration) · QL 4 + lint. Suites at close: SC 177 / TL 381 / QL 744, ruff clean (configured scope). TL 429→381 reconciled exactly: 83 removed (41 deleted TL-local normalization pins + 41 star-import duplicates via tests/test_historical_parquet.py + 1 rename) vs 35 added; every removed pin maps to deleted machinery now covered by SC's 15 parquet-source tests or the new shim/gate/retention tests.
Review verdict: approved, zero code fixes. Accepted deviations: retention formula (CC's correction of the spec); legacy moved-not-deleted (book-mid parity proof still drives it; W3 decides retirement). Unflagged behavior fix recorded: the old TL adapter mapped Databento side 'A' (sell aggressor) to UNKNOWN; the shim maps it correctly. Pins: TL+QL Strategy-Core pin dc14652 → 256020c (W1 greenlight chore commits). Operator note: pre-W1 bundles with 120-min approach windows are refused by the gate under the default 45-min retention ceiling — correct behavior; they are tracer dye under D-P-01 and the fresh W3 bundle declares its own windows.

### W2 record (2026-06-12, landed LOCALLY on all three repos — NOT pushed; awaiting greenlight review) [GREENLIT + PUSHED 2026-06-12: pins HELD at `256020c` (no consumer-facing SC change this window, per the 9.6 pin convention); CI green ×3 incl. SC's first `ci.yml` run; W2-FIX = SC `32e9cc0` (F4) + `ecbc15e` (F3 bracket correction), TL `df6b2c4` (F1–F3) + lint `5a8d28a`]
Scope landed — TL (worktree branch `worktree-w2-operate`, base 81a54b2): P1a integer-ns decode in the live adapter (floor-µs `EPOCH + timedelta(µs=ns//1000)`; float `fromtimestamp` route deleted; precision-loss unit test at ns 1_770_000_000_123_456_789) + an unflagged-defect rider mirroring W1's shim note: live side 'A' (ask aggressor) now maps to SELL (was UNKNOWN — every sell print starved side-aware features on the live path). P1b warm-start: PRIMARY = `start=<trading-day 18:00 ET>` forwarded on the trades+quote live subscribes (gateway intraday replay through the SAME adapter path); FALLBACK on runtime rejection = Historical-API DBN records (trades + mbp-1) merged by ts_event and drained through the same `normalize_provider_message` path BEFORE the live subscribe (spec order fetch→feed→subscribe-from-now, so history can never overflow the live queue); status surface reports "warming (N events)" vs "live" (event ts vs start wall clock). P1c prior-day PDH/PDL: ohlcv-1h over the prior trading day reduced to (max high, min low) ticks → `runtime.load_prior_day_summary` (the research/cold-replay seed path); loud skip without API access; `prior_trading_day` skips weekends (Friday serves Monday; holidays surface as an empty fetch + warning). P1d reconnect = the same warm-start path: a feed disconnect re-runs the FULL start (reset + prior-day seed + trading-day replay) after a short delay — the wipe-without-recovery hole is closed; fake-feed drop test. P1e Chicago seed RETIRED: `services/seed.py` + tests deleted (zero other importers), `seed_enabled`/`seed_lookback_days` settings removed; display warm-up now comes from real engine bars via the warm-start replay. P2a (F10): `runtime.flush_resolver()` wired at replay stream end (last event instant), live stop (wall clock; FastAPI lifespan shutdown hook added so it runs on process exit), and hot-swap (OLD resolver flushed before the swap); flushed drops ride the existing drop→DroppedPrediction surface and the journal. P2b (F12): registry `prepare_activation`/`commit_activation` + runtime `prepare_inference_rebind`/`commit_inference_rebind` — validation, ActiveModel construction, and resolver build all complete BEFORE the swap; the commit pair is pure assignment with no awaits between (loop-atomicity preserved); negative test: a corrupt-binary bundle that passes discovery 409s and leaves the old model serving. P2c: typed `model.reset` WS frame (reason activation|replay_reset|live_reset) replaces the frontend 'runtime reset' substring trigger; activation clears prediction/outcome panes only, runtime resets also clear chart+intelligence; frame named `model.reset` per the envelope dot convention (spec example said `model_reset`); emitted on live resets too since the replaced trigger fired there. P2d: `FeatureComputationError` names the failing feature; the runtime logs exc_info=True with the name, counts, and surfaces `last_inference_error` (name + ts) on /api/v1/status. P2e (D-P-07): append-only per-trading-day JSONL journal under `TRADE_LAB_JOURNAL_PATH` (default backend/data/journal/), records predictions (features/probabilities/eligibility), outcomes, drops, tagged replay|live + bundle id; 18:00 ET rotation tested; write-only this window. QL: P3a OOS ROOT CAUSE — every shipped bundle predates commit 25d7459 (2026-06-07), which introduced BOTH `build_oos_predictions_frame` and the writer; `training_result.get("oos_predictions")` was None at every save, and the `isinstance(...) and not empty` guard (scripts/ml_training_tab.py:1498-1502 pre-W2) silently skipped — no bundle was ever saved after the writer landed, so none has the parquet. Fix: writer UNCONDITIONAL (empty frame writes the parquet WITH canonical schema; missing/illtyped frame or failed write fails the save loudly). P3b: `save_trained_model` refuses partial bundles — `training_result` and `config` now REQUIRED; metadata-augmentation and strategy.json swallows removed (failures abort); NEW unconditional `model.cbm.sha256` sidecar (TL activation verifies it; the store had none) [review initially flagged the verification as missing — a diff-only inspection error: `_verify_checksum` has gated activation since E3; W2-FIX hardened it (bundle-named mismatch detail, absent-sidecar log warning→debug per D-P-01) and added the API-level tampered/absent tests]. P3c (A177): acceptance harness = the documented W3 entrypoint; bundle/data paths from `QL_ACCEPTANCE_BUNDLE`/`QL_ACCEPTANCE_DATA_DIR` with loud refusal; contract loads via the registry section hook (`validate_section_via_registry=True`); NOT run against real data. P3d (D-P-02): QL `scripts/audit_lookahead.py`, `scripts/phase8_1_golden.py`, `data/experiment/phase8_1/` (engine.json + golden.json) deleted; the `parity_harness*.py` pair lives in SC validation/ and was deleted THERE (repo-split deviation from the part labels; zero imports proven in both repos). SC: P1f weekend-gap verify — the emission lookup already resolves the most recent banked day < current trading day, so NO FIX was needed; Friday→Monday two-day stream test added. P4: NEW SC `.github/workflows/ci.yml` (cold install, config-faithful repo-root ruff, pytest) + `workflow_dispatch` on all three repos' workflows (A157); pyproject testpaths gains `validation/` (every validation test self-skips on path-existence guards and imports only SC+numpy+pandas at module level — cold collection green, 184 collected); the 47 F32 lint errors fixed mechanically (F401 removals, E401/E702 splits, E741 l→lvl renames, `# noqa: E402` where imports must follow the documented sys.path bootstrap — moving them would change harness behavior). P5 route-seam (D-P-03): `scripts/route_seam_check.py` (API trades+mbp-1 with the canonical post-merge L1 dedup vs `DatabentoParquetSource.for_trading_day`; trade count + sequence-identity sample, TOB-transition count, first/last instants; one attempt, no retries) — RUN ATTEMPTED ONCE: `DATABENTO_API_KEY` absent in the execution environment → clear-message exit 2, no report; the one-shot check remains to be run when the key is present.
Commits: SC 40ecb0b..2c732ee (4 + this doc commit: cb3f637 P1f test · b393979 D-P-02 deletions · 7e7751d CI/lint/testpaths · 2c732ee route-seam script) · TL 81a54b2..c9e139b on `worktree-w2-operate` (06ed9eb P2 · a0dcb1f P1 · c9e139b P4b) · QL 393716d..12c50a5 (15f23f6 P3 · 12c50a5 P4b). Suites at close: SC **178** (177+1) + repo-root ruff clean; TL **403** (381+22 net) + ruff clean + frontend tsc clean + vitest **142**; QL **746** (744+2) + ruff clean. Per the window's "no validation harness runs" rule, SC's close pass executed `tests/` and proved `validation/` COLLECTION (the data-dependent runs ride CI's loud-skip path); the b3/d1/decision-diff gates were not re-run (no SC engine-semantics change this window — W2 touched levels-test, validation lint, CI, and a new script only).
Structural notes: TL `domain/trading_day.py` (ET 18:00 helpers) landed in the P2 commit (journal dependency) with P1 consumers following; app.py's P2 endpoint riders landed in the P1 commit (file-level coupling) — both flagged in the commit messages. The frontend DOES have a harness (vitest), contra the spec note — the three substring-trigger tests were mechanically repointed to the typed frame. No new DECISIONS.md ruling was needed; no design fork outside the spec was taken.
W2-FIX (2026-06-12, post-review): four findings — F1 TL live `_side()` word tolerances ("ask"/"bid") deleted (single-letter canon only; words now UNKNOWN). F2 TL warm-start Historical-fallback seam gap (clamped slice end vs live-subscribe instant) logged at WARNING where the drain completes. F3 TL activation checksum gate converged to this record's claim (mismatch names the bundle path-free; absent sidecar debug-only per D-P-01) + tampered-binary/absent-sidecar tests. F4 SC route_seam_check default symbol dir repointed to the canonical store (Claude-Quant-Lab/data/databento/NQ).

Known debt (recorded 2026-06-12, W3a doc-op; one line each):
- TL's serving fixture (`backend/tests/fixtures/strategy.json`: sl 30 / `16:15_US/Eastern_rth_close` / `level_representative_price`) and QL's contract-test fixtures (sl 30) pin superseded v1 label values; refresh to the v3 policy rides post-gate (after W3b green).
- Replay-harness store references still point at `Trade-Dashboard/data/databento/NQ` (b3 go-live/multiday readers) — same data as the canonical Claude-Quant-Lab store (route_seam_check already repointed at W2-FIX F4); harness repoint queued.

### W3a record (2026-06-12, landed LOCALLY — NOT pushed; awaiting review. TRAIN NOT LAUNCHED: P2 compute stop-gate fired)
Scope landed — QL: **P1 quote-pass vectorization** (`ef77885`): `process_single_date_stream`'s per-quote pure-Python span scan (O(quotes×touches)) replaced by chunked numpy window membership over epoch-ns (64Ki-event chunks, hull-bounded retention; SC feature formulas still consume the same `Quote` objects — single-source intact); slow path DELETED. **OUTPUT-IDENTITY PROOF** over two real days, `frame.equals` bit-identical: 2022-02-15 (2 rows; old 673.9s / new 655.7s) and 2026-02-18 (3 rows; old 1022.0s / new 1080.9s; new ran cold-cache first each day). Honest note: near-neutral timings — unseeded proof days yield few touches, so the old quadratic term was small THERE; the change bounds the many-touch (seeded) case, and the cost wall is elsewhere (below). **P3 plumbing** (`c6fc42c`): `run_walk_forward_training` gains `day_folds` (purged TRADING-day folds — the exact `train_dashboard_model` 40/5/5/2 logic emitted as `WalkForwardSplit`s; the exact label-horizon purge still runs on top) + `pinned_features` (exact list, validated, wins over RFECV); the session-experiment CLI gains `--fold-scheme purged-days`, `--fold-*-days`, `--min-train-events`, `--pin-features`; 4 new focused tests. **P5 docs** (`b8d2eb0`): D-036 (the ratified W3 config — verbatim block in QL `docs/DECISIONS.md`; window 2025-11-21→2026-02-13 = 73 store dirs selected, 61 weekdays + 12 inert weekend dirs, 2025-11-20 confirmed self-skipping at date discovery) + D-037 (quote feature RIDES the gate; the stub-exclusion pre-ruling superseded — the `quotes_in_window` stub is SC-plugin-path-only).
**P2 COMPUTE STOP-GATE: STOP.** Full per-day pipeline (post-P1, exact P3 config, fresh — config hash `7850272e`, no cache) on 2026-02-12: **1447.1s (24.1 min) → ×60 days ≈ 24.1 h >> the 90-min gate.** Attribution: ONE bare canonical-reader drain (`DatabentoParquetSource.for_trading_day().events()`, no runtime, no features) = **513.4s for 15,303,125 events (~34µs/event)**; the labeling pipeline makes TWO such passes (trades+runtime, then quotes), so ~17 min of the 24 is SC reader event decode — an SC-side cost, untouchable under this window's `src/strategy_core UNTOUCHED` constraint. Per the gate: **the train was NOT launched; no bundle exists; P4 (save+audit) did not run.** The W3 config stands RATIFIED (D-036) awaiting an owner ruling on the reader cost. Options for that ruling (none taken): (a) SC reader batch/vectorized decode (column-pruned arrow → typed arrays) — an SC window; (b) QL single-pass quote collection (trailing approach-window buffer during pass 1 — halves reader cost, needs its own identity proof); (c) accept a one-time overnight dataset build (per-day `ml_utility_<hash>` caches make reruns ~instant; ~24 h once per config).
Commits: QL `ef77885` (P1) + `c6fc42c` (P3 plumbing) + `b8d2eb0` (D-036/D-037); SC `9ff4f81` (P0 doc-op) + this record; TL `b27e2c0` (P0 housekeeping: merged `worktree-w2-operate` deleted; root recon/diff scratch gitignored). Gates at close: QL suite **750** (746+4) + ruff clean on the configured scope (the 13 known pre-existing root-scratch findings stand); SC suite + ruff (doc-only window) below; TL suite + ruff (hygiene-only) below. Evidence at QL root (untracked): `W3A_P1_PROOF.log`, `W3A_P2_GATE.log`, `scratch_w3a_p2_gate.py` (the re-runnable gate harness), `W3A_QL_DIFF.txt`/`W3A_SC_DIFF.txt`.

#### W3A-READER (2026-06-12, post-stop-gate; supersedes W3a-RESUME and the prior W3A-READER text. BUILD NOT LAUNCHED — launches after review, per the task's FULL STOP)
Reader-cost ruling executed under **D-P-15** (supersedes D-P-14's SC-freeze for this one component; D-P-14's remaining scope — L1 event cache, single-pass quotes, parallel day-pool — stays post-soak). Scope landed — QL **P0 zero-touch guard** (`0a03980`): `process_single_date_stream`'s vectorized approach-quote pass is guarded `if touches:` (empty → `approach_quotes` stays empty, the old per-touch loop's natural no-op; previously the hull `min()`/`max()` would raise if the early no-touch return were ever bypassed) + a zero-touch-day test (real one-hour slice, PDH/PDL seeded absurdly far above any stored price — levels exist but untouchable, approach pass ON, asserts empty frame). SC **P2 vectorized decode** (`332ad3e`): `DatabentoParquetSource`'s per-row `to_pylist`/`_normalize_row` decode replaced by a vectorized core — column-pruned pyarrow read (`ts_recv` dropped; decoded-and-discarded before), trade/L0 classification + exact-grid price validation + TOB-change dedup (shift-compare, state carried across batches AND files) + day-window bounds as numpy masks, canonical per-batch order via `np.lexsort` with an explicit emission index reproducing the row-wise stable sort's insertion order (a row's Trade item before its Quote item), identical `Trade`/`Quote` objects from extracted scalars (ns-unit columns emit ns-precision `pd.Timestamp` exactly as `as_py` did — the canonical order IS ns-precise; µs-floor window compare proven equivalent for whole-µs bounds). `events()` dispatches: ordered-disjoint windows (single path / the trading-day composition) → `_events_sequential` (concatenation; suppressed quotes never constructed); generic overlapping multi-path → the k-way heap merge + merge-layer dedup (the pinned canonical-interleave semantics), fed by the same vectorized scan. PUBLIC API unchanged; no DuckDB on this path. SC **P3c delete** (`37359ae`): row-wise path deleted on full green (the W3a P1 convention; the proof harness re-runs at `332ad3e`). **P3a IDENTITY PROOF** (`W3A_READER_PROOF.log` at SC root, untracked; harness `scratch_w3a_reader_proof.py`): full-trading-day event-by-event old-vs-new — 2022-02-15 **IDENTICAL, 5,218,914 events** (trades 378,369 / quotes 4,840,545 / warnings 0); 2026-02-18 **IDENTICAL, 10,720,798 events** (trades 353,681 / quotes 10,367,117 / warnings 0); count + order + every field + ns-exact ts; compare pass ran cold-cache first, then both timed drains warm: **NEW 17.5s vs OLD 227.1s (×13.0; 3.36 vs 43.51 µs/event)** and **NEW 30.8s vs OLD 383.7s (×12.5; 2.87 vs 35.79 µs/event)**. **P3b DRIFT NET, all green, committed P2 tree**: SC **184** (tests + validation — b3 golive/multiday digest regressions on untouched fixtures, duckdb-streaming parity, decision-diff, d1 streaming-vs-batch, production-pair parity) + repo-root ruff clean; QL **751** (750+1, consuming the new reader via the editable install); SC re-ran **184** + ruff clean on the committed post-delete tree. **BUILD PROJECTION** (honest): new drain projected on the gate day 3.36 µs/event × 15,303,125 = **51.4s** → per-day pipeline 1447.1 − 2×(513.4 − 51.4) ≈ **523s** → **×60 ≈ 8.72 h** (was 24.1 h) — still above the 90-min gate; the residual ~420s/day is the NON-reader pipeline (runtime drive + labeling + features), exactly D-P-14's post-soak scope; per-day `ml_utility_<hash>` caches make same-config reruns ~instant. Documented edge deviations (unreachable on store data; zero-warning tallies attest): inf-price / out-of-range-ts / uint64-overflow cells warn-and-skip the ROW where the old path aborted the FILE. Evidence: SC root `W3A_READER_PROOF.log` + `scratch_w3a_reader_proof.py` + `W3A_READER_SC_DIFF.txt`; QL root `W3A_READER_QL_DIFF.txt` (P0 is its own QL commit — separate diff, not folded). Launch command (verbatim, from QL root, after the review go — dry-run verified to resolve the exact D-036 config, 73 store dirs 2025-11-21→2026-02-13):
`PYTHONPATH=src python scripts/run_dashboard_session_experiment.py --preset all_to_ny --symbol NQ --bar-type 147t --start 2025-11-21 --end 2026-02-13 --tp 15 --sl 15 --interaction-window 5 --include-approach-features --approach-window 15 --fold-scheme purged-days --fold-train-days 40 --fold-test-days 5 --fold-step-days 5 --fold-purge-days 2 --min-train-events 30 --pin-features int_time_within_2pts,int_absorption_ratio,app_avg_trade_size,app_large_trade_vol_pct,app_max_spread --iterations 1000 --depth 6 --save --allow-failed-gates --model-name NQ_W3_$(date -u +%Y%m%dT%H%M%SZ)`

#### W3a BUILD → W3b GATE → READER VALIDATION (2026-06-13 → 2026-06-17; landed LOCALLY — push pending)
The build ran after the review go. **W3a bundle BUILT** on the ratified D-036 config (the verbatim launch command above), fed by a **parallel per-day cache warmer** (QL `aa05334`; per-worker RSS bounded via `max_tasks_per_child`, `5eb6f5b`) over the `ml_utility_<hash>` day caches — artifact **`NQ_W3_20260613T055600Z`** (the W3b parity-gate ARTIFACT, tracer dye under D-P-01 — its OOS edge is not a performance claim). **W3b GATE built + run** (TL `fb26643` per-touch batch↔serving parity gate + falsification · `d96094f` crash-resumable window runner + parity report · `099a1a5` Finding-1 `classify_serving_only` reconciling the deliberate `<5-interaction-print` serving asymmetry): the harness replays the full **73-day D-036 window** through the TL serving stack and re-derives the QL training-cache rows per touch. Full-window result: **236/236 cache touches BIT-EXACT** on every axis (features tol 0, label, level price, mfe/mae, proba, eligibility, ns-exact ts) with **ONE RED — 2026-02-12**: serving emits 5 surviving touches; the frozen cache has 4 (those 4 exact) + a 5th `pdl|long` (10:54 ET) the cache lacks.
**Root cause (resolved):** the 02-12 day cache was a **None-seeded standalone-build cache** — that day was built standalone and **skipped by the warmer**, so the rolling prior-day PDH/PDL seed was absent (None); the unseeded level set dropped the PDL first-touch that the seeded serving path detects. NOT a reader fault. Fixed by **regenerating the day with the correct (5-touch) seeded cache**, and guarded permanently by QL **`098e354`** (`build_utility_dataset` now refuses seedless / wrong-seed day caches). **`098e354` + the 6 preceding W3a commits** (`ef77885` · `c6fc42c` · `b8d2eb0` · `0a03980` · `aa05334` · `5eb6f5b`) **reviewed and greenlit; push pending.**
**Two conclusions from design review (stated explicitly):**
- **(a) The bundle AND the entire W3b gate ran on the STALE 583-line site-packages `strategy_core` reader — NOT the validated vectorized repo reader.** Both train (QL) and serve (TL) resolved `strategy_core` from the same site-packages install (the pre-vectorization 583-line `databento_parquet.py`), not the SC repo at `37359ae`. So the gate's bit-exact green proves **CONSISTENCY on a shared, unvalidated reader — NOT correctness** against raw ground truth. (The 02-12 RED and its seed root-cause stand independently of which reader ran.)
- **(b) The vectorized reader (SC `37359ae`) is now validated CORRECT against raw ground truth.** Per **`READER_CORRECTNESS_PROOF.md`** (Trade-Lab repo root, 2026-06-17): 23/23 reader + 178/178 SC tests green, imported from an isolated `37359ae` worktree (NOT site-packages); byte-faithful fidelity (price = dollars/0.25, ns-exact `ts_event`, side, bid/ask/sizes) for first/last/mid-session/session-seam events across dense (2026-02-12), thin (2025-11-28), and session-boundary (2026-02-09) days; exact row→event completeness over a **full 1,968,223-event trading day** plus bounded early/seam/end windows on all three days **including the 159,256-event window straddling the disputed 10:54 ET PDL touch** — no dropped rows, no spurious extras, no mis-valued or mis-ordered events. Verdict: **VECTORIZED READER CORRECT**.
**IN FLIGHT:** redeploy the vectorized reader (SC `37359ae`) into both consumers, **rebuild the W3 bundle on it**, and **re-run the W3b gate** against that rebuild — so train + serve + gate all sit on the validated reader. LOCAL; push pending. **[DONE 2026-07-03 — see the W3b CLOSE subsection below.]**

#### W3b CLOSE — vectorized-reader adoption on the reduced-coverage re-gate (2026-06-17 → 2026-07-03; PUSHED at the 2026-07-06 W3b-land greenlight) [D-P-16]
The IN-FLIGHT items above are DONE: the W3 bundle was REBUILT on the validated vectorized reader — the `7850272e` day caches re-warmed on it (`W3A_WARM.log` final DONE 2026-06-17T22:06Z: wall 24.7 min, counts {EMPTY: 14, OK: 43}) and the D-036 train re-run → artifact **`NQ_W3_20260617T220752Z`** (42 OOS rows vs the 06-13 bundle's 41; tracer dye under D-P-01, unchanged) — and the W3b gate re-run against that rebuild, so **train + serve + gate all sit on the validated reader**. TL `w3b/window.py` `BUNDLE_ID` repointed to the rebuild.
**Coverage is REDUCED, stress-weighted, and stated from the run artifacts — never inferred** (ratified **D-P-16**; the 06-16 full-73-day 236/236 run REMAINS stale-reader CONSISTENCY evidence only):
- **30-day journal base** (`backend/data/w3b_journal/`, serial + resume, 2026-06-17→06-18): the contiguous window **2025-11-21 → 2025-12-17** (23 days incl. thin 11-23/11-30/12-07/12-14) + **12-18** + **12-23** + the spread sample {12-28ᵗ, 01-01ᵗ, 01-06, 01-11ᵗ, 01-15} (ᵗ = thin). Re-scored READ-ONLY from the journals at land (parity `diff_day` directly — no replay, journals untouched): **HARD-GREEN — 92/92 matched (23 cache + 7 thin days), 0 mismatches on every axis (feature/label/excursion/price/instant/proba/eligible), 0 drops, thin 0==0 clean, max diffs 0/0/0.**
- **Dense 7-day set** {12-18, 12-23, 01-20, 01-29, 02-03, 02-12, 02-13} (6 days ≥1 GB + the light control), full recompute (`--no-resume`), isolated journal bases: **29/29 matched, 0 mismatch, HARD-GREEN at BOTH `--workers 2` (87.6 min) AND `--workers 4` (78.1 min), per-day rows IDENTICAL across the two configs** — worker-count nondeterminism ruled out. Reports: `data/w3b_worker_bench7_w2.txt` / `data/w3b_worker_bench4_w4.txt`.
- **2-day worker bench** (12-18 + 12-23): 8/8 HARD-GREEN at workers=1 AND workers=2 (`data/w3b_worker_bench_w1/_w2.txt`; `data/w3b_bench/BENCH_SUMMARY.md`). **Official gate config: `--workers 2`** — w=2 runs each day at ~solo speed (clean 1.4×→~2× wall win); w=4 REJECTED (heavy days degrade 1.24–1.60×, RSS ×1.8, for +11% wall).
- **The two previously-problematic days are the point of the spread:** **2025-12-18** (the prior end-of-stream wedge) completes to terminal `state=completed` — 13,483,063 events, 2/2 matched, watchdog silent. The wedge was a harness/runtime terminalization LIVELOCK, not data (`W3B_LIVELOCK_ROOTCAUSE.md`, TL root): the status-only busy-poll `_drive` hot-spinning `asyncio.sleep(0)` + a `BaseException` escaping the core's `except Exception` leaving `_state=RUNNING`. Fixed at BOTH layers — TL: task-aware `_drive` (awaits the worker task, categorises its exit, 120 s no-progress watchdog, `ReplayTaskFailed` keeps `run_window`'s RED-day-and-continue contract, interrupts abort raw) + interrupt-exact `run_window`; SC: `finally` liveness guard in `ReplayRuntime.start()` (**`f9a1f63`**) — with deterministic regression tests in both repos (SC 1 + TL 8 `_drive`-exit cases + TL 5 `run_window`-contract cases). **2026-02-12** (the 73-day run's stale-cache RED) is **5/5 matched in BOTH dense-set configs** on the regenerated seeded cache (QL `098e354` guard).
- Watchdog (`W3B_DRIVE_WATCHDOG_S=120`): fired **0** times across every run above.
- **Distinct days re-gated on the new reader + rebuilt bundle: 35 of the 73-day D-036 window** (the 30-day journal base ∪ the dense set). The remaining 38 days are ACCEPTED RISK under D-P-16: reader correctness vs raw is proven independently (`READER_CORRECTNESS_PROOF.md`), batch≡stream drift is empirically discharged on the densest + BOTH previously-problematic days, and the 73-day stale-reader run already proved the shared pipeline deterministic end-to-end.
Also in this land (TL, non-gate): the 2-full-prior-trading-day live warm-start via the Historical API (the live replay-start subscribe path DELETED — a 2-day start always exceeds the gateway's ~24 h intraday-replay cap; `recent_closed_bar_limit=8000`) and the chart batch (two-day retention 8 000 bars, warm-up-aware viewport — incremental appends, settle-then-fit, scroll-back pinning — and inline marker labels restored with an enlarged glyph, reversing `77ec617`'s hover-only call). Pins to SC `f9a1f63` (the latest consumer-facing commit, per the 9.6 convention — doc commits do not move pins).
**Land self-verify (run at stage-close on the committed land trees; recorded here at the 2026-07-06 greenlight):** SC **185 passed** (incl. the validation harnesses: b3 golive/multiday digests, duckdb-streaming parity, decision-diff, d1 streaming-vs-batch, production-pair parity) + tracked-tree ruff clean (repo-root run: 3 findings, all in untracked root scratch — standing, the known pattern); TL backend **441 passed, 1 skipped** + ruff clean; TL frontend **tsc exit 0** + vitest **154 passed**; QL **755 passed** + ruff clean (editable SC install — pin RESOLUTION deliberately deferred to the CI witness). **PUSHED at the W3b-land greenlight 2026-07-06** — post-review additions are exactly this doc-correction commit + the TL REPORT.md historical marker; no reviewed commit amended (reviewed tips: SC `fc77a7a` · TL `1050f14` · QL `3f451bd`).

### Status

**STATUS (DOC-SYNC, 2026-07-25) — THE single current-window pointer. Every other "Current:" / "Current window:" claim in this file, above or below, is historical record of its own moment, not live state.** The platform arc is **COMPLETE THROUGH INGEST**: every window W1 → INGEST is GREENLIT + PUSHED, CI green on each pushed tip, and both consumers pin SC **`9d49353` ×2**. **No window is in flight.** Next arc: **deployment-model training against the prop-sim objective** — not yet opened; as of this doc-op nothing is pre-registered, built, scored, or saved for it (newest bundle on disk remains `NQ_W3_20260617T220752Z`, 2026-06-17).

Phases A–E3: COMPLETE. W1: COMPLETE (pushed; pins bumped; CI witnessed). W2: COMPLETE (pushed; pins held `256020c` — no consumer-facing SC change; CI ×3 green incl. SC's first run; W2-FIX + the TL lint commit `5a8d28a` recorded). W3: COMPLETE (pushed at the W3b-land greenlight; CI witnessed below) — **W3a bundle REBUILT on the validated vectorized reader (`NQ_W3_20260617T220752Z`, D-036 config); W3b DONE on REDUCED, stress-weighted coverage (D-P-16): batch≡serving HARD-GREEN — 30-day journal base 92/92 + dense 7-day set 29/29 at BOTH workers=2 and 4 (per-day rows identical) + 2-day bench 8/8; 0 mismatches on every axis in every run; watchdog silent; 12-18 (the prior wedge — a harness/runtime terminalization livelock, fixed at both layers + regression-tested: TL `_drive`/`run_window`, SC `f9a1f63`) and 02-12 (the prior stale-cache RED — seeded regen + QL `098e354` guard) both GREEN; the earlier full-73-day 236/236 run stands as STALE-READER CONSISTENCY evidence only. Reader ADOPTED as THE reader (D-P-16); pins at `f9a1f63`.** [HISTORICAL as of the W3b land — the then-current window was **QL-UI-PARITY** (QL-only; UI-wiring to train the D-036 bundle from the Workbench — the TL visibility half of worklist item 2 was delivered by the W3b land: markers/warm-up/viewport, per the deleted BACKLOG entry rationale); SUPERSEDED by the DOC-SYNC STATUS line above. The pin figure `f9a1f63` in this paragraph is likewise historical: pins moved `f9a1f63 → 1650327 → 3d4193e → 9d49353` across SEED / EXEC / INGEST.] S9.9, F1–F3: PARKED behind W3 green + soak. Live model outputs remain DECORATIVE pending the serving-side soak (D-P-12 pre-registration) — the W3b gate is banked; the soak is not.

**CI witness (W3b-land greenlight, 2026-07-06):** SC `ci` / TL `backend-ci` / QL `ci` on the pushed tips — the TL and QL runs cold-install `strategy-core` resolving the NEW pin `f9a1f63` (the pin-resolution witness the land self-verify deferred). SC ci run 28813805822 (#3) success · TL backend-ci run 28813819792 (#7) success · QL ci run 28813836317 (#6) success — all on the pushed greenlight tips (SC 0f7599b · TL 923b29a · QL 3f451bd); TL/QL cold-installed strategy-core @ f9a1f63 on fresh runners (the deferred pin-resolution witness, banked).

#### QL-UI-PARITY — the ML Training Workbench trains the D-036 bundle (2026-07-06; QL-only, LOCAL — NOT pushed) [GREENLIT + PUSHED 2026-07-06 — the owed CI witness: QL `ci` run 28817637012 (#7) success on `0b4a2e8` (push-triggered) · SC `ci` run 28817731288 (#4) success on `108d1a7` (workflow_dispatch; the push did not auto-trigger). Pins unchanged (QL-only window).]
**Scope:** UI-wiring only, per the QL_UI_TRAIN_GAP_RECON.md work order — the training/save core is UNTOUCHED (both recon passes proved `run_walk_forward_training` already had `pinned_features=`/`day_folds=` kwargs and `save_trained_model` already had `allow_failed_gates=`; the UI simply never passed them). QL commits on `platform-refactor` off base `3f451bd`: **`e3ea980`** (feat: `resolve_training_kwargs` pure module-level kwarg builder — empty pin ⇒ None, non-empty pin ⇒ verbatim selection order + RFECV forced off, calendar ⇒ `day_folds` None, purged-days ⇒ the 40/5/5/2/30-shaped int dict; pin-features multiselect over the dataset's `int_`/`app_` preview universe with disabled "Build the dataset first" placeholder; explicit RFECV checkbox; fold-scheme selectbox + five purged-day number_inputs; all threaded as `day_folds=`/`pinned_features=` into the single train call + `rfecv_enabled` into the utility ModelConfig), **`44b1327`** (8 unit tests on the pure seam), **`0b4a2e8`** (review fix: `st.rerun()` after a successful dataset build — without it the pin multiselect stayed placeholder-disabled on the build run while Train was already clickable, silently training unpinned).
**DELIBERATE DEFAULT CHANGE (ratified here):** utility-mode RFECV was implicitly ON whenever approach features were on (`rfecv_enabled=ml_approach`, the old `:2333` coupling); it is now an explicit "RFECV feature selection" checkbox defaulting **OFF**, disabled + forced-off display while a pin list is non-empty. Two ratified scope notes: (i) the pin/fold widgets render in **utility mode only** (the `int_`/`app_` universe and the purged trading-day scheme are utility concepts; the literal spec text stated no mode gate) — extrema behavior adversarially verified byte-identical; (ii) a checked RFECV is reset to off by a pin→unpin cycle (keyed-widget cleanup under the forced-off display requirement) — accepted; the effective training value is never wrong.
**Adversarial review (4-lens workflow, 19 agents):** 5 confirmed / 10 refuted; the one functional major (missing rerun) FIXED in-window as `0b4a2e8`; the rest ratified/documented above.
**Acceptance (headless, evidence `QLUI_ACCEPTANCE.log` at QL root, untracked):** D-036 rebuilt through the SAME UI constructor path on the warm `7850272e` caches (config hash verified `7850272e`; dataset 237 rows → 169 training rows == reference; UI-default walk-forward sliders derive 30/7/1 == reference full_config). **REQUIRED 4/4 PASS** vs `NQ_W3_20260617T220752Z`: selected_features == the 5 contract features in order; strategy.json feature_set identical; evaluation.json fold dates (label_purge.folds — the spec's "fold_details" key does not exist on disk; adaptation reviewed) identical; OOS rows 42/42. **TARGET (model.cbm sha256) FAILED as specced, adjudicated:** same file size, exactly 40 differing bytes in 2 clusters = `model_guid` (random per CatBoost run) + `train_finish_time` (wall clock); ALL other 2,140,144 bytes identical including the full 1000-iteration learn_metrics_history; feature importances bit-identical; OOS predictions frame exactly equal (`check_exact=True`). Byte-identity is unachievable by construction; training is numerically identical. Temp bundle kept pending review adjudication (`models_qlui_acceptance_tmp/QLUI_ACCEPTANCE`).
**Gates (final tree `0b4a2e8`):** QL suite **763 passed** (W3b-land 755 + the 8 new unit tests) + ruff clean on src/tests/scripts (repo-root findings confined to untracked scratch, the standing pattern). SC receives exactly two doc commits this window (`4540578` open — the owed W3b CI witness ids — and this close record). TL untouched. **NOT pushed (work-order FULL STOP).**

---

#### SEED-PARITY recon (2026-07-06; read-only doc-op — evidence `SEED_PARITY_RECON.md` at the TL root) — verification half of `verify-prior-session-levels` CLOSED

**Verdict:** QL training's rolling `prev_full_hl` carry is CORRECT — tick-exact against canonical prior-day full [18:00 -> 18:00)-ET extremes (ground truth = the adopted D-P-16 SC reader, max/min of `Trade.price_ticks` over `for_trading_day`) on **7/7 probe days**, including the Presidents'/MLK short sessions, the Christmas empty-window carry-through (12-25 -> 12-24), the Sunday-file carry (2026-01-11 -> 2026-01-09), the 2025-11-20 store-hole (11-21 seeds from 11-19), and an old-regime NQU5 day; an **independent pyarrow re-computation agreed on every day including exact trade counts** (front-month election by trade count vs TickStore's all-row count did not bite on any probe). The TL **dashboard replay is structurally UNSEEDED**: no seed call anywhere on the `POST /api/v1/replay/start` path (exhaustive grep, every hit classified), a fresh plugin per `runtime.reset` (rebuilt `StrategyCoreService`), and the single-day replay window can never day-roll — PDH/PDL levels/zones never exist during dashboard replays (only asia/london extremes emerge organically). The **verification half** of `verify-prior-session-levels` is CLOSED on this evidence; the **build half** (seed dashboard replays from the canonical store walk; QL cache-stamp churn fix) is the SEED window, opened by this commit.

**Adjacent facts banked:** (i) QL `build_utility_dataset` stamps a day-D cache with day-D's OWN H/L (write after the carry reassignment) while the `098e354` read guard expects the seed ENTERING D — builder-written caches self-invalidate on the next run (rebuild churn, content stays correct; the warmer's stamp convention is the matching one) — fix rides the SEED window; (ii) the LIVE seed's weekday-only `prior_trading_day` key + skip-on-empty-fetch (no backward walk) diverges from training's carry on holiday keys (e.g. 2025-12-26 keys the empty 12-25 window), papered over only by the 2-day warm-start's organic banking — appended to the Tier-1 live-reader audit item (BACKLOG).

---

#### SEED — dashboard replays get the training-parity PDH/PDL seed; QL cache-stamp churn fixed (2026-07-06; cross-repo, PUSHED)

**Scope (evidence base `SEED_PARITY_RECON.md` at the TL root; its §5 probe values are this window's test oracles):** SC gains ONE additive module — `strategy_core/data/prior_day.py`: `PriorDayExtremes` + `prior_full_day_extremes(symbol_dir, trading_day, *, requested_symbol=None, max_walk_days=10)` — the recon §5 ground-truth computation verbatim (dated store dirs strictly before the day, descending, <= max_walk_days candidates; drain the canonical `for_trading_day` reader per candidate accumulating max/min `Trade.price_ticks`; first candidate with >=1 front-month trade wins; empty dirs/dayless dirs/trade-less windows skipped like QL's carry-through; exhausted -> None). NO engine-path change; frozen digests untouched by construction (the full-suite pass, incl. validation/, is the check). TL `HistoricalReplayService.start` seeds day-mode replays: AFTER `runtime.reset` (the rebuilt SC service would wipe an earlier seed) and BEFORE the core replay task starts (the summary is banked before the first event), via `asyncio.to_thread`; found -> `runtime.levels.load_prior_day_summary(extremes.source_day, ...)` keyed by the WALKED day (SC emission is most-recent-banked-below-D, so any key < D emits identically to QL's calendar-D-1 key — recon §4) + "seeded PDH/PDL from <source_day>" in the loading feed status; walk miss -> warning + proceed unseeded (QL cold-start equivalent); ANY seed exception -> warning + proceed (a seed problem never kills a replay); non-day-mode (synthetic) replays unchanged. The `requested_symbol` threaded into the walk is `ReplayConfig.requested_symbol` (the same value the runtime reset and the day-mode scan already use). QL `build_utility_dataset` now stamps each day-D cache with the seed ENTERING D (`entering_seed` captured before the carry reassignment) — the value the trust check compares against on the next run and the warmer's convention; pre-fix the builder stamped the post-update carry (day D's OWN H/L), so every builder-written cache self-invalidated on the next run (recon §3(d) rebuild churn; content was never wrong — rebuilds used the correct seed).

**Commits:** SC `60650bb` (window-open doc-op: recon verdict banked + owed QL-UI-PARITY CI ids) -> `f948065` (P1 module + tests) -> this close record. TL `7445af5` (P2 seeding + 3 tests). QL `820b532` (P3 stamp fix + test, red pre-fix). Deliverables: `SEED_SC_DIFF.txt` / `SEED_TL_DIFF.txt` / `SEED_QL_DIFF.txt` at the repo roots (base..tip), the adversarial-verify summary.

**Replay-start cost (recorded):** the threaded prior-day drain adds roughly 5-35 s before the first replay event (this session's probe timings on the canonical reader: ~7 s for a 180 MB day, ~25-35 s for 0.7-1.9 GB days; the recon's §5 instrumented total was ~186 s across all probe steps — attribution corrected by the adversarial verify), surfaced to the operator in the feed status seed note; cacheable later if it annoys.

**w3b harness interaction (recorded):** `headless_replay.py` passes `trading_day`/`symbol_dir`, so gate replays now ALSO get the service seed; its `_SeedingSource` still seeds during `scan()` — after the service seed — under key calendar D-1 >= the walked key, so on every day with a non-None QL carry the harness's entry wins the most-recent-banked lookup — with values proven tick-identical on every recon-probed day (7/7; the front-month election difference — reader trade-count vs TickStore all-row — did not bite on any probe but is unproven on roll-week days, recon §5): banked gate evidence unchanged. The one divergence is a window's FIRST day (e.g. 2025-11-21 in D-036): its cache was built with a cold None seed, but a re-gated replay now banks 11-19 extremes from the all-store walk — re-gating that day requires regenerating its cache under the all-store seed (or accounting for the delta). With seed values proven identical on every recon-probed day (and the roll-week election caveat above), dashboard replays are the w3b harness-equivalent on the proven surface, and the W3b gate evidence transfers to dashboard replays on that basis.

**Gates (pre-verify trees):** SC **190 passed** (incl. the 5 new prior_day tests; validation/ digests green) + ruff clean (src/tests/scripts). TL backend **444 passed / 1 skipped** (incl. the 3 new seed tests) + ruff clean. QL **764 passed** (763 + the new stamp test) + ruff clean. `verify-prior-session-levels`: **CLOSED** (verification half by the recon, build half by this window; BACKLOG entry graduated). **Pins:** bump to the new SC tip at the greenlight (consumer-facing: TL imports `strategy_core.data.prior_day`).

**Pushed (2026-07-06, greenlight):** SC `1650327` · TL `c92f13b` (pin bumped f9a1f63 → 1650327) · QL `75f83dc`. CI ×3 green with pin resolution witnessed: SC ci **28839878234** #6 success on 1650327 · TL backend-ci **28839902876** #8 success on c92f13b · QL ci **28839925480** #8 success on 75f83dc; both consumers' cold installs resolved strategy-core @ 1650327.

**Adversarial verify (mandatory close gate, 2026-07-06):** read-only 25-agent workflow (5 lenses x find, then per-finding adversarial refutation) against the exact window commits — 20 findings, **18 CONFIRMED / 2 REFUTED**. Fixed in-window: TL `91e4537` — the 5-35 s seed drain had turned three previously-instantaneous `start()` gaps into real races (concurrent second start passed the `_task` guard; `status()` reported the PREVIOUS run's stale COMPLETED for the whole drain, which also punched through the app-level live/replay 409 exclusion; a mid-drain `stop()` was silently overwritten) — closed with an in-flight `_starting` flag, dropping the stale core handle first, and honoring `_stop_requested` post-drain; the seed try now also covers the banking call (the "ANY seed exception" claim is literally true) — all four pinned by new tests. SC `a4969a0` — non-positive `max_walk_days` walked all-but-|n| candidates (slice semantics; now walks nothing), lenient `date.fromisoformat` dir names consumed walk slots (now strict `YYYY-MM-DD` round-trip), docstring parity claim scoped to the recon-probed surface; the carry-through skip branch is now CI-runnable synthetically (out-of-window-rows + quotes-only candidates). Doc corrections in THIS commit: the two close-record overclaims ("guaranteed by the recon proof" scoped to the 7/7-probed surface with the roll-week election caveat; the cost figures re-attributed to this session's probe timings), the stale Tier-3 QL-Training-UI BACKLOG item removed (delivered by QL-UI-PARITY), and the warmer stamp-test gap filed as Tier-2. Report-only residue: QL empty-output days write no cache and rebuild each run (pre-existing, known-accepted warmer behavior); TL `ReplayStatus` counters during LOADING read from the internal fields (post-fix truthful). **Gates (final trees, post-fix):** SC **194 passed** + ruff clean · TL backend **447 passed / 1 skipped** + ruff clean · QL **764 passed** + ruff clean (unchanged).

---

#### Live post-drain wedge — root cause banked (2026-07-07; doc-op, opens the TL WARM-FIX window)

The silent post-drain live stall (first observed as WARM_PERF_RECON's anomaly: 45+ min of
`warm_start_state:"warming"`, counters frozen at the warm total, feed "connected", zero live events, no
error) was captured and **reproduced deterministically (2/2)** under DEBUG instrumentation — evidence
`WEDGE_CAPTURE.md` at the TL root. Root cause has three blind layers:

1. **Cross-thread transport writes in databento-python.** `Live.subscribe()`/`Live.start()` execute the
   gateway writes on the CALLING thread (`session.subscribe` → `protocol.subscribe` →
   `transport.writelines`; same for `start`'s `transport.write` pre-0.79), while the transport belongs to
   the SDK's private `databento_live` event loop — asyncio transports are not thread-safe. TL's
   post-drain `_connect` (`databento.py:362`) runs on the uvicorn MainThread, so all six post-auth writes
   raced the loop thread's auth-completion callback (~1 ms window). The capture shows CRAM auth succeed
   (its writes run ON the loop thread) and then **zero inbound bytes ever** — no records and no
   heartbeats despite the negotiated 30 s interval — i.e. the gateway never received subscribe/start.
   The SDK's thread-safe paths (`stop()`, `call_soon_threadsafe(transport.close)`) worked instantly
   mid-wedge, isolating the unsynchronized writes as the failing pair.
2. **SDK watchdog blind at `math.inf`.** The SDK's own gateway-timeout monitor computes
   `gap = loop.time() − _last_msg_loop_time`, but `_last_msg_loop_time` initializes to `math.inf` and is
   only set by `received_record` — a session that never receives its FIRST record has gap = −inf
   forever: no timeout, no reconnect, no exception. The SDK cannot self-heal exactly this failure.
3. **TL status blind by construction.** FeedStatus CONNECTED is asserted before any live byte arrives,
   `warm_start_state` flips only on a post-anchor event (which never comes), and nothing compares
   last-event age to wall clock — the operator surface stays green over a dead feed.

Upstream verdict: databento **0.79.0** (2026-06-02) fixed the `Live.start()`/`terminate()` half
("thread-unsafe behavior … which would call methods from the client's event loop in the main thread");
`subscribe()` writes **remain caller-thread as of 0.81.0** (verified from source). The TL WARM-FIX window
takes: SDK floor >=0.79 with host install 0.81.0, facade-level marshaling of subscribe/start onto the
SDK session loop (fail-loud if the loop handle is unreachable), a TL liveness watchdog (D-P-06
single-retry), the warm inference gate, the schema-scoped warm fetch, and a real backend logging config
(the wedge was also invisible because the deployment had none — WEDGE_CAPTURE §A.2).

---

#### WARM-FIX — live wedge fixed + warm gated + fetch scoped + logging (2026-07-08; TL window, CLOSED — LOCAL, not pushed)

**Commits (TL, ordered, base c92f13b):** `4d0eb81` P1 wedge fix → `6019bef` P2 watchdog → `e69937f` P3
warm gate → `0fcffa2` P4 scoped fetch → `850e361` P5 logging → `5a661ea` P6 verify fixes. SC: `7001f0c`
(window-open doc-op) + this close record. Work order: WARM_PERF_RECON.md + WEDGE_CAPTURE.md at the TL root.

**P1 (wedge fix + SDK verdict):** host SDK upgraded databento 0.71.0 → **0.81.0** (databento_dbn 0.49.0 →
0.62.0); upstream **0.79.0** fixed the `Live.start()`/`terminate()` half of the cross-thread write bug,
`subscribe()` still writes caller-thread as of 0.81.0 (verified from source) — so the TL facade now
force-connects with zero subscription writes (guarded private-handle access, LOUD failure if the SDK
shape moved) and marshals every subscribe/start onto the SDK session loop via call_soon_threadsafe with
a bounded wait. Floor declared as the new pyproject extra `[live] databento>=0.79` (SDK stays optional).
**P2 (watchdog):** post-drain silence beyond `TRADE_LAB_LIVE_WATCHDOG_SECONDS` (default 120) → loud
wedge-signature error + DEGRADED + the D-P-06 single-attempt reconnect; second silent episode → FAILED.
Disarms on the warm→live flip; liveness evidence includes the feed's provider-callback stamp (see verify
fix 1). **P3 (warm gate):** runtime suppresses predict+resolver-register+journal atomically for
observations whose ORIGINATING TOUCH predates the warm anchor (anchor-based after the verify pass);
everything else builds unchanged; default off (replay/tests keep predict-on-completion). Kills the
restart-duplicate mode="live" journal rows (WARM_PERF_RECON §2, measured up to ×10). **P4 (scoped
fetch):** trades keep the full 2-prior-trading-day span; mbp-1 starts at now − (max(contract-driven
buffer retention, settings baseline) + 10 min slack), read at fetch time (hot-swap staleness caveat in
the docstring); per-schema end<=start guard + availability clamp; both spans logged at INFO. **P5
(logging):** root→stderr with UTC timestamps at `TRADE_LAB_LOG_LEVEL` (default INFO), uvicorn.access
capped WARNING (uvicorn launched with `log_config=None` so its dictConfig can't undo the cap — verify
fix 5), databento at INFO / DEBUG when env DEBUG.

**Live smoke (2026-07-08 03:55-04:03Z, Globex open, NQU6, real gateway, new SDK):** POST→200 in
**19.8 s** (was 2 m 57 s); drain 966,315 warm events in ~116 s; **warm total 2 m 15 s vs ~20 min
pre-fix** (recon projected ~1.5-2 min / ~0.96M — both hit); **warming→live flip observed** (the exact
transition that wedged 2/2 pre-fix) with **20,789 live events** in the 5-min observation window,
last-event lag sub-second; the INFO span line read "trades from 2026-07-05T22:00Z, quotes from
2026-07-08T03:00:26Z (retention 45m + 10m slack)"; **zero journal rows** added (no model active — the
gate's zero-rows proof is the P3 test set); clean stop ("connection closed" in 1 ms).

**Adversarial verify (mandatory close gate):** read-only 35-agent workflow (5 lenses × find → 2
adversarial refuters per finding) against the exact commits — 15 findings, **10 CONFIRMED / 2 PLAUSIBLE
/ 3 REFUTED** (dedup → 6 distinct). Fixed in-window (TL `5a661ea`): (1) MAJOR heartbeat-blind watchdog —
the adapter drops gateway SystemMsg heartbeats below the liveness stamp, so a healthy quiet-market start
(weekend/halt) would double-strike into terminal FAILED; the feed now stamps
`last_provider_activity_utc` on every provider callback and the watchdog folds it in (the
WEDGE_CAPTURE §C.4 healthy-vs-wedge discriminator); (2) MAJOR reconnect-vs-replay collision — the
internal auto-reconnect could reset the shared runtime + arm the gate under a replay started during the
reconnect delay; it now checks the injected `_replay_is_active` predicate (audit #NN-2 extended to the
internal path); (3) watchdog strikes reset on operator start (stale-strike leak denied a fresh session
its retry); (4) gate seam-tail leak — warm touches whose windows cross the drain's end journaled
duplicates post-flip; the gate became anchor/origin-based; (5) uvicorn.access cap was silently undone by
uvicorn's default dictConfig (it names that logger); `log_config=None` now; (6) diverging per-schema
availability ends (>60 s) now warn instead of hiding inside the max-based seam stamp. Upheld-plausible
recorded: the P1 docstring's loop-block quantification corrected (~1-2 s connect+auth dominated).
**Report-only residue (pre-existing):** `replay.stop()` on an IDLE never-started service stamps the
shared runtime's feed status mode="replay", mislabeling subsequent live journal rows — filed here, not
window-introduced.

**Gates (final trees):** TL backend **466 passed / 1 skipped** + ruff clean; frontend tsc clean +
vitest **154 passed** (16 files). SC untouched by code (docs only). Deliverables at the TL root:
`WARMFIX_TL_DIFF.txt` (c92f13b..5a661ea), `WARMFIX_SC_DIFF.txt` (1650327..tip, docs only). **NOT pushed
(work-order FULL STOP).** Pins unchanged (no SC code change; TL pyproject gained only the optional
`[live]` extra).

---

#### WARM-FIX pushed annotation (2026-07-10)

The WARM-FIX close record above (2026-07-08) recorded "CLOSED - LOCAL, not pushed". The window has
since been GREENLIT + PUSHED: TL `origin/platform-refactor` = `5a661ea` with **backend-ci run
29073049585 = success** (push event, branch platform-refactor); SC `origin/platform-refactor` =
`6e94091` (docs only) with **ci run 29073067597 = success**. Pins unchanged (no SC code change in
that window).

---

#### REPORT - performance surface: journal aggregator + read-only endpoint + Performance page (2026-07-10; TL window, CLOSED - local commit `8e54ad1`, not pushed)

**Dual purpose:** the trader's reporting dashboard AND the D-P-12 soak adjudication artifact - one
implementation, two consumers. **SUPERSESSION recorded:** this replaces the earlier plan of a
QL-side adjudication script for the D-P-12 soak; adjudication now reads
`GET /api/v1/performance` (or calls `trade_lab.services.performance.aggregate_performance`
directly) instead of a bespoke QL script.

**Commit (TL, base 5a661ea):** `8e54ad1` - `services/performance.py` (pure aggregator; no
engine/registry/strategy_core imports), `GET /api/v1/performance` (read-only, per-request file
opens, 404 clean on missing journal dir), Performance page (top-level tab: cards row with
simulated-$ toggle at $20/pt labeled "simulated, 1-contract, no costs", cumulative curve + daily
bars, trading-day CALENDAR on Mon-Fri trading weeks with 18:00 ET day keys + week subtotals +
green/red intensity, per-class/level/session/drop/funnel tables, OOS-vs-journal panel when a
bundle is active, journal data-quality strip). SC untouched (this doc-op only).

**Recon facts built to (TL/REPORT_RECON.md):** ResolutionType is `tp_hit`/`sl_hit` ONLY - D1b
retired force-labels; flatten/cutoff/no-resolution surface as DROP rows with no exit price, so
they are excluded from net and bucketed by reason, never priced. Outcome rows carry no
session/direction/eligibility (prediction join via `prediction_id`, across day files - a 17:59 ET
prediction resolves into the next trading day's file). The OOS artifacts
(`oos_predictions.parquet` 41 rows, `evaluation.json`) carry NO MFE/MAE - the comparison shows
MFE/MAE journal-side only. Pricing proxy ladder: row tp/sl values > row `bundle_id` contract
under `TRADE_LAB_MODELS_PATH` > explicitly requested bundle contract > unpriced bucket. Trades
are dated by the OUTCOME's trading day; the funnel is prediction-cohort based (follows in-window
predictions to their eventual fate). Every rate carries numerator/denominator; whole-directory
anomaly buckets (malformed/duplicate-id/orphan/conflict/undated) are counted pre-filter.

**Gates:** TL backend **485 passed / 1 skipped** + ruff clean; frontend **170 passed** (17 files,
incl. 16 new viewmodel/calendar cases) + tsc + eslint clean. Live smoke against the real journal +
active bundle `NQ_W3_20260613T055600Z`: page verified in-browser (cards/curve/bars/calendar/
tables/OOS panel/$-toggle/month nav; zero console errors), model deactivated after.

**Adversarial verify (bounded close gate, 2026-07-10):** 6 agents total (the window cap) - 3 lens
finders (aggregator math vs the real journal schema; endpoint contract + failure modes; frontend
viewmodel + trading-day calendar math) + one refutation pass per lens on the finders' findings
only. **18 findings -> 15 CONFIRMED / 3 REFUTED** (refuted as unreachable given the real writer:
weekend-key intensity pollution, formatMoney "-$0", missing-session misclassification). **4 majors
FIXED in-window (TL `209f1d0`):** (1) non-UTF-8 bytes in any journal file 500'd every request
(UnicodeDecodeError past `except OSError`) - now salvaged via errors="replace" + counted in
`anomalies.decode_error_files`; (2) OSError-unreadable journal files silently vanished while
files_scanned claimed them read - now `anomalies.unreadable_files`; (3) non-dict
`quality_gates.gates` in evaluation.json raised AttributeError out of the WHOLE report - now
degrades the OOS section only; (4) PerformancePage fetch race (older all-bundle response could
overwrite the newer active-bundle one) - request sequencing, latest wins. **11 confirmed minors
REPORTED, not fixed:** null/mismatched-bundle outcomes under ?bundle= excluded without a scoped
counter (funnel/headline gap); scoped-drop exclusions under session/eligibility filters uncounted;
gated_hit_rate shows 0.0 (not null) when eligible_class is unresolvable; ?bundle= 404s for retired
bundles whose journal rows persist [FIXED as an EXEC P0 rider]; session filter domain-unvalidated
(typo -> all-zeros 200) [FIXED as an EXEC P0 rider];
_is_safe_bundle_id lacks the registry's Windows-drive-prefix check (cross-drive strategy.json read
under a tampered row bundle_id); NaN in outcome numerics nulls means / order-dependent median with
no anomaly flag; failed refresh leaves the stale report + noJournal panel rendered under new filter
labels; month cursor stays pinned to an empty month across filter changes; zero-net day renders a
1px green sliver below the axis; only-malformed-rows journal shows the "rows outside filters"
empty-state with the data-quality strip hidden. Post-fix gates: TL backend **488 passed / 1
skipped** + ruff clean; frontend **170 passed** + tsc + eslint clean.

---

#### REPORT pushed annotation (2026-07-10)

The REPORT close record above recorded "CLOSED - local commit `8e54ad1`, not pushed" (majors fixed
in `209f1d0`). The window has since been GREENLIT + PUSHED (REPORT_GREENLIGHT_REPORT.txt): TL
`origin/platform-refactor` = `209f1d0` with **backend-ci run 29077742228 = success** (push event,
branch platform-refactor); SC `origin/platform-refactor` = `17ee822` (docs only, this record + the
verify record) with **ci run 29077759730 = success**. Pins unchanged at `1650327` (no
consumer-facing SC change that window).

---

#### EXEC — paper execution layer: derived fills, positions, P&L as an observer of the observer (2026-07-10; cross-repo, CLOSED — LOCAL, not pushed)

**Commits:** SC `c81982e` (P0c doc-op: the REPORT pushed annotation above) + `3d4193e` (P1
accessor); TL `4411347` (P0 riders) + `a31e357` (P2 tracker) + `e7bb6fa` (P3 surface) +
`009889e` (P4 verify major fix). Evidence base: TL/REPORT_RECON.md (drop semantics),
TL/VIZ_RECON.md §5 (entry exists at `register()`, previously surfaced only at resolution).

**THE OBSERVER INVARIANT (stated, enforced, verified):** the paper-execution tracker has ZERO
influence on touches, inference, the resolver, or the prediction journal. It consumes the same
RuntimeUpdate stream the UI receives — observed once per broadcast at the WebSocketBroadcaster
choke point, clients connected or not — plus two READ-ONLY providers (the resolver's
`open_setups()` snapshot via `runtime.open_setup_views()`; the active contract's
ExecutionPolicy), and writes only its own `executions/<trading_day>.jsonl` beside the prediction
journal (same never-raises discipline). Nothing in the tracker can mutate serving state; its
`observe()` swallows everything.

**P1 (SC, additive):** `StreamingHonestResolver.open_setups() -> tuple[OpenSetupView, ...]` — a
frozen read-only projection (prediction_id, entry_price_ticks, entry_ts_utc, direction,
tp_price_ticks, sl_price_ticks) of the private open-setup state: the honest fill and the
barrier prices already implied at registration (LONG tp = entry + tp_points / sl = entry −
sl_points; SHORT mirrored — exactly the excursion rule). Integer ticks; `round()` absorbs float
representation only (fills and the production tp/sl offsets sit on the tick grid). Engine call
paths untouched by construction — accessor only — so parity digests unaffected. +4 tests
(fill/barriers per direction, registration drops never appear, resolved/flushed/reset disappear,
returned tuple is a point-in-time snapshot).

**P2 (TL tracker, `services/execution.py`):** pure state machine. OPEN: an ELIGIBLE prediction
whose setup appears in `open_setups()` (the resolver filled); ineligible predictions never
tracked in v1; the same-batch register+resolve race reconstructs from the outcome/drop row's own
honest entry (counted). CLOSE: `tp_hit`/`sl_hit` at the setup's barrier; terminal drops
(`no_forward`/`no_resolution`) at the tracker's last-seen trade print; registration drops
(`flatten`/`cutoff`/`no_fill`, entry null) mean the position NEVER existed (invariant counter if
violated, never raised). **THE TWO-COLUMN BRACKET = the execution-drag measurement:** optimistic
prices the exact honest anchor/barriers; conservative prices a 1-tick-adverse entry and a
1-tick-adverse sl exit (tp exit AT the barrier — the print requirement is already resolution
semantics; drop exits are real prints, unadjusted). The spread between the columns measures how
much of the observed edge survives minimal slippage: an edge that exists only in the optimistic
column is not tradeable. Sizing 1 contract at the contract's point_value (default 20). All
prices tracked in integer ticks for exact column arithmetic. **RESET semantics:** every runtime
reset (replay start `replay_reset`, live start `live_reset`, activation) clears open positions
with a `reset` journal row carrying the cleared prediction ids — no phantom carry, NO synthetic
closes (the activation path first broadcasts the old resolver's flush drops, which the tracker
CLOSES properly at the last print, then the reset clears only what could never resolve).
Live positions are live-originated only by construction (the anchor-based warm gate blocks
warm-REPLAYED touches).

**P3 (TL surface):** `position.opened`/`position.closed` typed WS frames (emitted AFTER the
prediction frames they derive from) + a snapshot `open_positions` block with live unrealized P&L
(both columns) against the tracker's last-seen print; price-anchored chart markers at the actual
FILL prices (lightweight-charts v5 SeriesMarkerPrice, `atPriceMiddle` — visually distinct from
every bar-anchored touch/observation/prediction/outcome glyph); an Executions panel
(open-position card: side/entry/both-column unrealized recomputed against the local latest
print/age on the event clock; closed table: entry/exit/points both columns/reason); the
Performance page gains a paper-execution summary card when execution files exist —
`aggregate_executions` is ONE pure function with counted buckets
(unreadable/decode/malformed/unknown/undated/outside-filters/missing-pnl), close rows filtered
like the journal and dated by their own exit ts, `None` until the tracker ever writes.

**P0 riders (TL `4411347`):** two REPORT verify minors fixed — the performance session filter now
validates against the plugin vocabulary (typo → 400, not all-zeros 200); a well-formed ?bundle=
absent from models_root no longer 404s (bundle_id row filter with no OOS panel — retired
bundles' journal history stays queryable).

**Adversarial verify (bounded close gate, 2026-07-10):** 6 agents (the window cap) — 3 lens
finders (tracker state machine vs resolver semantics incl. every drop reason; DTO/WS seam +
reset ordering; P&L arithmetic both columns) + one refutation pass per lens. **18 findings → 14
distinct: 1 MAJOR (confirmed by all three refuters) + 13 confirmed minors + 1 REFUTED** (a
policy-provider fault aborting an update's closes — the shipped providers cannot raise:
lock-protected committed registry reads + pydantic-validated contract fields). **The MAJOR,
FIXED in-window (TL `009889e`):** the live warm/lag throttle swallowed every market
RuntimeUpdate while `_live_streaming` was False (warm catch-up tail AND the mid-session >30s
stall relapse), and the tracker observes only broadcast updates — a catch-up-tail prediction
never opened, and a stall-window resolution left a position stuck open forever with no close
row (executions journal permanently diverging from the prediction journal). Updates carrying
predictions/outcomes/drops/resets are now ALWAYS forwarded to the choke point (a handful per
session — no flood risk); market-only updates keep the snapshot throttle; regression test pins
forwarded-vs-suppressed per delta kind. Two window-introduced doc statements the verify proved
false were corrected in the same commit (execution.py live-phase docstring; stores.ts closed-
table reconnect comment). **13 confirmed minors REPORTED, not fixed:** (1) cap eviction (>500
open backstop) leaves a dangling journal open row and the later resolution is silently ignored
(same trace gap in the registration-drop-while-open guard); (2) flat 0-point closes counted as
losses in aggregate_executions' win/loss split; (3) the same-batch fallback stamps entry_ts from
prediction.event_ts, diverging from the view's decision instant under the log-warned
offset-mismatch config; (4) a mid-replay activation broadcasts its reset frame ahead of the
replay's buffered pre-activation deltas (post-reset open+close attribution possible in the 50ms
flush window; activation-during-replay has no 409 guard); (5) WS backpressure drop-oldest can
discard a position.closed/model.reset frame for a slow client (phantom open card until
reconnect; backend journal correct); (6) the closed-executions table survives a reset missed
while disconnected (comment corrected; behavior reported); (7) the Performance $ card recomputes
dollars from headline point_value instead of the exact realized.dollars the backend ships
(diverges on multi-point-value journals); (8) activation flush closes appear in the UI then are
wiped by the following reset's clearExecutions (journal/Performance page retain them); (9) SC
OpenSetupView `round()` snaps non-tick-multiple tp/sl barriers off the true excursion trigger
(latent; production policy is tick-multiple; nothing validates multiplicity); (10) the tracker
mixes feed-grid bar ticks with contract-grid position ticks in drop exits/unrealized marks
(latent; garbage P&L only for a contract with tick ≠ 0.25, unreachable today); (11) the frontend
hardcodes 0.25 when recomputing the unrealized mark (same latent class; DTO carries no
tick_size); (12) aggregate_executions sums dollars independently of the points guard — a row
with points but no dollars silently diverges the two with no counter; (13) undated close rows
are summed uncounted when no day window is set (anomaly accounting is filter-dependent,
contradicting the docstring's promise).

**Gates (final trees):** TL backend **507 passed / 1 skipped** + ruff clean; frontend **187
passed** (19 files) + tsc + eslint clean; SC **192 passed** (+4) + ruff clean. End-to-end test
drives the REAL resolver → accessor → tracker → choke point → journal (honest fill, barriers,
frame ordering, never-opened flatten). Deliverables at the repo roots: `EXEC_TL_DIFF.txt`
(209f1d0..tip) and `EXEC_SC_DIFF.txt` (17ee822..tip). **NOT pushed (work-order FULL STOP).**
**Pins: bump BOTH consumers to the pushed SC tip AT GREENLIGHT — the OpenSetupView accessor is
consumer-facing (TL requires SC ≥ `3d4193e`).**

---

#### EXEC pushed annotation (2026-07-10)

The EXEC close record above recorded "CLOSED — LOCAL, not pushed". The window has since been
GREENLIT + PUSHED (EXEC_GREENLIGHT_REPORT.txt at the SC root): SC `origin/platform-refactor` =
`f2f0d16` (the docs-only close record atop the reviewed `3d4193e`, per the standing
close-record-rides-the-greenlight pattern) with **ci run 29101442670 (#9) = success**; TL
`origin/platform-refactor` = `c9a06d5` (pin chore) with **backend-ci run 29101483167 (#11) =
success**; QL `origin/platform-refactor` = `76546b0` (pin chore) with **ci run 29101530109 (#9)
= success** — all three push-triggered on `platform-refactor`, no workflow_dispatch needed.
Pins bumped `1650327 → 3d4193e` in BOTH consumers (TL `c9a06d5` `backend/pyproject.toml`, QL
`76546b0` `pyproject.toml`; consumer-facing per the 9.6 convention — TL
`runtime.open_setup_views()` requires `StreamingHonestResolver.open_setups()`; the EXEC SC doc
commits do not move the pin), and pin RESOLUTION was witnessed in both consumers' cold-install
raw logs on those runs (`Resolved ... Strategy-Core.git to commit 3d4193e6bf3e...` in both).
Current window: **COCKPIT** — the trader-facing UI pass (TL frontend + ONE display-only backend
DTO addition; SC doc-ops only).

---

#### COCKPIT — trader-facing UI pass: strip, decision surfaces, chart cockpit, trade tape (2026-07-10; TL window + SC doc-ops, CLOSED — LOCAL, not pushed)

**Commits:** SC `a36b858` (P0 doc-op: the EXEC pushed annotation above + COCKPIT status line) +
this close record (docs only — NO SC code this window). TL, base `c9a06d5`: `07586d9` (P1
backend) + `30bc5b5` (P2 strip) + `b2f5172` (P3 decision surfaces) + `dbc8bed` (P4 chart) +
`b23cc57` (P5 tape).

**P1 (TL backend, display-only):** the model-status DTO gains the serving-gate parameters from
the active contract's InferencePolicy — `confidence_gate`, `eligible_class`,
`eligible_sessions` — all null when no model is loaded. `eligible_sessions` ships the RUNTIME
session vocabulary (`["ny"]`, not the contract's raw `ny_rth`) via `eligible_session_tokens`,
the display projection of `_session_matches`' leading-token rule kept beside the predicate so
the two conventions cannot drift; contract tests pin unloaded nulls, fixture values
(0.7 / tradeable_reversal / [ny]), deactivate-reverts, and token/predicate agreement. The gate
itself stays in `InferenceEngine.predict_for_observation`, stamped per-prediction as
`is_eligible` — the DTO never influences serving. **P1b level-origin investigation =
REPORT-THE-GAP (no code):** "Level origin: unknown" is NOT a DTO/normalize seam drop —
`origin_session` flows faithfully end-to-end; the panel read `levels[0]`, which is PDH by SC
emission order, and the adapter's `_level_origin` maps PDH/PDL to None by construction. The
PDH/PDL DAY-origin is computed-then-discarded inside SC `StrategyLevelState.levels()` (the
engine `Level` dataclass carries no source-day field), and seed-vs-organic provenance is
genuinely absent upstream (`load_prior_day_summary` and the organic day-roll write
indistinguishable summaries; `_SeedingSource` is w3b-harness-only). Threading it requires an SC
`Level` field — out of this window's scope; the display side is made honest in P3a
(`levelOriginLabel`: nearest level's origin; PDH/PDL with null origin render "prior day").

**DEVIATION (DTO budget):** the work order budgeted ONE backend DTO addition (the model-status
fields). The window shipped a SECOND display-only passthrough — `ObservationDTO.direction` —
because P3c requires direction on the active-setup card WHILE the observation is open, no wire
field carries it pre-prediction, and client-side re-derivation from `level_kind` is exactly the
documented audit-#NN-1 inversion bug (mixed-side merged zones). It passes through the
AUTHORITATIVE `Observation.direction` (null-safe for legacy observations), contract-tested;
zero serving influence.

**P2 (strip):** `TraderStrip` replaces `TopStatusBar` — large last price (newest print from the
forming/closed bar streams, forming wins wall-clock ties) with tick-direction flash; session net
change vs the trading day's `bar_index`-0 open (EXACT-OR-NOTHING: em-dash when bar 0 is
truncated out of retention — never an approximation); day high/low across the day's retained
bars; NY-open 09:30 and flatten 16:40 countdowns on America/New_York wall time via the Intl
timezone database with an inverse-lookup correction loop (NEVER fixed UTC offsets), switching to
"since" after passing, day-scoped — pinned by spring-forward (7h real) and fall-back (9h real)
transition-day tests. Ops pills compacted right. Safe Replay / Databento collapse to one status
line each once RUNNING (state chip · N events · last event) with Expand/Collapse.

**P3 (decision surfaces):** (a) levels sort by |distance| from the last print — signed
points+ticks per row, nearest highlighted, absolute price demoted; fixed kind order remains the
no-print fallback. (b) PredictionRow renders the gate math — eligible-class probability vs
confidence_gate ("0.82 / 0.70") with a filled bar + threshold tick, and WHY when ineligible,
derived client-side in priority order class > session > gate; rendered ONLY when
`prediction.modelId` matches the active model (hot-swap safe) and never overriding the backend
`is_eligible` verdict. (c) active-setup card while an observation is open: level kind/price,
touch price (joined via `originating_touch_id`, null-safe on a missed join — the reconnect
snapshot carries observations but no touches), authoritative direction, and a countdown to the
observation window end on the EVENT clock (latest print ts — replay runs at replay speed, a
paused feed freezes).

**P4 (chart):** (a) open paper positions draw TP (green) / SL (red) as large-dashed 1px price
lines on a dedicated overlay layer keyed `tp:/sl:<predictionId>`, removed when the id vanishes.
(b) session shading — translucent full-height bands (asia/london/ny) classified from bar opens
in ET per the SC v3 scheme, ET offsets Intl-derived with a per-UTC-hour cache (US DST
transitions land on UTC hour boundaries), rendered as a lightweight-charts v5 series primitive
(`drawBackground`, z-order bottom) with the band→pixel clipping pure and unit-tested. (c)
outcome markers RE-ANCHORED to the resolution bar (`resolved_ts`) per VIZ_RECON §3; touch and
prediction markers stay on the touch bar. (d) the decision timeframe tab is badged
"147t · decision", derived as min(supportedTimeframes) — the same rule the backend uses for
`ServingCapabilities.decision_timeframe_ticks`.

**P5 (tape):** the blotter is a trade tape — typed `TapeRow` payloads attached at WS ingestion:
prediction (class, predicted-class probability, gate verdict, direction, session), outcome
(resolution, correct/miss, actual class + realized points joined at RENDER time from the
executions store by prediction id, both bracket columns), drop (reason), position open (both
entry columns + tp/sl) and close (reason, both point columns, exit). Filter chips
all/predictions/executions/drops (untyped runtime events All-only; filtering precedes the
80-row render slice), newest-row flash, 200-event store bound unchanged.

**Gates (final trees):** TL backend **510 passed / 1 skipped** (+3 over EXEC: 2 gate-param + 1
observation-direction contract tests) + ruff clean; TL frontend **243 passed** (23 files; +56)
+ tsc + eslint + vite build clean. SC code untouched (doc-ops only); pins UNCHANGED at
`3d4193e` per the 9.6 convention.

**Adversarial verify (bounded close gate, 2026-07-10):** 6 agents (the window cap) — 3 lens
finders (ET/DST clock math incl. both 2026 transition days; DTO/normalize seam for the new
fields; store/viewmodel lifecycle across reset/reconnect) + one refutation pass per lens.
**7 findings → 4 CONFIRMED minors / 3 REFUTED, ZERO majors** (refuted: session-pill-vs-shading
divergence — the pill is SC-v3-fed through `strategy_core_service.snapshot().session` and agrees
with the shading at every minute; client session-predicate drift — unreachable over the closed
single-token session vocabulary; filter-chips-hide-the-reset-row — intended filter semantics,
not a regression). **4 confirmed minors REPORTED, not fixed:** (1) the countdowns are
calendar-day-scoped with no trading-calendar awareness — a weekend shows "since" for a
09:30/16:40 that was never a market event; (2) gate-reason text can render
"gate — 0.70 below 0.70" when the probability rounds up to the gate at 2dp (verdict correct,
text self-contradictory; reachable whenever p ∈ [gate−0.005, gate)); (3) TraderStrip
tick-direction refs survive model.reset — one stale cross-run flash and a transiently colored
em-dash after a reset drops the price; (4) outcome tape rows silently lose their realized-points
bracket after model.reset (clearExecutions wipes the render-time join source while blotter
events survive; neighboring close rows keep self-contained points — tape internally
inconsistent; also reachable via the 100-close cap inside the 200-event tape).

**Deliverables:** `COCKPIT_TL_DIFF.txt` (c9a06d5..b23cc57) + `COCKPIT_STATES.md` (the
strip/cards states description) at the TL root; `COCKPIT_SC_DIFF.txt` (f2f0d16..tip, docs only)
at the SC root. **NOT pushed (work-order FULL STOP).** Pins: no bump required at greenlight —
no consumer-facing SC change this window.

---

#### COCKPIT pushed annotation + COCKPIT-FIX close + ENV-FIX record (2026-07-10; PROP-SIM P0 doc-op)

**COCKPIT GREENLIT + PUSHED** (COCKPIT_GREENLIGHT_REPORT.txt at the SC root). The COCKPIT close
record above recorded "CLOSED — LOCAL, not pushed"; the window has since been pushed: TL
`origin/platform-refactor` = `b23cc57` (push `c9a06d5..b23cc57`; P1–P5 ancestor-asserted:
`07586d9`/`30bc5b5`/`b2f5172`/`dbc8bed`/`b23cc57`) with **backend-ci run 29109919564 (#12) =
success** (head `b23cc57e0d0…`, completed 2026-07-10T17:09:24Z); SC `origin/platform-refactor`
= `0e86cb5` (push `f2f0d16..0e86cb5`, DOCS-ONLY confirmed — diff touches only this file) with
**ci run 29109952671 (#10) = success** (completed 2026-07-10T17:09:31Z). QL untouched — no run
owed. Both push-triggered on `platform-refactor`, no workflow_dispatch. Pins NOT bumped: both
consumers still pin `3d4193e` (no consumer-facing SC change; 9.6 convention).

**COCKPIT-FIX CLOSED + PUSHED** (COCKPITFIX_GREENLIGHT_REPORT.txt at the SC root): four
owner-replay frontend defects, frontend-only, backend untouched, one TL commit `67e03e4`
(`fix(cockpit): owner replay defects…`, 13 files +491/−32; deliverable TL
`COCKPIT_FIX_TL_DIFF.txt`). Content: F1 chart/sidebar layout decoupling (viewport-only
`--workspace-h`, per-section internal scroll); F2 per-category tape retention (60 predictions /
60 executions / 40 drops / 60 untyped via the shared `tapeCategory` classifier); F3 predictions
pane 340px internal scroll, newest first; F4 display-only CT axis (America/Chicago via Intl,
synthetic-time → real wall-clock tick resolution). Adversarial verify pre-commit: **5 confirmed
/ 0 refuted, all fixed inside the reviewed commit** — incl. the MAJOR lightweight-charts
tick-label memoization (labels cached by (weight, time-key), flushed only by
`timeScale.applyOptions({})`, never `setData`; synthetic keys collide across timeframes) —
plus 4 recorded deviations (h:mm:ss seconds ticks; >1850px residual band; F2 test-infra
adaptations; `src/test/node.d.ts` shim). Pushed `b23cc57..67e03e4`, origin match, never
amended; **backend-ci run 29121846588 (#13) = success** on head `67e03e48c4b…` (backend
untouched — the run is the standing cold-install/pin witness). Frontend gates ran locally on
the committed tree: tsc --noEmit clean, eslint clean, vitest **261/261** (25 files). Pins
unchanged at `3d4193e` ×2.

**ENV-FIX EXECUTED** (ENVFIX_REPORT.txt at the SC root; closes the two READER_PIN_RECON risks):
strategy-core reinstalled **EDITABLE** into the shared system Python 3.13 — resolution proven
from BOTH consumer cwds to import the SC checkout src tree (`…\Strategy-core\src\strategy_core`)
with the VECTORIZED reader probe green; local runtime = working tree ALWAYS, the git pin stays
enforced by CI cold-installs (witnessed at every greenlight). SC checkout at fix time `0e86cb5`
(src byte-identical to pin `3d4193e`; the commits past the pin are docs-only). QL commit
**`f247046`** (`fix(acceptance): live Strategy-Core sys.path becomes opt-in (ENV-FIX)`): the
acceptance script's default `../Strategy-Core/src` sys.path insert is now gated behind
`QL_ACCEPTANCE_USE_LIVE_SC=1`, the summary self-documents `strategy_core_source`, two seam
tests cover both modes. Gates at fix time: pytest 4 files **59 passed**, ruff clean. `f247046`
is COMMITTED NOT PUSHED — **it rides THIS window's (PROP-SIM) greenlight.**

**PROP-FIRM RESEARCH + RATIFIED SIM-FIRST SEQUENCING:** the prop-firm evaluation-rules research
(TopStep 50K et al.) concluded in-conversation — no repo artifact; its ratified output IS the
PROP-SIM work order, parameters recorded here. **Sequencing (ratified): sim first, QL-side** —
the barrier-options walker (eval pass-probability from equity paths) is built in Quant-Lab as
`alpha_lab.propsim`, model selection is the FIRST consumer; TL Performance-page presets are a
LATER follow-up. **Preset one = TopStep 50K:** starting balance 50_000 / profit target 3_000 /
trailing drawdown 2_000, style `eod_floor_realtime_breach` (floor = max of prior EOD balances −
trail, ratchets on EOD only, breach checked in real time), floor LOCKS capped at the starting
balance / daily loss limit 1_000 SOFT (day halted, remaining trades skipped — not a bust) /
consistency 50% (best day ≤ pct × TOTAL profit — supersedes the alpha_lab-era
`config/prop_firms.yaml` comment "50% of profit target"; presets are data in a registry, additions
need no code) / no min-days / point_value 20.0. Both breach modes are always computed and
labeled: `realized_only` (equity at trade closes + EOD) and `unrealized_adverse_first` (each
trade's path visits entry − MAE before entry + MFE).

Current window: **PROP-SIM** — the barrier-options walker (QL `alpha_lab.propsim` module + CLI,
OOS-writer per-row outcome columns, TopStep-50K preset, day-level block-bootstrap Monte Carlo,
baseline evidence run; SC doc-ops only).

---

#### PROP-SIM — the barrier-options walker: pass-probability from equity paths (2026-07-10; QL window + SC doc-ops, CLOSED — LOCAL, not pushed)

**Commits:** SC `53b9b34` (P0 doc-op above) + this close record (docs only — NO SC code). QL,
base `76546b0`: `f247046` (ENV-FIX, pre-window — RIDES this greenlight) + `86654c7` (P1
OOS-writer columns, D-038) + `dbf73d8` (P2 walker) + `1ef0ebe` (P4 verify fix). TL untouched.
Pins UNCHANGED at `3d4193e` ×2 (no SC code this window; 9.6 convention).

**P1 (QL OOS-writer columns, D-038):** `oos_predictions.parquet` gains per-row `max_mfe_pts` /
`max_mae_pts` / `entry_price` / `resolution_type` on FRESH saves — threaded, not recomputed:
MFE/MAE pass through from the training frame's engine `OutcomeResult` values (captured
positionally at the fold seam alongside timestamps/sessions); `entry_price` is written into the
dataset row by the stream builder via the SAME injected trade-price accessor at the SAME
decision instant the engine used (`resolve_honest_outcome` computes-then-drops it; SC untouched
— the accessor call is the one expression its contract documents); `resolution_type` is the
ratified label mapping mirrored from TL serving (tradeable_reversal → tp_hit, trap/blowthrough
→ sl_hit). Existing bundles NOT retrofitted; frames/caches predating a column degrade it to NaN
(warm D-036 `7850272e` caches lack `entry_price` until a day rebuilds — the cache tag hashes
config, not row schema, deliberately). Canonical-schema test updated 11 → 15 columns; small-train
test asserts OOS values == the training frame's, plus a missing-columns degradation test.

**P2 (the walker, `src/alpha_lab/propsim/` — pure module + CLI):** loaders normalize three
sources to `TradePath{day, entry_ts, points_optimistic, points_conservative, mfe_pts, mae_pts,
resolution}` — (a) TL executions closes ⋈ journal outcomes on `prediction_id` (18:00 ET
trading-day roll mirrored from TL, trades dated by ENTRY), (a′) journal-outcomes EVIDENCE mode
(every resolved outcome as a 1-lot trade; tracker-mirroring conservative fill model — added
because the executions dir has zero fills on disk), (b) OOS parquet (post-P1 columns; pre-P1
degrades unrealized mode to realized-only with a stated reason; idealized fills — conservative
column EQUALS optimistic, stated). `Ruleset` dataclass exactly as ratified; preset registry
keyed by name, presets are data — **topstep_50k** = 50_000 / 3_000 / 2_000
`eod_floor_realtime_breach` / locks-at-start / 1_000 SOFT DLL / 50% consistency (best day ≤ pct
× TOTAL) / no min-days / point_value 20.0. ENGINE: days in order, trades in intra-day order at
1 contract; floor = max(prior EOD balances incl. start) − trail, EOD-ratcheted, never down,
capped at start when locked, breach ≤ in real time; BOTH breach modes always computed and
labeled — `realized_only` (closes + EOD) and `unrealized_adverse_first` (entry − MAE before
entry + MFE; on the falling adverse leg the floor and the DLL level are BARRIERS — the higher
one is touched FIRST: floor touch = bust, soft-DLL touch = force-close AT the DLL level, day
halted, remaining trades skipped, not a bust; hard DLL = bust); PASS at EOD when total ≥ target
∧ min-days ∧ best day ≤ pct × total (else keep walking — later days dilute). Outputs per run:
verdict / days_to_outcome / bust_reason / best_day_ratio / min_floor_distance. MONTE CARLO:
seeded day-level block bootstrap, whole days with replacement, walk-until-verdict with a
max-days runaway guard (default 1000), N default 10_000 → P(pass) (+ Wilson 95% MC CI), P(bust),
P(incomplete), days-to-pass median/p10/p90, days-to-bust median, bust-reason counts — per breach
mode × fill column, plus the as-sequenced historical verdict. CLI
`python -m alpha_lab.propsim` per the ratified form (`--source executions <dir> [--journal
<dir>] | --source journal <dir> | --oos <parquet>`, `--preset/--column/--n/--seed/--json`,
TP/SL resolve flags → bundle `strategy.json` `label_policy`). Oracle tests: floor lock at
start; EOD floor never moves down; a within-day MAE excursion busting unrealized while realized
survives THE SAME sequence; DLL soft halt skipping remaining trades without busting (+ the
force-close-at-DLL-level excursion variant + hard-DLL bust + floor-beats-DLL barrier ordering);
consistency blocking a pass until later days dilute; min-days; bootstrap seed determinism;
empty/degraded inputs.

**P3 (baseline, `PROPSIM_BASELINE.md` at the QL root, untracked — evidence, not a gate):**
preset topstep_50k, both columns, N=10_000 seed 42. Data reality stated exactly: the spec's
executions⋈journal leg has **0 trades** (all 93 execution rows are resets — every on-disk
prediction is `is_eligible:false`, and the tracker only opens eligible predictions), so a
journal-outcomes EVIDENCE run stands in: **49 deduped trades over 13 days** (80 outcomes − 31
warm-restart duplicates), win 30/49 = 0.612 (binomial 95% CI 0.472..0.736) → P(pass) ≈
0.989/0.990 optimistic, 0.973/0.981 conservative (unrealized/realized); as-sequenced: optimistic
PASSES day 13 at $53,300, conservative ends INCOMPLETE at $52,960 — **$40 short of target: the
tick-adverse fill model costs $340 over 49 trades and decides the sequence**. The 06-17 bundle
OOS (42 rows / 15 days, pre-P1 → realized-only, stated): win 17/42 = 0.405 (binomial 95% CI
0.270..0.555) → **P(bust) = 0.9984** every cell, as-sequenced BUST on day 6 — the walker turns
the known negative W3 OOS edge into an evaluation verdict. Gated subset (3 trades / 2 days):
P(bust) = 1.0, as-sequenced incomplete. Fidelity caveats recorded verbatim in the baseline: MFE/
MAE order unknown → adverse-first is conservative; OOS lacks excursions pre-P1; 42 OOS rows =
huge CI (binomial interval reported); no costs modeled; evidence-mode trades are all
serving-ineligible and mix replay/live days as exchangeable bootstrap draws.

**Verify (bounded close gate, 3 lenses × find + 1 adversarial refuter per finding):** engine
math vs the ruleset spec — **ZERO findings**; loader joins + bootstrap statistics — 3 CONFIRMED
/ 0 refuted, ALL FIXED in `1ef0ebe`: **PROPSIM-L1 (major)** journal evidence mode counted
warm-restart duplicate outcomes of the same physical touch as independent trades (2026-06-16:
36 outcomes = 8 touches ×10/×9/×9/×4; fresh uuids per restart defeat id-dedup) → touch-signature
dedup, last-write-wins, drop count surfaced — the baseline was RE-RUN post-fix (80 → 49 trades;
P(pass) 0.997 → 0.990 optimistic); PROPSIM-L2 (minor, latent) the same duplication class for
executions files across replay re-runs (append-only, resets carry no epoch key) → fill-signature
dedup + note; PS-1 (minor) a NaN `points` row crashed `format_human` past the win_rate-only
guard → loaders reject non-finite numerics at the boundary + the report guards every formatted
field. Wilson math, percentile conventions, seed determinism, uniform day draws, p_pass + p_bust
+ p_incomplete = 1, empty-pool paths: verified clean by the statistics lens (independent
reference implementations run).

**Gates (final trees):** QL suite **811 passed** (807 at the pre-fix tree = 766 + 41 window
tests; +4 fix-regression tests) + `ruff check src tests` clean. SC docs-only; TL untouched.

**Deliverables:** `PROPSIM_QL_DIFF.txt` (`76546b0..1ef0ebe` — includes `f247046`, which RIDES
this greenlight) + `PROPSIM_BASELINE.md` at the QL root; `PROPSIM_SC_DIFF.txt` (`0e86cb5..tip`,
docs only) at the SC root. **NOT pushed (work-order FULL STOP).** Pins: no bump required at
greenlight — no consumer-facing SC change this window.

---

#### PROP-SIM pushed annotation + PRESETS ratified parameters (2026-07-10; PRESETS P0 doc-op)

**PROP-SIM GREENLIT + PUSHED** (PROPSIM_GREENLIGHT_REPORT.txt at the SC root). The PROP-SIM
close record above recorded "CLOSED — LOCAL, not pushed"; the window has since been pushed:
SC `origin/platform-refactor` = `d92eaf7` (push `0e86cb5..d92eaf7`, docs-only: P0 doc-op
`53b9b34` + close record `d92eaf7`) with **ci run 29134311915 (#11) = success** (head
`d92eaf7d0707…`, push-triggered, updated 2026-07-11T01:16:20Z); QL `origin/platform-refactor`
= `1ef0ebe` (push `76546b0..1ef0ebe`: `f247046` ENV-FIX riding + `86654c7` P1 + `dbf73d8` P2 +
`1ef0ebe` P4 fix) with **ci run 29134318835 (#10) = success** (head `1ef0ebe92c80…`,
push-triggered, updated 2026-07-11T01:17:37Z). **Pin witness:** the QL cold-install log
resolves `Strategy-Core.git to commit 3d4193e6bf3e…` — pins unchanged at `3d4193e` ×2 (no
consumer-facing SC change; 9.6 convention). TL untouched — no run owed. Both CI ids
re-witnessed via the REST API at this doc-op (run/head/conclusion match).

**PRESETS parameters RATIFIED** (owner-confirmed checkout data, 2026-07-10 dashboard screens;
recorded here as the ratified work order). Two new trail mechanics land in the QL walker
engine (`alpha_lab.propsim`, models + engine — presets stay data):

- `intraday_peak_trail` — the floor trails **PEAK equity including unrealized**: in the
  unrealized breach modes each trade's favorable leg (entry + MFE observed) raises the peak
  and floor = max(floor, peak − trail), still capped at the starting balance when the ruleset
  locks; in `realized_only` the peak updates from realized equity at trade closes + EOD.
- `static_floor` — the floor is FIXED at start − trail forever (never ratchets).
- `Ruleset` gains `max_eval_days: int|None` → verdict **"expired"** (distinct from
  `incomplete`) when the day budget runs out — expiry lands on day max+1, the first day the
  eval is no longer allowed to trade; and `dll_hard: bool` (True = a DLL touch is a BUST, not
  a halt) — supersedes the P2-era `dll_soft` flag (same semantics, inverted sign; one flag,
  no contradictory states).

**Ratified presets (data only, ⚠ = "verify at dashboard" note carried in the preset
docstring — flip when confirmed, data-only change):**

- `apex_50k_eod` = 50_000 / 3_000 / 2_000 `eod_floor_realtime_breach` / locks-at-start
  ⚠verify-lock / DLL 1_000 **HARD** ⚠verify-soft-vs-hard / NO consistency in eval /
  max_eval_days 30 / point_value 20.
- `apex_50k_intraday` = same but `intraday_peak_trail`, DLL None, max_eval_days 30.
- `tpt_50k_test` = 50_000 / 3_000 / 2_000 `eod_floor_realtime_breach` / locks-at-start /
  DLL None / consistency 50% / min_days 5 / NO expiry.

Oracle tests ratified with the mechanics: the separating case — an identical day sequence
where a 20-pt MFE-then-retrace trade busts `intraday_peak_trail` while `eod_floor` survives
it; the static floor never ratchets; expiry lands as `"expired"` on day max+1; hard-DLL busts
where soft halts THE SAME sequence. Baseline appendix: the journal evidence pool + the 06-17
OOS (ungated) re-run across ALL FOUR presets, both columns, N=10_000 seed 42 → cross-preset
table appended to `PROPSIM_BASELINE.md` (the first firm-vs-firm comparison on identical
paths).

Current window: **PRESETS** — the remaining eval rulesets + two trail mechanics + expiry/
hard-DLL semantics + the cross-preset baseline appendix (QL engine window; SC doc-ops only).

---

#### PRESETS — remaining eval rulesets + two trail mechanics (2026-07-10; QL window + SC doc-ops, CLOSED — LOCAL, not pushed)

**Commits:** SC `9ecd6c5` (P0 doc-op above) + this close record (docs only — NO SC code). QL,
base `1ef0ebe`: `3c4417e` (P1 trail mechanics) + `49c2f22` (P2 presets, data only). TL
untouched. Pins UNCHANGED at `3d4193e` ×2 (no SC code this window; 9.6 convention).

**P1 (QL engine, `models.py` + `engine.py` + minimal `bootstrap.py`/`report.py` carry-through):**
two new `trail_style` mechanics exactly as ratified — `intraday_peak_trail` (the floor trails
PEAK equity including unrealized: the favorable leg entry + MFE raises the peak IN ORDER —
adverse leg checked against the pre-favorable floor, the favorable ratchet lands BEFORE the same
trade's settle so an MFE-then-retrace can bust its own settle; in `realized_only` the peak
updates from closes + EOD; lock cap min(peak − trail, start) on every ratchet path) and
`static_floor` (start − trail forever, never ratchets). `Ruleset` gains `max_eval_days:
int|None` → verdict **"expired"** (distinct from `incomplete`): day max can still pass/bust,
the ATTEMPT of day max+1 lands expired untraded (`days_to_outcome` = max+1, `days_walked` =
max, nothing banked). **`dll_hard: bool` supersedes `dll_soft`** (rename, semantics inverted-
preserved — one flag, no contradictory states; `topstep_50k` `dll_hard=False` ≡ old
`dll_soft=True`) at BOTH DLL sites (adverse-leg force-close AT the level + settle). Carry-
through: bootstrap counts `expired` runs (`p_expired`; incomplete = n − passes − busts −
expired, Wilson CI still on passes) and the report prints `hard=`/`max_eval_days` in the
ruleset line + a `P(exp)` column. Oracle tests, all four ratified separating cases hand-
computed: the 20-pt MFE-then-retrace trade that busts `intraday_peak_trail` (floor 49,900 via
the +MFE leg; settle 49,800) while `eod_floor` survives THE SAME sequence (floor 48,000 all
day) and realized-only-intraday also survives (proves the UNREALIZED leg is load-bearing);
static floor pinned at 48,000 through a new-high day while the EOD control busts; expiry lands
`"expired"` on day max+1 with day-max pass/bust still landing; hard-DLL busts where soft halts
THE SAME sequence (+ the intraday lock-cap witness; + bootstrap-level expired-vs-incomplete
distinctness).

**P2 (presets, data only):** `apex_50k_eod` = 50_000 / 3_000 / 2_000 eod floor / locks
⚠verify-lock / DLL 1_000 HARD ⚠verify-soft-vs-hard / no consistency / max_eval_days 30;
`apex_50k_intraday` = same but `intraday_peak_trail`, DLL None; `tpt_50k_test` = eod floor /
locks / DLL None / consistency 50% / min_days 5 / no expiry. Both ⚠ parameters carry the
"VERIFY AT DASHBOARD" note in the preset docstring AND inline at the exact fields (flip when
confirmed = data-only change), pinned by a test.

**P3 (cross-preset baseline appendix, `PROPSIM_BASELINE.md` at the QL root, untracked — the
window's deliverable: the first firm-vs-firm comparison on identical paths):** journal evidence
pool (49 trades / 13 days) + 06-17 OOS ungated (42 / 15, excursion-DEGRADED everywhere), all
four presets × both columns, N=10_000 seed 42. **Regression witness: `topstep_50k` reproduces
the PROP-SIM baseline EXACTLY** (journal 0.9900/0.9889/0.9813/0.9730; OOS P(bust) 0.9984; same
as-sequenced verdicts). Headlines: the INTRADAY PEAK TRAIL is the binding firm difference —
optimistic unrealized P(pass) 0.9889 (TopStep) → 0.9492 (Apex intraday), conservative 0.9730 →
0.9076, bust counts ×3–×4 (111→455, 270→776 per 10k), and even realized-only it is tighter
(ratchets on every close: 0.9900 → 0.9720); the Apex 30-day budget expires 0.5–2.6% of journal
runs (slowest column hit hardest) and truncates the OOS pass-day median 22 → 16; the hard DLL
NEVER fired on either pool (±15pt/trade cannot reach −$1,000 before the nearer floor — the ⚠
soft-vs-hard question is numerically moot on these pools); `tpt_50k_test` ≈ `topstep_50k`
(min_days 5 never binds). Ranking: TopStep ≈ TPT > Apex-EOD > Apex-intraday; on the negative-
edge OOS pool every ruleset busts ≥ 0.982 — no ruleset launders a losing strategy. As-sequenced
history is ruleset-INVARIANT per column on the journal pool (optimistic pass day 13 $53,300;
conservative incomplete $52,960 — the fill model still decides that sequence).

**Verify (bounded close gate, 3 find-lenses + adversarial refuters on any finding):** engine
math vs the ratified spec — ZERO findings (25 hand-computed oracle checks + a 1,500-trial ×
4-cell fuzz: old-`dll_soft` 1ef0ebe engine vs new engine FLOAT-EXACT on every per-day
verdict/balance/floor for topstep semantics); presets + oracle-test arithmetic recomputed by
hand — ZERO findings (rename hygiene: `git grep dll_soft` hits only two behavior-describing
test names); appendix vs the 8 run JSONs — ZERO mismatches (640 programmatic cell/claim checks
+ 32-row human-table cross-check; p_pass+p_bust+p_expired+p_incomplete ≡ 1 in all 32 cells).
No refuters needed. Two recorded non-defect boundaries: (1) a bootstrap `--max-days` ≤ the
ruleset's `max_eval_days` would silently zero `p_expired` (expiry needs the day-max+1 attempt;
default max_days 1000 always clears it) — flagged for a future guard/warning; (2) pre-existing
`wilson_interval(0, n)` low bound is ~1.7e-18 float residue, harmless.

**Gates (final trees):** QL suite **822 passed** (811 at PROP-SIM close + 11 window tests: 6
engine oracles, 1 bootstrap expiry, 4 preset pins) + `ruff check src tests` clean, run on the
committed tree. SC docs-only; TL untouched.

**Deliverables:** `PRESETS_QL_DIFF.txt` (`1ef0ebe..49c2f22`) + the `PROPSIM_BASELINE.md`
cross-preset appendix at the QL root; `PRESETS_SC_DIFF.txt` (`d92eaf7..tip`, docs only) at the
SC root. **NOT pushed (work-order FULL STOP).** Pins: no bump required — no consumer-facing SC
change this window.

**PRESETS — PUSHED annotation (recorded 2026-07-11, INGEST P0 doc-op):** the window has since
been GREENLIT + PUSHED: SC `origin/platform-refactor` = `1a58aa8` (close record rides the
greenlight) with **ci run 29136911173 (#12) = success**; QL `origin/platform-refactor` =
`49c2f22` with **ci run 29136917345 (#11) = success**, cold-installing strategy-core resolving
the pin `3d4193e` on a fresh runner (pin witness). Pins unchanged at `3d4193e` ×2 (no
consumer-facing SC change; 9.6 convention). TL untouched — no run owed. Both CI ids banked
here; no debt outstanding.

---

#### Databento batch download — provenance (recorded 2026-07-11, INGEST P0 doc-op)

Portal **batch download** job `GLBX-20260711-EEDSMFU845` (Databento web portal, **$0 —
plan-covered**, no metered cost): dataset GLBX.MDP3, schema **MBP-1**, encoding DBN +
zstd, **split by day**, range **2026-01-11 .. 2026-07-10**. Delivered as one zip
(`Claude-Quant-Lab/data/databento/GLBX-20260711-EEDSMFU845.zip`, ~38.7 GB): **156 daily
files** `glbx-mdp3-YYYYMMDD.mbp-1.dbn.zst` + 3 job JSONs (`condition.json`,
`metadata.json`, `manifest.json`). Purpose: extend the local NQ store past the MBP-10 era
(store ends **2026-02-22**) — overlap 2026-01-11..2026-02-22 enables an identity gate
against the existing `mbp10.parquet` days before the post-gap days become first-class.

Current window: **INGEST** — convert the batch download into first-class store days
(`NQ/<date>/mbp1.parquet`), prove L1-projection identity on overlap days against the
original MBP-10 store through `DatabentoParquetSource`, fresh-day dataset build + route-seam
check, then full conversion (QL converter window; SC touched ONLY if the reader's file
discovery hardcodes `mbp10.parquet`).

---

#### INGEST — batch MBP-1 download → first-class store days (2026-07-11; QL converter window + SC D-P-17 deviation + TL catalog fix, CLOSED) [GREENLIT + PUSHED 2026-07-11 — ids in the greenlight annotation at the end of this record; pins bumped `3d4193e` → `9d49353` ×2]

**Commits:** SC, base `1a58aa8`: `9692696` (P0 doc-op) → `7340b2d` (D-P-17 trade
classification + discovery-precedence pins) → `b21316e` (close-verify: era-boundary
schema-matching prior-day fallback + buy-trade ordering pin + D-P-17 wording) → this close
record. QL, base `49c2f22`: `8f6f45e` (P2 converter + tests) → `6601dc7` (close-verify:
schema-pin order-diff message + sanity docstring). TL, base `67e03e4`: `58a5a85`
(close-verify: replay-catalog mbp-1 gate accepts level-00 TOB names). Pins were UNCHANGED at
`3d4193e` ×2 at close; **bumped at the greenlight to `9d49353` ×2** — D-P-17 + the boundary
fallback are consumer-facing SC code (9.6 convention). See the greenlight annotation at the
end of this record.

**P1 recon verdicts (banked):** (a) zip = 156 daily `glbx-mdp3-YYYYMMDD.mbp-1.dbn.zst`
(UTC-day split) + 3 job JSONs; NQ.FUT parent → instrument_id, so each file mixes NQ
outrights (front + back months) with calendar spreads — same multi-instrument mix as the
store; prices int64 1e-9; trades ride as action='T' rows (flags=0); per-instrument snapshot
seed rows (flags=168) open each file. (b) SCHEMA DIFF VERDICT: `DBNStore.to_parquet`
DEFAULTS in databento 0.81.0 ≡ the store schema exactly on all 20 shared columns (name,
arrow type, order, semantics — float dollars, tz-aware ns, mapped symbol, ts_recv pandas
index); only diff = the 54 level-01..09 columns, absent by nature of mbp-1. (c) discovery
NOT hardcoded — `DAY_FILE_PRIORITY` has been mbp1-aware with mbp10 precedence since W1 →
the literal P3 is SKIPPED. Reader never reads levels beyond 00 (`DECODE_SELECTED`
column-pruned read; W3A-READER P2 contract, D-P-15/D-P-16). (d) reuse verdict:
`process_batch_download.py` built the modern store era; its transform core
(`DBNStore.from_file → to_df()` defaults → write-time spread filter → `df.to_parquet`) is
adopted VERBATIM by the new converter. Store paths: ONE physical store (QL
`data/databento/NQ`; Trade-Dashboard\data is a symlink onto it).

**DEVIATION — D-P-17 (SC code beyond the work order's P3 scope, flagged):** the reader's
documented contract had mbp-1 parquet = QUOTES-ONLY (no Trade events), and the D-036
per-day build drives bars/levels/touches from Trade events only — so converted fresh days
would produce EMPTY datasets and the window's own P4b gate was unsatisfiable; the
mbp10-masquerade dodge is forbidden by the honest-naming ruling (below). Minimal amendment
taken in-window: action-bearing TOB schemas (mbp-1/cmbp-1/tbbo) classify T rows as trades,
exactly the mbp-10 rule; bbo/cbbo (no action column) unchanged. The contract line it amends
was vacuous — no mbp1/bbo/tbbo parquet existed in any store, so no existing consumer sees
different behavior. DECISIONS.md D-P-17 + oracle tests (incl. mbp-1 ≡ mbp-10 ordering
parity on identical rows for both buy and sell trades).

**HONEST-NAMING RULING (recorded):** store day files are named for the schema they contain
— MBP-1 data lands as `mbp1.parquet`, never as a `mbp10.parquet` masquerade (which would
have drained through the untouched reader but lied about depth). The reader was amended
(D-P-17) so honestly-named files are first-class instead.

**P2 (converter, QL `scripts/ingest_databento_batch.py`):** zip-or-dir →
`NQ/<date>/mbp1.parquet`, the process_batch_download.py core verbatim + `--workers`
(default 2), resume (exists-AND-loads), per-day `INGEST.log` lines (day, rows, seconds,
MB, notes), fatal sanity gates (non-empty; ts_recv within the file's UTC day), a written
**schema pin** against the store fingerprint (off-pin days are deleted, never left), and
date-range filters. Spreads dropped at write (3,830,522 rows total), back-month outrights
kept — front-month election stays read-time, matching the store.

**P4 gate results (IDENTITY RESULTS):** (a) OVERLAP IDENTITY — 2026-01-12, 2026-02-12
(dense), 2026-02-20: original mbp10 vs converted mbp1 through `DatabentoParquetSource`
(single-file drains, full window, front-month): trade / quote / warning streams **EXACT
event-by-event** — 35,677,893 events total, 1,163,904 trades bit-exact, 0 warnings; merged
interleave exact except **7 ns-tied clusters** (2–3 events each, dense days only), every
one permutation-verified with byte-identical underlying rows — root cause: the reader's
per-batch sort granularity on differently-sized files (venue fill+cancel pairs share a
sequence number; a 65,536-row batch boundary can split the cluster; first case: converted
row 3,407,872 = 52×65,536 at 02-12 14:51:17). Not an ingest defect; log =
`INGEST_IDENTITY.log` (QL root). (b) FRESH-DAY BUILD — 2026-03-02 through the D-036
per-day build (tag `7850272e` exact): cache written, **5 rows** (Feb warmed-day range
3–6), `prev_full_hl` seed exact via the 02-27 walk-back (Sunday 03-01 empty), 147 s /
3.0 GB RSS. (c) ROUTE-SEAM — key present, run on 2026-03-02: trade_count delta **0**
(441,575), tob_transitions delta **0** (12,625,748), first-event equal; the ±1 µs sampled
ts diffs are the check's own float-µs serialization (`route_seam_check.py:55`), price/size
identical at every sampled position; report `route_seam_report_ingest.json` (QL root).

**Full conversion (COUNTS):** **156/156 days converted, 0 failed** (37 overlap alongside
untouched mbp10.parquet — precedence keeps them serving the original — + 119 fresh
2026-02-23..2026-07-10), 1,833,605,368 rows, 43.6 GB, ~39 min wall at workers=2 across the
staged runs. 48 days carry a benign 1–2-row invalid-price WARN (far-from-market
cancel-order prices on quote rows — the `price` field of non-trade rows is never consumed
by the reader; the mbp10 originals carry the same rows). `INGEST.log` (QL root).

**Close verify (3 find-lenses + adversarial refuters):** 7 CONFIRMED (3 major / 4 minor),
6 refuted. All fixed in-window except one recorded debt:
- **MAJOR (era boundary, found by two lenses):** `for_trading_day(2026-02-23)` degraded to
  single-file (prior 02-22 resolves mbp10 ≠ mbp-1), silently dropping the Sunday
  Globex-open hour (8,413 front-month trades) AND understating the 02-24 PDH seed by
  19.75 pt vs the QL research carry — the research↔serving seed-drift class. **FIXED**
  (`b21316e`): schema-MATCHING prior-day fallback before degrading; witnessed live
  post-fix: two-file composition, zero warnings, first trade 23:00:00 UTC, 02-24 extremes
  100239/98672 (true full-session values). Degrade-still-works pinned by test.
- **MAJOR (TL):** replay-catalog mbp-1 live-column gate lacked the `bid_px_00/ask_px_00`
  aliases the ingested files use → the ENTIRE new era was invisible to TL replay (0
  sources ≥ 02-23). **FIXED** (`58a5a85`); witnessed post-fix: 156 mbp-1 sources, all 119
  new-era days discoverable.
- minor: D-P-17 wording claimed unconditional trade-before-quote (false for buy trades —
  canonical-key-determined) → FIXED + mbp-1≡mbp-10 ordering parity test.
- minor: converter schema-pin order-diff message inverted (pure order mismatch → empty
  message) → FIXED + test.
- minor: sanity docstring overclaimed PBD-check mirroring → FIXED (docstring; the
  non-monotonic/dup-ts warns are intentionally dropped as always-firing noise).
- minor **NAMED DEBT (not fixed):** QL dashboard `replay_client.py` (+ legacy backtest
  scripts) are mbp10-hardcoded — mbp1-era days are invisible to the QL dashboard replay
  surface. Off this window's critical path; owed to a future window.
Refuted (6): converter resume/atomicity, NaT-blindness, duplicate-member race, identity
permutation-tolerance over-breadth, day-class coverage gap, unfiltered back-month/spread
divergence — refuter reasoning in the verify journal.

**Gates (final committed trees):** SC suite **205 passed** (202 at D-P-17 + 3 close-verify
tests; tests + validation, real-store validation harnesses included) + ruff clean (tracked
dirs). QL suite **830 passed** (822 at PRESETS + 8 window tests) + `ruff check src tests
scripts` clean. TL backend **511 passed / 1 skipped**. Era-boundary + catalog witnesses
re-run live post-fix (above).

**Deliverables:** `INGEST_SC_DIFF.txt` (`1a58aa8..tip`) / `INGEST_QL_DIFF.txt`
(`49c2f22..6601dc7`) / `INGEST_TL_DIFF.txt` (`67e03e4..58a5a85`) at the repo roots;
`INGEST_IDENTITY.log`, `INGEST.log`, `route_seam_report_ingest.json` at the QL root; the
identity/P4b harnesses `scratch_ingest_identity.py` / `scratch_ingest_p4b.py` (QL root,
untracked, re-runnable). At close the window was NOT pushed (work-order FULL STOP), with the
pin bump and the TL/QL pin-witness runs owed at greenlight; **all three were paid at the
2026-07-11 greenlight — annotation next.**

**INGEST — GREENLIT + PUSHED annotation (2026-07-11; ids banked here at the DOC-SYNC doc-op,
2026-07-25):**

- **SC** `origin/platform-refactor` = **`9d49353`** (this close record rides the greenlight) —
  **ci run 29162591811 (#13) = success.**
- **TL** `58a5a85` (close-verify catalog fix) + pin chore **`3466aff`** —
  **backend-ci run 29162631478 (#14) = success.**
- **QL** `6601dc7` (close-verify) + pin chore **`3b470d3`** + CI test-hermeticity fix
  **`5ab6da9`** — **ci run 29162951541 (#13) = success on the fix tip.** The FIRST run,
  **#12 (29162655755) = failure** on `3b470d3`: pandas-3 / pyarrow-25 fixture-type drift in
  `tests/agents/test_ingest_databento_batch.py` — the fixtures relied on pandas dtype
  inference, which the cold-install runner resolved differently from the host. **The
  production schema pin behaved exactly as designed** — it caught a genuine type mismatch;
  what was wrong was the test's construction of the input, not the pin. The fix
  (`5ab6da9`) builds the `schema_problems` fixtures with explicit Arrow types and is
  **test-only** (1 file, +40/−23 — no `src/`, no script, no production surface).
- **D-P-11(c) DEVIATION, DISCLOSED:** `5ab6da9` is an unreviewed commit taken mid-greenlight
  and **rode post-review** rather than stopping-and-reporting first. It is recorded here as a
  deviation, not as compliance. Reviewer sign-off artifact generated this session:
  **`5AB6DA9_QL_DIFF.txt`** at the QL root (`git diff 3b470d3..5ab6da9`, 106 lines, 1 file,
  test-only).
- **Pins bumped `3d4193e` → `9d49353` on both consumers**; cold-install pin resolution
  witnessed in both consumers' raw CI logs.

---

#### Owner doc commit outside window scope (recorded 2026-07-25, DOC-SYNC doc-op)

TL **`14ed624`** (2026-07-15, `feat: add readme` — `README.md`, `backend/README.md`,
`backend/.env.example`, `.claude/scheduled_tasks.lock`): owner-authored documentation/config,
outside any window's scope, **no code change**; TL `backend-ci` run **29470434376 (#15) =
success** on it. Recorded so the ledger accounts for every commit on `platform-refactor`.
