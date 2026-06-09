# Platform + Strategy-Plugin SDK — Migration Plan

PLANNING DOCUMENT (no source files changed to produce it). Extracts a thin, versioned **platform** + a **strategy-plugin SDK** out of the Strategy-Core monolith so many strategies become plugins, the existing key-level touch/zone-reversal strategy becomes strategy #1 behind the interface, and no-drift becomes structural. Incremental (strangler-fig) behind green tests — never big-bang.

Grounded against (HEADs at planning time): Strategy-Core `fd53e06`, Quant-Lab `5a096a1`, Trade-Lab `a191202`. CURRENT code is quoted verbatim with file:line; target design is labeled PROPOSED.

---

---

## 1. Current-state seam (grounded recap)

This section is grounded in the live source of all three repos. Every CURRENT signature below was re-read from disk and is quoted verbatim with `file:line`. Items labelled **PROPOSED** do not exist today.

### (a) There is NO Strategy abstraction / base-class / registry — CONFIRMED (negative)

There is exactly one strategy: the hardwired pipeline `StrategyLevelState` (levels) → `build_zones` → `detect_touches` → `resolve_(honest_)outcome`, driven by `StrategyRuntime`. It is selected by the `ENGINE_VERSION` stamp + `training_mode` config, never by registration.

- Grep for `class \w*Strategy\w*\(`, `register_strategy`, `STRATEGY_REGISTRY`, `entry_points`, `@register` across all three `src/` trees returns **zero** strategy-interface hits. The only `class …Strategy…(` matches are Pydantic contract models, not interfaces:
  - `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/contract/schema.py:246` `class StrategyContract(_ContractModel):`
  - `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/contracts/strategy_contract.py:160` `class StrategyContract(_ContractModel):`
  - Quant-Lab `src/`: no matches at all.
- No `[project.entry-points]` / `entry_points` in any of the three `pyproject.toml`.
- The only "strategy logic" baked into the runtime is the inline touch/zone/level fold in `StrategyRuntime._process_trade` (`C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/runtime/state.py:262-290`), with `detect_touches`/`build_zones`/`classify_session`/`StrategyLevelState` imported at module top. There is **no plugin/strategy hook param** on `StrategyRuntime.__init__` and no dispatch by `strategy_id` (it is carried opaquely as a label; see (c)/consumers).

**PROPOSED:** any plan to host multiple strategies must INTRODUCE this abstraction — it does not exist today.

### (b) The single global `engine_version` stamp — CONFIRMED

There is one global stamp, single-sourced in Strategy-Core (`C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/__init__.py:54,57`):

```python
ENGINE_VERSION = "strategy_core_engine_v3"   # __init__.py:54
CONTRACT_VERSION = "trade_lab_contract_v1"   # __init__.py:57
```

This is a single monolithic engine-wide version, not per-strategy. The SC schema (`schema.py:30`) and loader (`loader.py:21`) import these from the package rather than restating them; the QL emitter imports both; TL restates `CONTRACT_VERSION` locally (see (c)). A v2-built model "correctly fails the v3 loader" (per the `__init__.py:50-53` comment). The fail-close runs in the LOADER, not the registry (see (c)).

### (c) Contract format duplicated across three places, and TL's 3-way divergence — CONFIRMED

The contract format exists in three copies:

1. **SC canonical schema + loader** — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/contract/schema.py` (+ `loader.py`). `StrategyContract` (`schema.py:246-278`) has `engine_version: str = Field(min_length=1, max_length=64)` (REQUIRED, `schema.py:256`), a `LabelPolicy` carrying `decision_offset_minutes: int = Field(gt=0, le=1440)` (`schema.py:161`), and an optional `research_session_experiment: ResearchSessionExperiment | None = None` (`schema.py:274`). The loader takes an injectable `expected_engine_version` keyword checked BEFORE `model_validate` (`loader.py:28-77`).
2. **TL local copy** — `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/contracts/strategy_contract.py` (schema + loader in one file). It restates `CONTRACT_VERSION = "trade_lab_contract_v1"` locally (`:20`) and only does `import strategy_core` (`:17`) to read `strategy_core.ENGINE_VERSION` at load time.
3. **QL dict emitter** — `C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/strategy_contract.py`, `build_strategy_contract(...) -> dict` (plain dict, not a Pydantic model), single-sourcing structural fields from `strategy_core.constants` and importing `CONTRACT_VERSION, ENGINE_VERSION` from `strategy_core`.

All three `_ContractModel` bases set `extra="forbid"` (TL confirmed verbatim at `strategy_contract.py:29-32`), which makes every divergence a hard parse breaker.

**The three ways TL's local copy diverged from SC canonical (verbatim):**

- **Divergence 1 — `engine_version` is OPTIONAL, not required.** TL `StrategyContract` (`strategy_contract.py:168`):
  ```python
      engine_version: str | None = Field(default=None, max_length=64)
  ```
  vs SC required `engine_version: str = Field(min_length=1, max_length=64)` (`schema.py:256`). The TL loader binds AFTER `model_validate` against the hardcoded `strategy_core.ENGINE_VERSION` and only logs a warning ("loading unbound") when the field is absent — it does not take an `expected_engine_version` keyword like SC.
- **Divergence 2 — `LabelPolicy` is MISSING `decision_offset_minutes`.** TL `LabelPolicy` (`strategy_contract.py:95-103`) jumps straight from `entry_reference` to `tp_points`:
  ```python
  class LabelPolicy(_ContractModel):
      resolution: str = Field(min_length=1, max_length=32)
      entry_reference: str = Field(min_length=1, max_length=64)
      tp_points: float = Field(gt=0.0)
      sl_points: float = Field(gt=0.0)
      trap_mfe_min: float = Field(ge=0.0)
      forward_bar_type: str = Field(min_length=1, max_length=16)
      forward_cutoff: str = Field(min_length=1, max_length=64)
      no_resolution_dropped: bool
  ```
  The QL emitter DOES emit `decision_offset_minutes` (`Claude-Quant-Lab/.../strategy_contract.py:191`), so under `extra="forbid"` a current v3 contract FAILS to parse against TL's local `LabelPolicy`.
- **Divergence 3 — NO `ResearchSessionExperiment` model and NO `research_session_experiment` field.** The TL `StrategyContract` field list ends at `provenance: Provenance` (`strategy_contract.py:185`) with no `research_session_experiment` field, and the file defines no `ResearchSessionExperiment` class. The QL emitter DOES emit a top-level `"research_session_experiment"` key (`Claude-Quant-Lab/.../strategy_contract.py:204`), so this too is rejected by TL's local loader.

Net: TL's local `extra="forbid"` schema **cannot parse a current QL-emitted v3 contract** (rejected on `decision_offset_minutes` and on `research_session_experiment`; plus `engine_version` is merely optional vs required).

### (d) TL's local candles/sessions/levels — they still exist on disk as DTO/display types, but the acceptance test asserts the ABSENCE of the strategy ENGINE classes from the runtime path — CONFIRMED (with nuance)

The TL local modules `domain/candles.py`, `domain/sessions.py`, `domain/levels.py` still exist post-migration and are still imported, but **only as data/display types**, never as the strategy compute engine:

- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/runtime.py:16` imports `Candle`; `:27` imports `DisplayLevel, TouchEvent`.
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/strategy_core_service.py:29` imports `Candle, CandleCloseReason`; `:33` imports `DisplayLevel, LevelDirection, LevelKind, TouchEvent`; `:35` imports `SessionName`.
- A TL local `CandleEngine` class still exists at `domain/candles.py:103` (with the same `"tick timeframes must be positive"` validation at `:112`) and `domain/levels.py:140` still defines a `process_trade`, and `services/seed.py:24` still uses the local `classify_session`/`to_ct` — i.e. the local engine code is present but the STREAMING runtime path no longer calls it for strategy meaning.

The acceptance test that asserts the absence is `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_strategy_core_acceptance.py:68-78`, `test_runtime_path_uses_strategy_core_service_not_legacy_strategy_engines`, which `inspect.getsource`s the runtime module + `StrategyCoreService` and asserts (verbatim):

```python
    assert "StrategyCoreService" in runtime_source
    assert "CandleEngine" not in runtime_source
    assert "SessionLevelEngine" not in runtime_source
    assert "SessionClassifier" not in runtime_source
    assert "CandleEngine" not in service_source
    assert "SessionLevelEngine" not in service_source
    assert "SessionClassifier" not in service_source
```

So the asserted absence is specifically the *legacy strategy ENGINE classes* (`CandleEngine`, `SessionLevelEngine`, `SessionClassifier`) from the runtime/service source — NOT the DTO types (`Candle`, `DisplayLevel`, `TouchEvent`, `SessionName`), which remain. The same file's `test_trade_lab_runtime_touch_matches_strategy_core_direct_runtime` (`:30-66`) is the cross-runtime acceptance: TL `ApplicationRuntime` touch output equals a direct `StrategyRuntime` run on the same trades.

### (e) QL's undeclared / unpinned Strategy-Core dependency — CONFIRMED

QL imports the engine directly (`engine_decision.py` and the emitter `import strategy_core … from strategy_core.constants import …`), but `strategy-core` is **not** a declared dependency:

- `C:/Users/gonza/Documents/Claude-Quant-Lab/pyproject.toml` lists pandas/numpy/scipy/pydantic/catboost/fastapi/etc. in `dependencies` (`:12-36`) and dev tooling in `[project.optional-dependencies] dev` (`:38-48`) — **no `strategy-core`, no git URL**. Pytest config has `pythonpath = ["src"]` (`:55`), pointing only at QL's own `src`.
- Contrast TL, which SHA-pins it: `C:/Users/gonza/Documents/Trade-Lab/backend/pyproject.toml:19` `"strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@fd53e06989084368aa3b89d33eb83bee081b695f"`.

This is the asymmetric-binding risk: QL resolves `strategy_core` only via an external editable / `PYTHONPATH=src`-style install and can silently float to a different SC commit than the one TL is pinned to.

### (f) Tick-bar-only candle aggregation in the streaming engine — CONFIRMED

`CandleEngine` is strictly a tick-COUNT bar builder; no time/minute (or volume) bars exist. `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/candles/streaming.py:100-108`:

```python
    def __init__(
        self,
        timeframes: tuple[int, ...] = (147, 987, 2000),
        *,
        scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
    ) -> None:
        # candles.py:111-112 -- positive timeframes only.
        if not timeframes or any(size <= 0 for size in timeframes):
            raise ValueError("tick timeframes must be positive")
```

The bar-close condition is a trade *count* (`if candle.trade_count == timeframe:` closes COMPLETE, `streaming.py` per evidence §3), `CloseReason` has only `COMPLETE`/`END_OF_DAY` (no `TIME`/`INTERVAL`), the field is named `timeframe_ticks`, and time appears only as a passive open/close stamp + the trading-day rollover. The vectorized parity path `build_tick_bars_from_frame` (`candles/batch.py:38`) buckets via `cumcount() // timeframe` — also tick-only. **PROPOSED archetype-2 (time/minute bars) is net-new work, not a config flag.**

### Key CURRENT signatures (verbatim, re-cited)

**Runtime — `StrategyRuntime.__init__` and `process_event`** (`C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/runtime/state.py:173-199, 229-236`):

```python
    def __init__(
        self,
        *,
        timeframes: tuple[int, ...] = (147, 987, 2000),
        decision_timeframe: int | None = None,
        requested_symbol: str | None = None,
        scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
        tick_size: float = DEFAULT_TICK_SIZE,
        recent_closed_bar_limit: int = 500,
        warning_limit: int = 100,
    ) -> None:
        ...
        self.candles = CandleEngine(timeframes, scheme=scheme)
        self.decision_timeframe = decision_timeframe or min(timeframes)
        self.level_state = StrategyLevelState(scheme=scheme, tick_size=tick_size)
```

```python
    def process_event(self, event: Trade | Quote | DataQualityWarning) -> RuntimeUpdate:
        if isinstance(event, DataQualityWarning):
            return self.record_warning(event)
        if isinstance(event, Quote):
            return self._process_quote(event)
        if isinstance(event, Trade):
            return self._process_trade(event)
        raise TypeError(f"unsupported runtime event type: {type(event).__name__}")
```

All params are keyword-only; `decision_timeframe` resolves to the smallest timeframe at construction (`state.py:188`); dispatch is `isinstance`-based, not pluggable.

**The hardwired strategy fold — `_process_trade`** (`state.py:262-290`), decision-timeframe-gated touch detection:

```python
    def _process_trade(self, trade: Trade) -> RuntimeUpdate:
        self._last_event_ts_utc = trade.event_ts_utc
        candle_update = self.candles.process_trade(trade)
        ...
        levels = self.level_state.process_trade(trade)
        touches: list[Touch] = []
        for bar in candle_update.completed:
            if bar.timeframe_ticks != self.decision_timeframe:
                continue
            zones = self._zones_for_detection(bar.trading_day)
            detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
            ...
```

**`RuntimeUpdate`** — sparse delta DTO, all 8 fields default empty/`None` (`state.py:113-122`):

```python
@dataclass(frozen=True, slots=True)
class RuntimeUpdate:
    feed_status: FeedStatus | None = None
    warnings: tuple[DataQualityWarning, ...] = ()
    current_bars: tuple[Bar, ...] = ()
    closed_bars: tuple[Bar, ...] = ()
    levels: tuple[Level, ...] = ()
    zones: tuple[Zone, ...] = ()
    touches: tuple[Touch, ...] = ()
    last_quote: Quote | None = None
```

**Contract model — `StrategyContract` (SC canonical)** (`C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/contract/schema.py:246-278`): `contract_version`, `engine_version` (REQUIRED, `:256`), `strategy_id`, `training_mode`, `supported_by_runtime`, `instrument`, `tick_size`, `point_value`, `model`, `feature_set`, `class_map`, `session_scheme`, `level_scheme`, `touch_rule`, `feature_windows`, `label_policy`, `inference`, `data_requirements`, `provenance`, `research_session_experiment: ResearchSessionExperiment | None = None` (`:274`).

**Decision functions (SC):**

```python
def build_zones(
    levels: list[Level], *, zone_proximity_pts: float = ZONE_PROXIMITY_PTS
) -> list[Zone]:
```
(`decisions/zones.py:23-25`)

```python
def detect_touches(
    bars: Sequence[Bar],
    zones: list[Zone],
    *,
    tick_size: float,
    trading_day: date,
    direction_from_side: Mapping[Side, Direction] = DIRECTION_FROM_SIDE,
) -> list[Touch]:
```
(`decisions/touch.py:47-54`)

```python
def resolve_honest_outcome(
    touch: Touch,
    day_bars: Sequence[Bar],
    trade_price_at: Callable[[datetime], float | None],
    *,
    tick_size: float,
    tp_points: float,
    sl_points: float,
    trap_mfe_min: float,
    decision_offset_minutes: int = DECISION_OFFSET_MINUTES,
    flatten_time: time = FLATTEN_TIME,
    rth_end: time = RTH_END,
    timezone: str = SESSION_TIMEZONE,
) -> OutcomeResult | HonestEntryDrop:
```
(`decisions/honest_entry.py:76-89`)

All decision functions are free module-level functions with no Strategy-object receiver — reinforcing (a): there is no strategy abstraction to dispatch through, only a fixed function pipeline.

---

## 2. Target architecture — the thin waist

The migration's organizing idea is a **thin waist**: a small, stable PLATFORM core that owns everything generic about ingesting market data and running an event-sourced loop, and a narrow, well-typed **STRATEGY-PLUGIN interface** through which all strategy meaning flows. Everything in the evidence that is *generic* (event fold, candle aggregation, the `RuntimeUpdate`→`ws.v1` transport, contract loading, parity harnessing) stays in the platform; everything that is *strategy-specific* (which levels/zones/FVGs to track, what a "setup" is, what barriers to place, what features to compute, what the typed contract section looks like) moves behind the plugin interface. Today neither side exists as a boundary — the touch/zone/level pipeline is hardwired into `StrategyRuntime._process_trade` with no seam (`runtime/state.py:262-290`), and the contract is one flat `StrategyContract` duplicated in three places. This section defines the target so a single platform can host BOTH archetypes.

### 2.1 The PLATFORM layer (what it OWNS)

The platform owns six concerns. The argument that it is **small and stable** is that every one of these already exists today as strategy-agnostic code; we are *removing* the one piece of strategy logic that leaked into it (the inline touch detection at `state.py:271-280`), not adding machinery.

**(1) Data ingest.** The neutral input value types `Trade`, `Quote`, `DataQualityWarning` and the Databento/parquet sources. The single event entrypoint is already strategy-free:

```python
# CURRENT — C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/runtime/state.py:229-236
    def process_event(self, event: Trade | Quote | DataQualityWarning) -> RuntimeUpdate:
        if isinstance(event, DataQualityWarning):
            return self.record_warning(event)
        if isinstance(event, Quote):
            return self._process_quote(event)
        if isinstance(event, Trade):
            return self._process_trade(event)
        raise TypeError(f"unsupported runtime event type: {type(event).__name__}")
```

This dispatch stays in the platform verbatim; it has no strategy knowledge.

**(2) Event-sourced runtime loop.** The platform owns the fold-one-event-at-a-time loop and the lifecycle around it (`reset`, `snapshot`, recent-bar ring buffer, feed status). CURRENT `_process_trade` (`state.py:262-290`) does five things, four of which are platform-generic (advance the clock, fold the trade into candles, maintain the recent-bar buffer, build `FeedStatus`) and one of which is strategy-specific (the `bar.timeframe_ticks != self.decision_timeframe` touch detection at `state.py:272-280`). **PROPOSED:** the platform loop keeps the four generic steps and, in place of the hardwired touch block, calls the active plugin's `on_bar_closed(...)` / `on_event(...)` (see §2.2). The platform still owns the `RuntimeUpdate` it returns; the plugin contributes only its strategy deltas to it.

**(3) Candle aggregation supporting BOTH tick AND time bars.** CURRENT `CandleEngine` is **strictly a tick-count builder** — a bar closes only on `candle.trade_count == timeframe` (`candles/streaming.py:180-181`) or a trading-day rollover; `CloseReason` has exactly two members, `COMPLETE` and `END_OF_DAY` (`types.py:51-55`); the validation message is literally `"tick timeframes must be positive"` (`streaming.py:108`). There is no clock-boundary close anywhere in `streaming.py` or `batch.py`. Archetype 2 needs 1H/4H/30m/15m/10m/5m/3m/1m **time** bars (ifvg-strat.md §4.2), which today is net-new work, not a config flag.

**PROPOSED — the platform owns a bar-spec abstraction the strategy *declares*, not hardcodes.** Replace the bare `timeframes: tuple[int, ...]` with a typed `BarSpec`:

```python
# PROPOSED
class BarKind(StrEnum):
    TICK = "tick"      # close on trade_count == size      (CURRENT engine)
    TIME = "time"      # close on wall-clock interval edge  (NEW close trigger)

@dataclass(frozen=True, slots=True)
class BarSpec:
    kind: BarKind
    size: int                 # tick count, or interval seconds for TIME
    label: str                # stable id, e.g. "147t", "1m", "1H"
```

A new `CloseReason.INTERVAL` member and an elapsed-time close trigger are added to the engine; the existing tick path is unchanged (so all candle-parity golden tests still pin byte-identically). The strategy declares which `BarSpec`s it needs via `required_bars()` (§2.2); the platform builds exactly that set and routes each closed bar to the plugin keyed by `BarSpec.label`. This is the one genuinely new platform capability the thin waist requires.

**(4) The contract ENVELOPE + loader + version binding.** The platform owns the *generic* envelope schema, the fail-closed loader, and the version-binding policy (§2.4, §2.5). It does NOT own any strategy's typed section — it validates the envelope and dispatches the section to the registered plugin for typed validation. The loader is already the right shape on the SC side (`loader.py:28-77`, injectable `expected_engine_version`); the divergent TL local copy (`domain/contracts/strategy_contract.py`) is retired and TL repoints onto the platform loader.

**(5) The `RuntimeUpdate`→`ws.v1` transport.** The platform owns the delta dataclass, the `to_dict()` serialization boundary, and the WebSocket envelope. CURRENT envelope, verbatim:

```python
# CURRENT — C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/api/dto.py:214-219
class Envelope(ApiModel):
    version: str = MESSAGE_VERSION
    type: MessageType
    sequence: int
    server_time_utc: datetime
    payload: dict[str, Any]
```

`MESSAGE_VERSION = "ws.v1"` (`api/dto.py:24`), `ApiModel` is `extra="forbid"` (`:42`), and `make_envelope` stamps `version="ws.v1"` on every frame (`:429-444`). The platform keeps owning the envelope and the generic message types (`feed.status`, `market.bar.updated`, `market.bar.closed`, `data_quality.warning`, `model.status`, `system.snapshot`). **PROPOSED:** strategy-specific deltas (today's `touch.detected`; tomorrow's `setup.updated`, `decision.created`, `decision.resolved`) are carried in a *generic* envelope frame whose `payload` is the plugin's own typed event serialized to a dict (§2.2 `emitted_event_types()`), so adding a strategy does not require editing the platform's `MessageType` Literal for each new delta shape — the platform validates the envelope; the payload schema is the strategy's.

**(6) The parity-harness FRAMEWORK.** The platform owns the *mechanism* — run the batch path and the streaming path over the same data and assert byte-equality (the recipe proven by `validation/test_duckdb_streaming_parity.py`, `tests/test_candle_parity.py`, and QL `test_decision_repoint_parity.py` with "max abs diff must be 0"). **PROPOSED:** the harness is parameterized by the active plugin: it asks the plugin for its decision records (§2.2) and diffs them; each strategy plugs in its own golden fixtures. The candle/level parity stays platform-level (it is strategy-agnostic); the decision/feature/label parity becomes per-plugin.

**Why this is small and stable:** the platform surface is `process_event`, `reset`, `snapshot`, the candle engine, the envelope/loader, and the harness framework — all of which exist today and none of which encode a strategy. The only additions are (a) `BarSpec`/time bars and (b) the plugin dispatch seam. Once those land, a new strategy ships **zero** platform changes.

### 2.2 The STRATEGY-PLUGIN interface (PROPOSED)

The interface is a `Protocol` (structural; a registry-discovered object need only satisfy it). It must express: lifecycle; consuming events/bars with **declared** tick AND time timeframes; emitting multi-stage **setup state** (arming/locking/invalidation) + **decision events** + **barriers** (fixed-point AND R-relative); declaring **features**; declaring a typed **contract section** the strategy owns; declaring the **envelope/event types** it emits; and declaring its **label/outcome policy** (per-setup R-relative barriers).

```python
# PROPOSED — the strategy-plugin Protocol (full surface)
from typing import Protocol, runtime_checkable, Any, Sequence, Mapping
from datetime import datetime

# ---- platform-provided context handed to the plugin each step (read-only) ----
class PlatformContext(Protocol):
    tick_size: float
    point_value: float
    def closed_bars(self, label: str) -> Sequence["Bar"]: ...   # by BarSpec.label
    def current_bar(self, label: str) -> "Bar | None": ...
    def trade_price_at(self, ts_utc: datetime) -> float | None: ...  # honest fill query
    def session_at(self, ts_utc: datetime) -> str | None: ...        # via SessionScheme

# ---- the things a plugin emits (all strategy-owned, platform-opaque) ----
class SetupState(Protocol):
    setup_id: str
    phase: str            # e.g. "scanning"|"htf_tapped"|"parent_locked"|"armed"|"invalidated"
    direction: str        # "long"|"short"
    status: str           # "active"|"invalidated"|"expired"|"resolved"
    evidence: Mapping[str, Any]   # audit payload (HTF zone, parent tf, opposing gap, …)

class Barrier(Protocol):
    kind: str             # "fixed_points" | "r_relative"
    # fixed_points: tp_points/sl_points are absolute points
    # r_relative:   sl_price is an absolute level (swing); tp_r is a risk multiple
    def stop_price(self, entry_price: float, direction: str) -> float: ...
    def target_price(self, entry_price: float, direction: str) -> float: ...

class DecisionEvent(Protocol):
    setup_id: str
    decision_ts_utc: datetime
    direction: str
    entry_reference: str          # "trade_price_at_decision" | "confirmation_close" | …
    barrier: Barrier              # per-setup; fixed OR R-relative

@runtime_checkable
class StrategyPlugin(Protocol):
    # ---- identity / binding ----
    strategy_id: str
    strategy_version: str
    SectionModel: type            # the pydantic section model this strategy OWNS (§2.4)

    # ---- lifecycle ----
    def configure(self, section: Any, ctx: PlatformContext) -> None: ...  # section: validated SectionModel
    def reset(self) -> None: ...

    # ---- data requirements (DECLARED, tick AND time) ----
    @staticmethod
    def required_bars() -> tuple["BarSpec", ...]: ...   # e.g. (BarSpec(TICK,147,"147t"),)
                                                        # or (TIME 60 "1m", TIME 180 "3m", … TIME 14400 "4H")
    @staticmethod
    def decision_bar_label() -> str: ...                # which BarSpec drives single-bar decisions

    # ---- event consumption ----
    def on_event(self, event: "Trade | Quote", ctx: PlatformContext) -> tuple[SetupState, ...]: ...
    def on_bar_closed(self, bar: "Bar", ctx: PlatformContext) -> "StrategyStep": ...

    # ---- declarations consumed by platform + consumers ----
    @staticmethod
    def feature_spec() -> "FeatureSpec": ...            # names, interaction/approach split, nan_policy
    @staticmethod
    def label_policy() -> "LabelPolicySpec": ...        # resolution + barrier MODE (fixed/R) + cutoff rule
    @staticmethod
    def emitted_event_types() -> tuple["EventTypeSpec", ...]: ...  # ws message types + payload schemas

# ---- what one bar-close step returns (sparse, like RuntimeUpdate) ----
class StrategyStep(Protocol):
    setups: tuple[SetupState, ...]        # arming/locking/invalidation deltas
    decisions: tuple[DecisionEvent, ...]  # fired entries (0..1 today; 0..1 for archetype 2)
    features: tuple[Mapping[str, float], ...]  # per-decision feature rows
```

Notes that make this load-bearing:

- **Lifecycle:** `configure(section, ctx)` replaces today's hardwired `__init__` wiring of `StrategyLevelState`/`detect_touches` (`state.py:187-189`, `state.py:11-17`); `reset()` mirrors the existing `StrategyRuntime.reset` (`state.py:201-214`) but the plugin clears *its* state, while the platform keeps owning candle/feed reset.
- **Declared timeframes (tick AND time):** `required_bars()` returns `BarSpec`s. Archetype 1 returns a single `TICK` spec; archetype 2 returns a mix of `TIME` specs (1m…4H). The platform reads this set at `configure` time and constructs exactly those builders — this is how a strategy declares it needs minute bars without the platform hardcoding them.
- **Setup state (multi-stage):** `on_event`/`on_bar_closed` return `SetupState` deltas with an explicit `phase`/`status`, so arming → locking → invalidation is first-class. Archetype 1 has a degenerate single-phase setup (touch → decision in one step); archetype 2 walks the full ifvg-strat.md state machine (§9 of that doc).
- **Barriers (BOTH fixed AND R-relative):** `Barrier` is a Protocol with `stop_price`/`target_price`. A `fixed_points` barrier reproduces today's `tp_points`/`sl_points` exactly (`decisions/outcomes.py:127-136`, defaults 15/30/5 at `constants.py:139-141`). An `r_relative` barrier computes `SL = swing level` and `TP = entry ± 1R` where `R = |entry − SL|` — directly modeling ifvg-strat.md §11.2/§6.3 (manipulation-swing stop, 1R target).
- **Feature declaration:** `feature_spec()` returns the names + interaction/approach partition + nan_policy that today live in the flat `FeatureSet` (`schema.py:77-94`) and are computed by the six fixed functions in `decisions/features.py`. The plugin owns which features it computes.
- **Typed contract section:** `SectionModel` is the pydantic model the strategy owns (§2.4).
- **Emitted envelope/event types:** `emitted_event_types()` lets the strategy declare its `ws.v1` payload shapes so the platform can route them generically (§2.1(5)).
- **Label/outcome policy:** `label_policy()` declares the resolution mode *including barrier mode*, so the platform's outcome/parity machinery knows whether to score fixed-point MFE/MAE (archetype 1) or R-normalized excursions (archetype 2).

This interface **expresses both archetypes** — validated explicitly in §2.6.

### 2.3 Strategy REGISTRY + selection

**Options compared.** (a) *Python entry-points* (`[project.entry-points."strategy_core.strategies"]`): pip-discoverable, no central import, but requires packaging metadata, is invisible to a simple grep, and couples discovery to install state — fragile given QL already resolves `strategy_core` through an *undeclared* editable install (BASELINE §2(a): no SC pin in QL `pyproject.toml`). (b) *Registry module*: a single `strategy_core.strategies.registry` with an explicit dict `{strategy_id: StrategyPlugin}` populated by a `@register` decorator at import.

**RECOMMENDATION: a registry module.** It is greppable, version-controlled in one place, requires no packaging changes, and binds cleanly to the existing `strategy_id` field already carried in the contract (`schema.py:257`). It also fits the asymmetric-binding reality: TL is SHA-pinned to SC (`backend/pyproject.toml:19`) while QL floats, so a registry that lives *inside* `strategy_core` is seen identically by both consumers at whatever SC commit each resolves.

```python
# PROPOSED — strategy_core/strategies/registry.py
_REGISTRY: dict[str, type[StrategyPlugin]] = {}

def register(plugin_cls: type[StrategyPlugin]) -> type[StrategyPlugin]:
    _REGISTRY[plugin_cls.strategy_id] = plugin_cls
    return plugin_cls

def get_strategy(strategy_id: str) -> type[StrategyPlugin]:
    try:
        return _REGISTRY[strategy_id]
    except KeyError:
        raise ContractError(f"unknown strategy_id {strategy_id!r}; "
                            f"registered: {sorted(_REGISTRY)}")  # fail-closed
```

**How QL selects for training:** QL's emitter (`alpha_lab/.../ml/strategy_contract.py:63`) is parameterized today by `training_mode` + `strategy_id`; PROPOSED it instead asks `get_strategy(strategy_id)` for the plugin and calls `feature_spec()`/`label_policy()`/`SectionModel` to build the contract — so the emitted section is *generated from the same plugin code* that runs live, killing the third-format drift (BASELINE §2(c): QL's hand-built dict is a third representation today).

**How TL selects for serving:** TL's `model_registry.activate(model_id)` (`model_registry.py:238-255`) already loads a contract and reads `strategy_id` opaquely (`:148`). PROPOSED it additionally does `plugin_cls = get_strategy(contract.strategy_id)` and instantiates it for the runtime — turning `strategy_id` from a label into a router. This is fail-closed: an unregistered `strategy_id` raises `ContractError` (re-raised as `ModelValidationError` by `_load_contract`, `:283-288`), leaving the prior active model untouched (`:244-245`).

**How a contract binds:** `contract.strategy_id` → `get_strategy(strategy_id)` → plugin whose `SectionModel` validates `contract.section` (§2.4) and whose `strategy_version` must match `contract.strategy_version` (§2.5). One lookup, three fail-closed checks.

### 2.4 The CONTRACT split — platform ENVELOPE + strategy SECTION

Today `StrategyContract` is **flat**: 20 fields mixing generic and strategy-specific concerns in one model (`schema.py:246-278`, quoted verbatim). The split:

**Platform-owned generic ENVELOPE** (validated by the platform loader, identical for every strategy):

| Envelope field | Source in today's flat contract |
|---|---|
| `contract_version` | `schema.py:255` |
| `platform_version` | replaces `engine_version` `schema.py:256` (§2.5) |
| `strategy_id` | `schema.py:257` (now also the registry key) |
| `strategy_version` | NEW (§2.5) |
| `instrument` / `tick_size` / `point_value` | `schema.py:260-262` |
| `model` (type/loss/file ref) | `schema.py:263` (`Model`, `:69-74`) |
| `feature_schema_envelope` | the generic `names`+`order_is_contractual`+`nan_policy` shell of `FeatureSet` (`schema.py:77-94`); the interaction/approach *partition* moves into the section |
| `data_requirements` | `schema.py:272` (`DataRequirements`, `:178-184`) |
| `provenance` | `schema.py:273` (`Provenance`, `:201-205`) |
| `class_map` | `schema.py:265` (`ClassMap`, `:208-243`) — generic 3-class shell |

**Strategy-owned typed SECTION** (a pydantic model the plugin owns via `SectionModel`):

| Section field (archetype 1) | Source in today's flat contract |
|---|---|
| `session_scheme` | `schema.py:266` (`SessionScheme`) — the "asia"/"london"/"ny" names are strategy choices, hardcoded today in `StrategyLevelState` (`runtime/levels.py:49`) |
| `level_scheme` | `schema.py:267` (`LevelScheme`, `:113-118`) |
| `touch_rule` | `schema.py:268` (`TouchRule`, `:121-129`) |
| `feature_windows` | `schema.py:269` (`FeatureWindows`, `:132-144`) |
| `label_policy` | `schema.py:270` (`LabelPolicy`, `:147-167`) — incl. `decision_offset_minutes` |
| `inference` | `schema.py:271` (`InferencePolicy`, `:170-175`) |
| `research_session_experiment` | `schema.py:274` (optional) |

```python
# PROPOSED — generic envelope; the section is opaque to the platform until dispatch
class StrategyEnvelope(_ContractModel):       # extra="forbid", frozen=True (schema.py:60-66)
    contract_version: str
    platform_version: str
    strategy_id: str
    strategy_version: str
    instrument: str
    tick_size: float
    point_value: float
    model: Model
    class_map: ClassMap
    feature_schema_envelope: FeatureSchemaEnvelope
    data_requirements: DataRequirements
    provenance: Provenance
    section: dict[str, Any]      # opaque here; typed by the strategy's SectionModel

# PROPOSED — archetype-1 plugin owns this section model
class TouchReversalSection(_ContractModel):
    session_scheme: SessionScheme
    level_scheme: LevelScheme
    touch_rule: TouchRule
    feature_windows: FeatureWindows
    label_policy: LabelPolicy            # barrier_mode = "fixed_points"
    inference: InferencePolicy
    research_session_experiment: ResearchSessionExperiment | None = None
```

**Validation + dispatch.** The platform loader (extending `loader.py:28-77`) validates the envelope, checks `contract_version` and `platform_version` (fail-closed), then resolves `plugin_cls = get_strategy(envelope.strategy_id)` and dispatches: `section = plugin_cls.SectionModel.model_validate(envelope.section)`. Because each section model is `extra="forbid"` (`schema.py:66`), each strategy contributes *only* its own section and unknown keys still fail closed. This directly fixes the three TL divergences (BASELINE §2(c)): there is no second hand-written schema to drift, because the platform validates the envelope and the *one* plugin owns the section.

### 2.5 The VERSION split — platform_version + per-strategy strategy_version/strategy_id

**Today's coupling.** There is a single global `ENGINE_VERSION = "strategy_core_engine_v3"` (`__init__.py:54`). Every change — even one that touches only the touch strategy's barriers — bumps the whole engine string, and *both* consumers must re-sync: QL re-emits (its emitter stamps `engine_version: ENGINE_VERSION`), and TL must accept the new string (today via a divergent optional-vs-required field, `domain/contracts/strategy_contract.py:168` vs `schema.py:256`). The fail-close lives in the loader (`loader.py:64-70` SC; TL inline `:230-237`).

**PROPOSED split:**

- `platform_version` — pinned once by both consumers, bumped only when the *platform contract* changes (event types, candle semantics, envelope shape, serialization). Rarely changes. Fail-closed in the platform loader exactly as `engine_version` is today (`loader.py:64-70`).
- `strategy_version` + `strategy_id` — owned per plugin (`StrategyPlugin.strategy_version`). The loader, after registry lookup, asserts `contract.strategy_version == plugin_cls.strategy_version` and fail-closes on mismatch. A strategy logic/barrier change bumps only *that* strategy's version.

**Why this removes the coupling:** retuning the touch strategy's TP/SL bumps `strategy_version` for `strategy_id="touch_reversal"` only. The platform string is untouched, so QL and TL do *not* re-sync the platform pin, and *other* strategies' bundles remain valid. Conversely, a platform change (e.g. adding the `INTERVAL` close reason) bumps `platform_version` once and is a single deliberate re-sync — not an implicit consequence of strategy churn. Both checks remain fail-closed and independent.

### 2.6 Archetype validation

**Archetype 1 — touch / zone-reversal / 3-class MAE-first (the existing strategy).** Maps cleanly:

- `strategy_id="touch_reversal"`, registered via `@register`.
- `required_bars() -> (BarSpec(TICK, 147, "147t"), …)`; `decision_bar_label() -> "147t"`. This reproduces today's `decision_timeframe = min(timeframes)` pin (`strategy_core_service.py:99-111`, `state.py:188`).
- `configure(section: TouchReversalSection, ctx)` builds the level/zone state (today `StrategyLevelState`, `runtime/levels.py:39-50`) from the section's `level_scheme`/`session_scheme`.
- `on_bar_closed(bar, ctx)`: when `bar.label == "147t"`, run `build_zones → detect_touches` (today `state.py:274-280`, `decisions/zones.py:23`, `decisions/touch.py:47`). A touch is a single-phase `SetupState(phase="touched", status="active")` plus a `DecisionEvent` whose `entry_reference="trade_price_at_decision"` and `barrier.kind="fixed_points"`.
- `Barrier(fixed_points)`: `stop_price`/`target_price` from `tp_points=15`/`sl_points=30` exactly as `resolve_outcome` consumes them (`outcomes.py:127-136`); `label_policy()` declares `barrier_mode="fixed_points"`, `decision_offset_minutes=5`, flatten 16:40 / cutoff RTH_END (`honest_entry.py:76-89`).
- `feature_spec()` returns the six current features partitioned into 3 interaction + 3 approach (`decisions/features.py`).
- The NY-session inference gate is `InferencePolicy` in the section (`schema.py:170-175`). **PASS.**

**Archetype 2 — HTF-FVG → parent-context → 1m-retest-lock → opposing-inversion (the future multi-stage strategy).** Maps onto the *same* interface:

- `strategy_id="ifvg_smc"`, `strategy_version="v1"`.
- **Multi/mixed-timeframe, incl. TIME bars:** `required_bars()` returns `BarSpec(TIME, 60, "1m")`, `BarSpec(TIME, 180, "3m")`, `300/"5m"`, `600/"10m"`, `900/"15m"`, `1800/"30m"`, `3600/"1H"`, `14400/"4H"` (ifvg-strat.md §4.2). `decision_bar_label() -> "1m"` (1m execution chart, ifvg-strat.md §4.1). This is precisely what the new `BarSpec`/TIME-bar platform capability (§2.1(3)) exists to serve — and the reason the current tick-only engine (`streaming.py:180-181`, `CloseReason` `types.py:51-55`) cannot host it today.
- **Multi-stage setup state (arming/locking/invalidation):** `on_bar_closed` walks the ifvg-strat.md §9 state machine, emitting `SetupState` with `phase ∈ {"scanning","htf_tapped","parent_selected","parent_locked","opposing_selected","inverted","armed","invalidated"}`. "Parent locks and cannot be replaced" (ifvg-strat.md §7.3) is a `phase="parent_locked"` transition; "reset on full fill before entry" is `status="invalidated"`; the 30-bar post-inversion expiry is `status="expired"`. The `evidence` mapping carries the audit payload the doc's §12 requires (which HTF zone, parent tf, opposing gap, inversion bar) — surfaced over the generic envelope via `emitted_event_types()` as `setup.updated` payloads.
- **Per-setup R-relative barriers:** the `DecisionEvent.barrier.kind="r_relative"`, where `stop_price` returns the **manipulation-swing** level (lowest 1m low / highest 1m high from parent retest through entry, ifvg-strat.md §5.9/§11.2) and `target_price` returns `entry ± 1·R` with `R = |entry − stop_price|` (ifvg-strat.md §6.3/§11.5). `entry_reference="confirmation_close"` (ifvg-strat.md §11.1). `label_policy()` declares `barrier_mode="r_relative"`, so the platform's outcome/parity machinery scores R-normalized excursions rather than fixed points — and the existing MAE-first kernel (`classify_mae_first`, `outcomes.py:63-106`) is reused by feeding it `tp_points/sl_points` *derived per-setup from R* (TP=R, SL=R), proving the same scoring engine serves both barrier modes.
- **Features/contract section:** `feature_spec()` declares FVG-geometry features; `SectionModel` is an `IfvgSmcSection` owning FVG min-gap (8 ticks), parent reaction window (24 bars), proximity (80 ticks), parent-priority order, and the America/New_York session windows (ifvg-strat.md §6) — a *different* typed section, validated by the same envelope-dispatch path (§2.4). **PASS.**

**Conclusion: the interface expresses both archetypes without revision.** The single genuinely new platform capability required is the `BarSpec`/TIME-bar close trigger (§2.1(3)); everything else — multi-stage setup state, mixed-timeframe declaration, and R-relative barriers — is carried by the Protocol's `SetupState`, `required_bars()`, and `Barrier` abstractions, with the existing MAE-first kernel and parity framework reused under both. No redesign is needed.

---

## 3. Symbol-by-symbol move map

Legend for destination column: **PLATFORM** = stays in (or moves into) the generic, strategy-agnostic `strategy_core` platform core; **TOUCH-STRATEGY-PLUGIN** = moves into the archetype-1 `touch_reversal` plugin (PROPOSED `strategy_core/strategies/touch_reversal/`); **COLLAPSED/DELETED** = redundant duplicate or per-run literal eliminated by the split. CURRENT paths are real and verified against source; destinations labelled PROPOSED are target design.

### 3.1 Strategy-Core engine symbols

| Symbol / module (CURRENT path) | Destination | One-line reason |
|---|---|---|
| `build_zones` — `Strategy-Core/src/strategy_core/decisions/zones.py:23-25` | **TOUCH-STRATEGY-PLUGIN** | Greedy proximity-merge of PDH/PDL/session levels into zones is touch-reversal-specific geometry (`zone_proximity_pts`, mean rep-price, ties→LOW); other archetypes (iFVG) build no zones. |
| `Zone` dataclass + `zone.touched` mutable flag (consumed in `zones.py`/`touch.py:87-97`) | **TOUCH-STRATEGY-PLUGIN** | The zone/first-touch object model exists only to serve `build_zones`→`detect_touches`; it is not a generic platform type. |
| `is_touch` — `decisions/touch.py:34` | **TOUCH-STRATEGY-PLUGIN** | Closed-interval straddle (`bar_low <= rep <= bar_high`) is the touch-reversal trigger predicate. |
| `detect_touches` — `decisions/touch.py:47-54` | **TOUCH-STRATEGY-PLUGIN** | First-touch-per-zone-per-day detection + v3 `available_from` look-ahead gate is the core of archetype 1's `on_bar_closed` hook; becomes the plugin's `SetupState`→`DecisionEvent` producer. |
| `resolve_outcome` — `decisions/outcomes.py:127-136` | **PLATFORM** (shared kernel) | Pure forward-scan MFE/MAE barrier engine takes `entry_points`/`tp_points`/`sl_points`/`trap_mfe_min` as args, holds NO session/touch meaning; PROPOSED Barrier Protocol (fixed_points AND r_relative) reuses it unchanged for both archetypes. |
| `classify_mae_first` — `decisions/outcomes.py:63-71` | **PLATFORM** (shared kernel) | Adverse-first label ladder is a generic barrier classifier; iFVG reuses it by deriving per-setup tp/sl from R. Barriers are FIXED POINTS today (`outcomes.py:95-99`), not R-relative — the plugin's `Barrier` adds R. |
| `OutcomeResult` — `decisions/outcomes.py:109-124` | **PLATFORM** (shared kernel) | Return type of the shared `resolve_outcome` kernel; neutral MFE/MAE/label record consumed by every plugin. |
| `resolve_honest_outcome` — `decisions/honest_entry.py:76-89` | **TOUCH-STRATEGY-PLUGIN** | Touch→decision-offset(+5m)→flatten/cutoff/no_fill/no_forward orchestration is the touch-reversal label policy; it wraps the PLATFORM `resolve_outcome` kernel. `trade_price_at` callable is supplied by `PlatformContext`. |
| `HonestEntryDrop` — `decisions/honest_entry.py:56-73` | **TOUCH-STRATEGY-PLUGIN** | Drop-reason record specific to the honest-entry orchestration above. |
| `int_time_beyond_level` — `decisions/features.py:68-75` | **TOUCH-STRATEGY-PLUGIN** | Level-relative interaction feature (dwell on adverse side of a level); meaningless without a touch level. Declared via plugin `feature_spec()`. |
| `int_time_within_2pts` — `decisions/features.py:103-110` | **TOUCH-STRATEGY-PLUGIN** | Level-band dwell feature (`within_band_pts`); level-relative, touch-specific. |
| `int_absorption_ratio` — `decisions/features.py:130-137` | **TOUCH-STRATEGY-PLUGIN** | At-level vs through-level volume ratio; defined relative to the touched level. |
| `app_large_trade_vol_pct` — `decisions/features.py:168-172` | **TOUCH-STRATEGY-PLUGIN** | Approach-window feature scoped to the pre-touch trade window; part of the touch-reversal feature set. |
| `app_avg_trade_size` — `decisions/features.py:194` | **TOUCH-STRATEGY-PLUGIN** | Approach-window mean trade size; same touch-scoped window. |
| `app_max_spread` — `decisions/features.py:206` | **TOUCH-STRATEGY-PLUGIN** | Approach-window max quote spread (consumes `Quote`s); touch-reversal feature. (All six are the exact `features.py:58-65 __all__`.) |
| `classify_session` — `decisions/sessions.py:71-74` | **PLATFORM** | Pure tz/`SessionScheme`-parameterized window classifier; generic session calendar used by candles, levels, and any plugin via `PlatformContext.session_at`. |
| `trading_day_for` — `decisions/sessions.py:112-122` | **PLATFORM** | Generic 18:00-ET trading-day rollover used by `CandleEngine.process_trade` (`streaming.py`); platform-level calendar primitive. |
| `is_in_closed_window` — `decisions/sessions.py:125-141` | **PLATFORM** | Generic closed-window predicate over a `SessionScheme`. |
| `RESEARCH_SESSION_SCHEME` (v3 ET scheme, `constants.py:170-179`) | **PLATFORM** (default) + plugin section override | The scheme axis is the one real parameterization; threads through `CandleEngine`/`StrategyLevelState`/`classify_session`. PROPOSED: default lives in platform, but the concrete asia/london/ny window set rides in the plugin's `TouchReversalSection.session_scheme` since names are hardcoded today. |
| Hardcoded session NAMES `"asia"`/`"london"` in `StrategyLevelState` (`runtime/levels.py:49,56,74,90`) | **TOUCH-STRATEGY-PLUGIN** | Which sessions produce levels is a strategy choice, not platform config; the hardcoded names are NOT scheme-driven today, so they move with the level-tracking strategy. |
| `StrategyLevelState` + `StrategyLevelState.levels()`/`zones()` — `runtime/levels.py:39-100` | **TOUCH-STRATEGY-PLUGIN** | PDH/PDL + asia/london high/low tracking, the `available_from` availability gate, and `zones()`→`build_zones` are entirely touch-reversal strategy state; becomes plugin-owned state configured via `configure(section, ctx)`. |
| `_Range` / `_DaySummary` helpers — `runtime/levels.py:17-36` | **TOUCH-STRATEGY-PLUGIN** | Internal accumulators for `StrategyLevelState`; move with it. |
| `StrategyRuntime` — `runtime/state.py:170-199` | **PLATFORM** (re-skinned) | Event-sourced loop, ring buffer, reset/snapshot are generic; KEEP `process_event` dispatch (`state.py:229-236`) verbatim. The hardwired touch/zone/level block (`state.py:271-280`) is REPLACED by plugin-hook calls. PROPOSED: gains a `plugin` param (no plugin seam exists today). |
| Hardwired touch pipeline inside `StrategyRuntime._process_trade` (`state.py:262-290`, module imports `state.py:11-17`) | **TOUCH-STRATEGY-PLUGIN** | The inline `_zones_for_detection`→`detect_touches`→`_touched_zone_keys` decision-timeframe gating (`state.py:271-280`) is the only strategy logic baked into the loop; it becomes the plugin's `on_bar_closed`. |
| `RuntimeUpdate` — `runtime/state.py:113-137` | **PLATFORM** (generic frame) | Sparse-delta envelope (`feed_status`/`bars`/`warnings`/`last_quote` generic). PROPOSED: `levels`/`zones`/`touches` fields become a generic plugin-event payload riding the frame, so the platform stays strategy-agnostic. |
| `RuntimeSnapshot` — `runtime/state.py:140-167` | **PLATFORM** (generic frame) | Full-state snapshot; same treatment — strategy-specific fields become opaque plugin payload, `feed_status`/bars/`session`/`trading_day` stay platform. |
| `FeedStatus` — `runtime/state.py:91-110` | **PLATFORM** | Pure feed/replay status; no strategy meaning. |
| `to_dict` serializers + helpers `_dt/_bar/_level/_zone/_touch/_quote/_warning` — `runtime/state.py:22-88,101-167` | **PLATFORM** (generic) / **PLUGIN** (`_level`/`_zone`/`_touch`) | Bar/quote/warning/feed serializers are the platform wire boundary; `_level`/`_zone`/`_touch` serialize plugin-owned types and move to the plugin's `emitted_event_types()` payload schemas. |
| `CandleEngine` (streaming) — `candles/streaming.py:100-216` | **PLATFORM** | Generic tick-bar builder, dependency-light, no strategy meaning. PROPOSED: extended from TICK-ONLY (`streaming.py:180-181`) with a new `BarSpec{kind: TICK|TIME}` + `CloseReason.INTERVAL` trigger — the ONE genuinely new platform capability (TIME bars are UNSUPPORTED today). |
| `build_tick_bars_from_frame` (batch) — `candles/batch.py:38-44` | **PLATFORM** | Vectorized parity twin of streaming (byte-locked via `test_candle_parity.py`); the only pandas-importing engine module. Extended for TIME bars alongside streaming. |
| `CandleUpdate` / `_MutableCandle` / `CloseReason` — `candles/streaming.py:74-83,31-71`; `types.py:51-55` | **PLATFORM** | Generic candle data shapes + close-reason enum; `CloseReason` gains `INTERVAL` member for TIME bars. |
| `Bar`/`Trade`/`Quote`/`Side`/`Direction`/`Level`/`Touch`/`SessionScheme`/`SessionInfo` — `types.py` | **PLATFORM** for `Bar`/`Trade`/`Quote`/`Direction`/`SessionScheme`/`SessionInfo`; **PLUGIN** for `Level`/`Touch`/`Side` | `Direction` (LONG/SHORT, `types.py:44-48`) is generic — every directional strategy emits it (iFVG is long/short too, see §2.6) — so it stays PLATFORM. `Side` (HIGH/LOW, `types.py:37-41`) is used ONLY by level/zone/touch code (`zones.py:85-86`, `touch.py:53,98`, `levels.py:88-96`, the `Level.side`/`Zone.side` fields `types.py:138,159`, and `DIRECTION_FROM_SIDE` `constants.py:66-68`); no platform market-data type uses it, and `Trade.side` is a DIFFERENT type — `str | None` (`types.py:67`), the trade aggressor, not the `Side` enum. So `Side` is touch-reversal vocabulary → PLUGIN with `Level`/`Touch`. |
| `DIRECTION_FROM_SIDE` (`Side`→`Direction` map) — `constants.py:66-68` (exported `:308`) | **TOUCH-STRATEGY-PLUGIN** | Typed `dict[Side, Direction]` — it references the plugin `Side` enum, so it cannot stay in platform `constants.py` or the platform would import a plugin type. Imported only by `detect_touches` (`touch.py:28,53`) and QL's contract emitter (`strategy_contract.py:165-168`, `k.DIRECTION_FROM_SIDE.items()`); no other platform module imports it. Relocate into the touch plugin alongside `Side`; QL imports it from the plugin (not platform `constants.py`) when generating the touch contract section (§2.3). |
| `make_bar_id` — `strategy_core` (re-exported) | **PLATFORM** | Generic bar identity helper. |

### 3.2 Contract schema sections — `Strategy-Core/src/strategy_core/contract/schema.py`

| Section model (CURRENT path) | Destination | One-line reason |
|---|---|---|
| `StrategyContract` (20 fields) — `schema.py:246-278` | **SPLIT**: PLATFORM `StrategyEnvelope` + PLUGIN `SectionModel` | The flat contract decomposes into a platform-owned envelope (versions, instrument, model, class_map, feature_schema, data_requirements, provenance, opaque `section`) + a strategy-typed section; this is what kills the third-format TL drift. |
| `_ContractModel` base (`extra="forbid", frozen`) — `schema.py:60-66` | **PLATFORM** | Shared base reused by both envelope and section; `extra="forbid"` per section is what fails unknown keys closed. |
| `Model` — `schema.py:69-74` | **PLATFORM** (envelope) | Model file/type/loss is generic bundle metadata, strategy-independent. |
| `FeatureSet` (+ partition validator) — `schema.py:77-94` | **PLATFORM** envelope shell, **PLUGIN** content | `names`/`order_is_contractual` is platform feature-schema; the interaction/approach partition is touch-reversal-specific and is declared by the plugin's `feature_spec()`. |
| `ClassMap` (+ validators, `labels`) — `schema.py:208-243` | **PLATFORM** (envelope) | Contiguous-from-0 label map is generic model-output metadata. |
| `SessionScheme` + `SessionWindow` — `schema.py:97-110` | **TOUCH-STRATEGY-PLUGIN** (`TouchReversalSection`) | Concrete asia/london/ny windows are this strategy's level-source calendar; lives in the typed section. |
| `LevelScheme` — `schema.py:113-118` | **TOUCH-STRATEGY-PLUGIN** | `pdh_pdl_source`/`session_levels`/`available_from_guard` describe touch-reversal level construction. |
| `TouchRule` — `schema.py:121-129` | **TOUCH-STRATEGY-PLUGIN** | Zone proximity / rep-price / direction-from-side IS the touch rule; pure plugin section. |
| `FeatureWindows` — `schema.py:132-144` | **TOUCH-STRATEGY-PLUGIN** | Interaction/approach window minutes + `within_band_pts`/`level_proximity_pts`/`mid_price_source` parameterize the touch features. |
| `LabelPolicy` (incl. `decision_offset_minutes:161`) — `schema.py:147-167` | **TOUCH-STRATEGY-PLUGIN** | Entry-reference/decision-offset/tp/sl/trap/forward-cutoff is the honest-entry label policy; PROPOSED adds `barrier_mode` (fixed_points vs r_relative). |
| `InferencePolicy` — `schema.py:170-175` | **TOUCH-STRATEGY-PLUGIN** | `eligible_class`/`eligible_session`/`confidence_gate` (NY) is the touch-reversal serving gate. |
| `DataRequirements` — `schema.py:178-184` | **PLATFORM** (envelope) | Book-level/live+replay schemas/depth usage are ingest-layer requirements the platform enforces; PROPOSED derived from the plugin's `required_bars()`. |
| `Provenance` — `schema.py:201-205` | **PLATFORM** (envelope) | Dataset hash + catboost params are generic training provenance. |
| `ResearchSessionExperiment` — `schema.py:187-198` | **TOUCH-STRATEGY-PLUGIN** | Train/eval/production-gate session split is a touch-reversal research artifact; absent from the TL local copy entirely. Moving it into the section removes the divergence. |

### 3.3 Versioning + loader

| Symbol (CURRENT path) | Destination | One-line reason |
|---|---|---|
| `ENGINE_VERSION = "strategy_core_engine_v3"` — `Strategy-Core/src/strategy_core/__init__.py:54` | **SPLIT → PLATFORM `platform_version`** | Single global stamp couples any change to a whole-engine bump + dual-consumer resync; replaced by `platform_version` (bumped only on platform-contract change, fail-closed in loader). |
| (implicit) per-strategy versioning — none today | **PLUGIN `strategy_version`/`strategy_id`** (PROPOSED, new) | Retuning touch barriers should bump only `touch_reversal`'s version; this per-plugin axis does not exist today. |
| `CONTRACT_VERSION = "trade_lab_contract_v1"` — `__init__.py:57` | **PLATFORM** | Stays single-sourced; envelope-level version, fail-closed in loader. |
| `load_strategy_contract` (canonical, `expected_engine_version` hook) — `contract/loader.py:28-77` | **PLATFORM** (extended) | Validates envelope, fail-closes `contract_version`/`platform_version`, resolves plugin via registry, then `section = plugin.SectionModel.model_validate(envelope.section)`. The pre-`model_validate` engine check (`loader.py:64-70`) becomes the platform-version check. |
| (PROPOSED, new) `strategy_core/strategies/registry.py` `@register` + `get_strategy(strategy_id)` | **PLATFORM** (new module) | Single-sourced registry so SHA-pinned TL and unpinned-floating QL resolve plugins identically; turns `strategy_id` from a label into a fail-closed router. No strategy registry/abstraction exists anywhere today (confirmed-absent grep). |

### 3.4 Trade-Lab consumer symbols — `Trade-Lab/backend/src/trade_lab/`

| Symbol (CURRENT path) | Destination | One-line reason |
|---|---|---|
| `CandleEngine` + `Candle`/`_MutableCandle`/`CandleUpdate` — `domain/candles.py:103-176` | **COLLAPSED/DELETED** | A legacy local tick-bar reimplementation (verified: trade-count close `candles.py:169`, `CandleCloseReason{COMPLETE,END_OF_DAY}` `:11-13`) that duplicates the platform `CandleEngine`; the service already runs the engine — this domain copy is dead weight to retire. |
| `classify_session`/`SessionClassifier`/`SessionName`/`SessionInfo` — `domain/sessions.py:11-93` | **COLLAPSED/DELETED** | Local **Chicago** ("America/Chicago", `sessions.py:8`) calendar with NY-end 16:00 CT — the non-canonical CT scheme the platform v3 ET scheme replaces; superseded by platform `classify_session`. |
| `SessionLevelEngine` + `LevelKind`/`LevelDirection`/`DisplayLevel`/`TouchEvent`/`SESSION_LEVELS`/`LEVEL_ORIGIN` — `domain/levels.py:16-312` | **COLLAPSED/DELETED** | Local **exact-price** touch engine (`trade.price_ticks != level_price_ticks` at `levels.py:272`) — a different touch semantic from the platform's bar-range/zone-merge `detect_touches`; superseded by the touch-reversal plugin via the service. |
| `Outcome`/`ResolutionType` — `domain/outcomes.py:19-40` | **COLLAPSED/DELETED** (consume plugin `OutcomeResult`) | Local resolved-outcome shape feeding the TL-local tracker; redundant once the plugin's shared `resolve_outcome`/`OutcomeResult` is the single labeler. |
| `OutcomeTracker` (LEVEL-price entry) — `services/inference/outcome_tracker.py:107,141-145` | **COLLAPSED/DELETED** | Re-implements the MAE-first ladder with LEVEL-price entry (NOT the engine's honest `trade_price_at` fill); a known divergence the v3 repoint retires in favor of the plugin's `resolve_honest_outcome`. |
| `StrategyCoreService.process_market_event` + DTO mappers — `services/strategy_core_service.py:137-148,153-322` | **PLATFORM-adjacent, KEPT** | Thin neutral→TL adapter that owns NO strategy meaning; survives the split mapping the generic `RuntimeUpdate` frame. PROPOSED: the plugin-event payload replaces direct `levels`/`zones`/`touches` mapping. |
| `StrategyRuntime(...)` instantiation pinning `decision_timeframe=min(...)` — `strategy_core_service.py:99-111` | **PLATFORM-adjacent, KEPT** | Construction site; PROPOSED gains `plugin=get_strategy(contract.strategy_id)` and reads `decision_bar_label()` from the plugin instead of pinning `min(timeframes)`. |
| `engine_version` surfaced via `strategy_core.ENGINE_VERSION` — `strategy_core_service.py:116-118` | **PLATFORM (repointed)** | Repoints to `platform_version`; the version axis the service reports changes with the split. |
| `_run_inference` + local `RuntimeUpdate{observations,predictions,outcomes}` — `services/runtime.py:313-346,38-63` | **TL-KEPT (soft seam)** | Inference attach is a TL concern (soft seam: no-model → `()`); KEPT, but `_track_outcomes` repoints onto the plugin's honest labeler instead of the local `OutcomeTracker`. |
| `model_registry.activate` / fail-close stack — `services/model_registry.py:238-255,283-348` | **TL-KEPT (extended)** | Atomic fail-closed activation stays; PROPOSED adds `plugin_cls=get_strategy(contract.strategy_id)` so `strategy_id` (today opaque label at `:148`) becomes a router. |
| Contract import `from trade_lab.domain.contracts import ...` — `model_registry.py:26` | **REPOINTED → PLATFORM** | Repoint to `strategy_core.contract` (envelope+section), eliminating the local schema. |
| `domain/contracts/strategy_contract.py` (TL LOCAL copy: schema+loader) — `strategy_contract.py:1-244` | **COLLAPSED/DELETED** | The third-format hand-written copy with 3 confirmed divergences (`engine_version` optional `:168`; `LabelPolicy` missing `decision_offset_minutes` `:95-103`; no `ResearchSessionExperiment`); deleting it and repointing onto the platform envelope/section is what fixes all three. |
| `WebSocketBroadcaster.messages_for_update` / `_model_status_message_if_changed` — `services/broadcaster.py:77-112,114-126` | **TL-KEPT (extended)** | `RuntimeUpdate`→`ws.v1` fan-out stays; the touch/level/zone delta types become a generic plugin-event message type carrying the plugin's typed payload. |
| `Envelope`/`MESSAGE_VERSION="ws.v1"`/`MessageType` Literal/`make_envelope`/`SnapshotPayload`/`ModelStatusDTO` — `api/dto.py:24-38,214-219,429-444,180-192,131-142` | **TL-KEPT (`extra="forbid"`)** | Frozen `ws.v1` wire contract stays platform↔UI boundary; PROPOSED adds a generic strategy-event message type whose payload is the plugin's declared schema (adding any type is a gated wire change). |

### 3.5 Quant-Lab consumer symbols — `Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/`

| Symbol (CURRENT path) | Destination | One-line reason |
|---|---|---|
| `use_engine` dispatch flag + engine route — `dashboard_utility_builder.py:244,281-293` | **QL-KEPT (repointed)** | Routes batch decision to the engine; survives, but routes through the plugin pipeline resolved by `strategy_id` rather than the hardwired path. |
| `process_single_date_engine` — `engine_decision.py:171-182` | **QL-KEPT (repointed)** | Batch driver of `build_zones→detect_touches→resolve_honest_outcome→6 features`; repoints those calls onto the touch-reversal plugin's batch surface (same math, plugin-owned). |
| Direct engine imports (`build_zones`, `detect_touches`, `resolve_honest_outcome`, 6 features, etc.) — `engine_decision.py:45-70` | **QL-KEPT (repointed)** | Re-source from the plugin module (touch-reversal) for strategy symbols; platform symbols (`Bar`/`Trade`/`Quote`/`classify_session`) stay from `strategy_core`. |
| Undeclared/unpinned `strategy_core` dependency — `pyproject.toml:12-48` (ABSENT) | **PLATFORM dep (must DECLARE)** | `strategy_core` is imported but NOT a declared dep (no requirements/lock/.pth), so QL can float to a different SC commit than SHA-pinned TL; the registry being single-sourced in SC mitigates, but the dep must be pinned. |
| `build_strategy_contract` emitter — `strategy_contract.py:63-220` | **QL-KEPT (regenerated from plugin)** | Emits the full v3 dict (incl. `decision_offset_minutes:191`, `research_session_experiment:204`). PROPOSED: generates the envelope+section FROM the plugin's `feature_spec()`/`label_policy()`/`SectionModel`, killing the no-restated-literals drift surface and the TL-incompatibility. |
| `_session_block`/`_hhmm` emitter helpers — `strategy_contract.py:50-60` | **QL-KEPT** | Local formatting helpers reading `k.RESEARCH_SESSION_SCHEME`; stay, but feed the plugin-derived section. |
| Imports `CONTRACT_VERSION, ENGINE_VERSION, constants as k` — `strategy_contract.py:38-39` | **REPOINTED** | `ENGINE_VERSION` use becomes `platform_version`; structural `k.*` values become plugin-declared (`SectionModel` defaults) so the emitter no longer single-sources strategy semantics from platform constants. |

### 3.6 Items with NO current home (PROPOSED, net-new — not a move)

| Target symbol (PROPOSED) | Destination | Reason it is net-new |
|---|---|---|
| `StrategyPlugin` Protocol, `SetupState`, `DecisionEvent`, `Barrier` Protocol, `PlatformContext`, `BarSpec`, `StrategyStep` | **PLATFORM (interfaces) + PLUGIN (impls)** | Confirmed-absent: zero `Strategy(Protocol\|ABC\|Base)`/`register_strategy`/`entry_points`/`STRATEGY_REGISTRY` hits across all three repos; the only `class *Strategy*(` matches are pydantic models. The plugin seam, multi-stage setup state, and R-relative Barrier do not exist today and must be introduced. |
| `CloseReason.INTERVAL` + TIME `BarSpec` close trigger | **PLATFORM (new candle capability)** | TIME/minute bars are UNSUPPORTED today (tick-count close only: `streaming.py:169`; `CloseReason{COMPLETE,END_OF_DAY}` `types.py:51-55`); archetype 2 (iFVG, 8 TIME specs) needs this one genuinely new platform capability. |

### 3.7 Net of the move (decision summary)

- **PLATFORM keeps:** event loop (`process_event` verbatim), candle engine (streaming+batch, +TIME extension), session calendar (`classify_session`/`trading_day_for`/`is_in_closed_window`), the shared barrier kernel (`resolve_outcome`/`classify_mae_first`/`OutcomeResult`), the contract envelope + loader + registry, market-data types (`Bar`/`Trade`/`Quote`/`SessionScheme`) plus the generic `Direction` primitive enum (`Side` HIGH/LOW is touch/level vocabulary — PLUGIN), and the `ws.v1` transport.
- **TOUCH-STRATEGY-PLUGIN owns:** `build_zones`, `is_touch`/`detect_touches`, `resolve_honest_outcome`/`HonestEntryDrop`, all six features, `StrategyLevelState`(+`_Range`/`_DaySummary`), the hardcoded asia/london level set, the `Level`/`Touch`/`Side` domain vocabulary (`Side` HIGH/LOW is used only by level/zone/touch code; the generic `Direction` enum stays PLATFORM — see the `types.py` row above), and the seven strategy contract sections (`SessionScheme`/`SessionWindow`/`LevelScheme`/`TouchRule`/`FeatureWindows`/`LabelPolicy`/`InferencePolicy`/`ResearchSessionExperiment`).
- **COLLAPSED/DELETED:** TL's entire legacy `domain/` strategy stack (`candles.py`, `sessions.py`-CT, `levels.py`-exact-price, `outcomes.py`), TL's local `domain/contracts/strategy_contract.py` (the 3-divergence third format), and TL's `OutcomeTracker` (level-price entry) — all superseded by the platform/plugin split routed through the existing `StrategyCoreService` adapter.

---

## 4. Touch strategy as strategy #1 (the proof)

This section shows the concrete retrofit of today's hardwired touch pipeline into a single `TouchReversalStrategy` plugin behind the §2 `StrategyPlugin` protocol. Nothing in the decision/feature/label kernel changes; the plugin is a thin declaration + dispatch shell wrapping functions that already exist verbatim. The acceptance criterion is that every existing parity/golden harness passes UNCHANGED.

### 4.1 What is being wrapped (CURRENT, hardwired)

Today there is no strategy seam. The "strategy" is the inline touch block inside `StrategyRuntime._process_trade`, which runs only on completed bars whose `timeframe_ticks == self.decision_timeframe`. CURRENT, `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/runtime/state.py:262-290`:

```python
    def _process_trade(self, trade: Trade) -> RuntimeUpdate:
        self._last_event_ts_utc = trade.event_ts_utc
        candle_update = self.candles.process_trade(trade)
        if candle_update.completed:
            self._recent_closed_bars.extend(candle_update.completed)
            if len(self._recent_closed_bars) > self._recent_closed_bar_limit:
                del self._recent_closed_bars[: len(self._recent_closed_bars) - self._recent_closed_bar_limit]
        levels = self.level_state.process_trade(trade)
        touches: list[Touch] = []
        for bar in candle_update.completed:
            if bar.timeframe_ticks != self.decision_timeframe:
                continue
            zones = self._zones_for_detection(bar.trading_day)
            detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
            for touch in detected:
                self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))
            touches.extend(detected)
        ...
```

The §2 split keeps lines 263-269 (candle fold + recent-bar ring) and the level fold on the PLATFORM side, and lifts the touch block at `state.py:271-280` into the plugin's `on_bar_closed` hook. The functions that block calls are exactly the ones the plugin wraps:

- `detect_touches(...)` — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/decisions/touch.py:47-54` (verbatim):

```python
def detect_touches(
    bars: Sequence[Bar],
    zones: list[Zone],
    *,
    tick_size: float,
    trading_day: date,
    direction_from_side: Mapping[Side, Direction] = DIRECTION_FROM_SIDE,
) -> list[Touch]:
```

- `build_zones(...)` — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/decisions/zones.py:23-25` (verbatim), reached today via `StrategyLevelState.zones()` and `StrategyRuntime._zones_for_detection`:

```python
def build_zones(
    levels: list[Level], *, zone_proximity_pts: float = ZONE_PROXIMITY_PTS
) -> list[Zone]:
```

- `resolve_honest_outcome(...)` (production label/outcome) — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/decisions/honest_entry.py:76-89` (verbatim):

```python
def resolve_honest_outcome(
    touch: Touch,
    day_bars: Sequence[Bar],
    trade_price_at: Callable[[datetime], float | None],
    *,
    tick_size: float,
    tp_points: float,
    sl_points: float,
    trap_mfe_min: float,
    decision_offset_minutes: int = DECISION_OFFSET_MINUTES,
    flatten_time: time = FLATTEN_TIME,
    rth_end: time = RTH_END,
    timezone: str = SESSION_TIMEZONE,
) -> OutcomeResult | HonestEntryDrop:
```

- `resolve_outcome(...)` (pure forward-scan it delegates to) — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/decisions/outcomes.py:127-136` (verbatim):

```python
def resolve_outcome(
    entry_points: float,
    direction: Direction,
    forward_bars: Sequence[Bar],
    tick_size: float,
    *,
    tp_points: float,
    sl_points: float,
    trap_mfe_min: float,
) -> OutcomeResult:
```

- the MAE-first kernel `classify_mae_first(...)` — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/decisions/outcomes.py:63-71` (verbatim), whose ladder is adverse-first (`outcomes.py:94-106`, verified: `if max_mae >= sl_points: return TRAP_REVERSAL if max_mfe >= trap_mfe_min else AGGRESSIVE_BLOWTHROUGH` then `if max_mfe >= tp_points: return TRADEABLE_REVERSAL`):

```python
def classify_mae_first(
    max_mfe: float,
    max_mae: float,
    *,
    tp_points: float,
    sl_points: float,
    trap_mfe_min: float,
    forced: bool = False,
) -> str | None:
```

- the six declared features — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/decisions/features.py:58-65` (verbatim `__all__`):

```python
__all__ = [
    "int_time_beyond_level",
    "int_time_within_2pts",
    "int_absorption_ratio",
    "app_large_trade_vol_pct",
    "app_avg_trade_size",
    "app_max_spread",
]
```

PROPOSED: `TouchReversalStrategy` calls every one of these UNCHANGED. The retrofit is "move the call site, not the callee."

### 4.2 The `TouchReversalStrategy` plugin (PROPOSED)

PROPOSED shape, expressed against the §2 `StrategyPlugin` protocol. Pseudocode — the bodies delegate to the CURRENT functions above:

```python
# PROPOSED — strategy_core/strategies/touch_reversal.py
@register("touch_reversal")
class TouchReversalStrategy:                       # runtime_checkable StrategyPlugin
    strategy_id = "touch_reversal"
    strategy_version = "touch_reversal_v3"          # was the global ENGINE_VERSION
    SectionModel = TouchReversalSection             # see §4.3

    def configure(self, section: TouchReversalSection, ctx: PlatformContext) -> None:
        self._section = section                     # zone_proximity_pts, tp/sl/trap, windows, gate
        self._levels = StrategyLevelState(scheme=ctx.scheme, tick_size=ctx.tick_size)

    def required_bars(self) -> tuple[BarSpec, ...]:
        return (BarSpec(kind="TICK", size=self._section.touch_rule.decision_tf, label="decision"),)

    def decision_bar_label(self) -> str:
        return "decision"

    def on_bar_closed(self, bar: Bar, ctx: PlatformContext) -> StrategyStep:
        if bar.timeframe_ticks != self._section.touch_rule.decision_tf:    # state.py:272-273
            return StrategyStep()                                          # empty delta
        zones = build_zones(ctx.levels_for(bar.trading_day),
                            zone_proximity_pts=self._section.touch_rule.zone_proximity_pts)
        touches = detect_touches((bar,), zones, tick_size=ctx.tick_size,
                                 trading_day=bar.trading_day)              # touch.py:47
        return StrategyStep(setups=tuple(_armed(t) for t in touches),
                            decisions=tuple(_decision(t) for t in touches),
                            features=())            # features computed on observation EXPIRED, §4.5
```

This maps cleanly onto §2: identity (`strategy_id`/`strategy_version`/`SectionModel`), declared data needs (`required_bars` returns a single TICK `BarSpec`, `decision_bar_label()=="decision"`), and consumption (`on_bar_closed -> StrategyStep{setups, decisions, features}`). The `bar.timeframe_ticks != decision_timeframe` continue at CURRENT `state.py:272-273` becomes the plugin's own decision-bar guard, no longer a platform concern.

### 4.3 Typed contract SECTION — `TouchReversalSection` (PROPOSED)

The §2 contract split moves the strategy-specific groups out of today's flat `StrategyContract` (`schema.py:246-278`, 20 fields) into a per-plugin `SectionModel`. CURRENT canonical sub-models that move WHOLESALE into `TouchReversalSection` (each is already its own `_ContractModel` with `extra="forbid"`, so the move is a re-parent, not a rewrite):

- `SessionScheme` — `schema.py:105-110`
- `LevelScheme` — `schema.py:113-118`
- `TouchRule` — `schema.py:121-129` (verified: `type, bar_type, zone_proximity_pts, zone_representative_price, scope, direction_from_side`)
- `FeatureWindows` — `schema.py:132-144` (verified: `interaction_window_minutes, approach_window_minutes, within_band_pts, level_proximity_pts, large_trade_threshold, mid_price_source`)
- `LabelPolicy` — `schema.py:147-167` (verified: includes `decision_offset_minutes: int = Field(gt=0, le=1440)` at `schema.py:161`)
- `InferencePolicy` — `schema.py:170-175` (verified: `eligible_class, eligible_session, confidence_gate`)
- `ResearchSessionExperiment` — `schema.py:187-198` (the optional training-only block)

What STAYS in the platform-owned `StrategyEnvelope` (generic to every plugin): `contract_version`, `platform_version`, `strategy_id`, `strategy_version`, `instrument`/`tick_size`/`point_value`, `model`, `class_map`, `feature_schema_envelope` (the `FeatureSet` partition shape), `data_requirements`, `provenance`. Loader path (PROPOSED): validate envelope -> fail-close `contract_version`/`platform_version` (the same hook as today's `expected_engine_version` at `loader.py:64-70`) -> `plugin = get_strategy(envelope.strategy_id)` -> `section = plugin.SectionModel.model_validate(envelope.section)`. Because each section keeps `extra="forbid"`, the move ALSO retires the three TL local-schema divergences (the `decision_offset_minutes`-missing and `research_session_experiment`-missing breakers) by deleting the hand-written second copy at `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/contracts/strategy_contract.py:160-189` and parsing the section through SC instead.

### 4.4 Declared features (PROPOSED `feature_spec()`)

`feature_spec()` returns exactly the partition the CURRENT `FeatureSet` validator enforces (interaction ∪ approach == names; `schema.py:81-94`):

- 3 INTERACTION (post-touch trade-stream): `int_time_beyond_level` (`features.py:68`), `int_time_within_2pts` (`features.py:103`), `int_absorption_ratio` (`features.py:130`).
- 3 APPROACH (pre-touch aggregates): `app_large_trade_vol_pct` (`features.py:168`), `app_avg_trade_size` (`features.py:194`), `app_max_spread` (`features.py:206`, consumes `Quote`s).

`mid_price_source == "trade_price"` and the band/threshold constants ride in `FeatureWindows` (already moved into the section, §4.3). The QL emitter generates this section FROM `plugin.feature_spec()` / `plugin.label_policy()` rather than restating constants, killing the third-format drift (§2 registry decision).

### 4.5 Label / outcome policy (PROPOSED `label_policy()`)

`label_policy()` declares `barrier_mode = "fixed_points"` and surfaces a §2 `Barrier` whose `stop_price`/`target_price` are the CURRENT fixed thresholds. This is the archetype-1 leg of the BOTH-archetypes test: the barrier abstraction must express today's fixed `tp_points=15.0 / sl_points=30.0 / trap_mfe_min=5.0` (constants.py:139-141) AND archetype-2's R-relative SL=swing/TP=1R. For touch, the barrier is `fixed_points` and the outcome resolution is the EXISTING `resolve_honest_outcome` (production) / `resolve_outcome` (pure), which I verified delegate as cited: `resolve_honest_outcome` computes `decision_ts_utc = touch.bar_ts_utc + timedelta(minutes=decision_offset_minutes)` (`honest_entry.py:127`), drops on flatten/cutoff/no_fill/no_forward (`honest_entry.py:138-161`), then calls `resolve_outcome(entry_points=float(entry_price), direction=touch.direction, forward_bars=forward, ...)` (`honest_entry.py:164-172`). The 3-class MAE-first ladder (`tradeable_reversal` / `trap_reversal` / `aggressive_blowthrough`), adverse-checked-first, is `classify_mae_first` UNCHANGED (`outcomes.py:94-106`). NO R-normalization exists in the touch path and none is introduced — the plugin pins `barrier_mode="fixed_points"`.

### 4.6 Emitted events (PROPOSED `emitted_event_types()`)

The plugin declares its own ws payload schemas; the platform fans them out on the generic `ws.v1` frame (`Envelope` at `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/api/dto.py:214-219`, `MESSAGE_VERSION="ws.v1"`, `extra="forbid"`). The touch plugin's emitted types are exactly today's strategy-meaning deltas (the platform keeps `feed.status`/`market.bar.*`/`levels.updated`/`data_quality.warning` generic):

- `touch.detected` — one per `Touch` from `detect_touches`, carrying the authoritative `Touch.direction` (the CURRENT `_touch_to_trade_lab` carries Core direction rather than re-deriving, `strategy_core_service.py:219-248`).
- `observation.updated` — the post-touch interaction-window observation lifecycle (ARMED setup that EXPIRES when the window elapses; this is the `SetupState{phase}` for archetype 1, single-phase: armed -> expired).
- `prediction.created` / `prediction.resolved` — emitted on the EXPIRED observation, driven by the §2 `DecisionEvent` (the touch is `setup_id`, `decision_ts_utc = touch+offset`, `direction`, `entry_reference`, `barrier`).

Inference stays a SOFT seam (no active model -> `()`, exceptions swallowed) exactly as CURRENT `runtime._run_inference` (`runtime.py:313-346`). Mapping onto §2: `StrategyStep.setups` -> `SetupState` (single-phase here), `StrategyStep.decisions` -> `DecisionEvent` (fixed-points `Barrier`), `StrategyStep.features` computed at observation-EXPIRED time as today.

### 4.7 ACCEPTANCE CRITERION

Every existing parity/golden harness passes UNCHANGED with `TouchReversalStrategy` running as the registered `strategy_id="touch_reversal"` plugin. Named from evidence, the harnesses that MUST stay green byte-for-byte:

PLATFORM-side (candle/level/runtime parity — unaffected by the plugin split because the candle fold and level fold remain platform):
- `C:/Users/gonza/Documents/Strategy-Core/tests/test_candle_parity.py` (batch == streaming candles).
- `C:/Users/gonza/Documents/Strategy-Core/validation/parity_harness.py`, `parity_harness_v2.py`, `test_production_pair_parity.py`, `test_duckdb_streaming_parity.py`, `phase4b_validate.py`, `phase4d_liveorder.py`.
- `C:/Users/gonza/Documents/Strategy-Core/tests/test_sessions.py`, `tests/test_zones.py`.

PER-PLUGIN decision/feature/label parity (these now exercise the plugin's `on_bar_closed` + `feature_spec`/`label_policy`, but must produce identical bytes):
- `C:/Users/gonza/Documents/Strategy-Core/tests/test_touch.py`, `tests/test_outcomes.py`, `tests/test_features.py`, `tests/test_honest_entry.py`.
- `C:/Users/gonza/Documents/Strategy-Core/validation/decision_diff_harness.py`, `validation/test_decision_diff.py`.
- `C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_decision_repoint_parity.py` (book-mid mode: 6 features "max abs diff must be 0").
- `C:/Users/gonza/Documents/Claude-Quant-Lab/scripts/phase8_1_golden.py` (`--mode compare` byte-equality of golden.json vs engine.json).

RUNTIME state-machine + cross-runtime acceptance (the plugin must reproduce the inline `state.py:271-280` behavior exactly):
- `C:/Users/gonza/Documents/Strategy-Core/tests/test_runtime_state.py`, `tests/test_runtime_touches.py`, `tests/test_runtime_touch_zones.py`, `tests/test_runtime_levels.py`.
- `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_strategy_core_acceptance.py` — verified: it runs a direct `StrategyRuntime(timeframes=(2,), decision_timeframe=2)` against TL's `ApplicationRuntime(tick_timeframes=(2,))` over the same 4 trades (`test_strategy_core_acceptance.py:30-57`) and asserts the touch output matches. With the plugin in place, BOTH sides run `TouchReversalStrategy`, so this cross-runtime equality is the single sharpest acceptance gate.

CONTRACT round-trip (after the envelope/section split):
- `C:/Users/gonza/Documents/Strategy-Core/tests/test_contract.py`.
- `C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_strategy_contract_nodrift.py`, `test_strategy_contract_repoint.py` (every structural leaf == its `strategy_core.constants` value; emitted contract re-loads fail-closed).
- `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_engine_version_binding.py` (re-expressed as `platform_version` + per-plugin `strategy_version` binding).

The criterion is strictly: with `touch_reversal` registered and `decision_timeframe` pinned to the smallest configured tick timeframe (as TL does today, `strategy_core_service.py:99-111`), the above harnesses produce identical bytes/labels/features to the pre-split runtime. If any diverges, the retrofit is wrong — the plugin must be call-site-only.

### 4.8 Why this is the proof (maps onto §2)

Archetype 1 stresses the §2 interface on its EASY axis and passes with zero kernel change: `required_bars()` = a single TICK `BarSpec` (no new platform capability needed — the TICK-only engine at `streaming.py:180-181` already produces it); `SetupState` is single-phase (armed -> expired); the `Barrier` is `fixed_points` reusing `resolve_outcome`; the six features are the CURRENT `features.py:58-65`; the inference gate is the CURRENT NY-session `InferencePolicy`. The same `StrategyPlugin` protocol must ALSO carry archetype 2 (multi-stage, 8 TIME `BarSpec`s, r_relative `Barrier`) per §2 — which is the redesign test the protocol already satisfies. Touch is the regression anchor: it proves the new seam is byte-for-byte faithful before any new strategy or the one genuinely-new platform capability (the `BarSpec` TIME-bar close trigger) is built.

---

## 5. "How to add strategy N" golden path

This section is the platform's litmus test. Under the §2 design (the thin-waist PLATFORM / `StrategyPlugin` protocol / registry / `StrategyEnvelope` + typed `SectionModel` / split versioning), a future strategy author adds a whole new strategy by touching **only files they own**: one plugin module, one registration line in their own module's import side-effect, one `SectionModel`, and one parity test stamped from a shared template. They edit **zero platform code and zero other strategies**. The worked example below is **Archetype 2** — the multi-stage HTF-FVG → parent-context → 1m-retest-lock → opposing-inversion strategy from `C:/Users/gonza/Documents/Trade-Lab/docs/ifvg-strat.md` — chosen precisely because it is the hardest case (multi-stage state, multi/mixed timeframes incl. TIME bars, R-relative barriers). If the golden path holds for it, it holds for anything.

Everything labeled CURRENT is quoted verbatim from live source with `file:line`. Everything else is PROPOSED (the §2 target design).

---

### 5.0 What "zero platform edits" means, and why it holds

The author writes one new package, e.g. `strategy_core/strategies/ifvg/` (PROPOSED), containing: `plugin.py` (the `StrategyPlugin` impl + `@register`), `section.py` (the typed `SectionModel`), `features.py` (optional strategy-specific feature fns), and `tests/test_ifvg_parity.py`. They add **nothing** to `runtime/state.py`, `candles/streaming.py`, `contract/loader.py`, `api/dto.py`, `services/model_registry.py`, or any sibling strategy package.

The property holds because of four structural facts established in §2, each replacing a hardwired decision with a lookup or a declaration:

1. **The event loop calls plugin hooks, not hardwired strategy code.** Today the loop has the touch/zone/level pipeline baked directly into `_process_trade` — CURRENT, `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/runtime/state.py:271-280`:
   ```python
           for bar in candle_update.completed:
               if bar.timeframe_ticks != self.decision_timeframe:
                   continue
               zones = self._zones_for_detection(bar.trading_day)
               detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
               for touch in detected:
                   self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))
               touches.extend(detected)
   ```
   PROPOSED: this block is replaced **once, by the platform team** with `step = self._plugin.on_bar_closed(bar, self._ctx)` over the plugin's *declared* decision bars. After that one-time edit, the loop never names a strategy again. Adding strategy N rides the existing call — no loop edit.

2. **Bar needs are declared, not configured.** The plugin's `required_bars() -> tuple[BarSpec, ...]` (PROPOSED) is what the platform feeds to `CandleEngine`. Archetype 2 declares TIME bars; the platform's new `BarSpec{kind: TICK|TIME, size, label}` + `CloseReason.INTERVAL` trigger (the ONE genuinely new platform capability from §2) services them. Crucially this is built **once** by the platform; strategy N just *names* the bars it wants. It does not extend the candle engine.

3. **The registry turns `strategy_id` into a router.** Today `strategy_id` is opaque — CURRENT, `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/model_registry.py:148` sets `ModelBundle.strategy_id = contract.strategy_id`, and §2/§3 confirm there is "NO `strategy_id`-driven dispatch." PROPOSED: `@register("ifvg_smc")` in the author's `plugin.py` adds the class to `strategy_core/strategies/registry.py`'s table at import time, and `activate` resolves it. The author edits the registry **by importing their module**, not by editing the registry file.

4. **The contract section is the plugin's own typed model.** The loader validates the platform `StrategyEnvelope`, then does `section = plugin.SectionModel.model_validate(envelope.section)` (PROPOSED). The author's `SectionModel` is `extra="forbid"` and lives in their package. No edit to the canonical schema — which is exactly what kills the three TL divergences documented in the contract evidence (the TL local copy rejects `decision_offset_minutes` and `research_session_experiment` under `extra="forbid"`).

The litmus: search the diff for strategy N. Every changed line is under `strategy_core/strategies/ifvg/`. The only platform files even *read* are the protocol and the `BarSpec`/`PlatformContext` definitions — imported, never edited.

---

### 5.1 Step 1 — Implement the `StrategyPlugin` interface

Author writes `strategy_core/strategies/ifvg/plugin.py` (PROPOSED). The plugin implements the §2 `runtime_checkable` `StrategyPlugin` protocol. For Archetype 2 the load-bearing methods are:

- **Identity:** `strategy_id = "ifvg_smc"`, `strategy_version = "ifvg_v4.1"` (matching the doc's "v4.1 tuned defaults", `ifvg-strat.md:311`), `SectionModel = IFVGSection` (§5.3).
- **Declared data needs — `required_bars()`:** returns TIME `BarSpec`s for every timeframe the doc names: 1m execution, parents 3m/5m/10m/15m/30m, and HTF 1H/4H (`ifvg-strat.md:135-152`) — eight specs. `decision_bar_label()` returns `"1m"` (the doc mandates 1-minute execution and forbids decisions on other charts, `ifvg-strat.md:130-131`, Do-Not-Break rule 1 at `:1389`).
  > This is the exact stress point on the platform. CURRENT, the engine is TICK-ONLY: a bar closes on a trade *count*, never elapsed time — `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/candles/streaming.py:180-181`:
  > ```python
  >             if candle.trade_count == timeframe:
  >                 completed.append(candle.freeze(complete=True, reason=CloseReason.COMPLETE))
  > ```
  > and `CloseReason` has exactly two members (CURRENT, `types.py:51-55`: `COMPLETE`, `END_OF_DAY`). The author does NOT add TIME bars — that platform capability (`BarSpec` + `CloseReason.INTERVAL`) is built once per §2. The author merely *declares* `BarSpec(kind="TIME", size="1m", label="1m")` etc. and consumes the closed bars the platform hands back.
- **Lifecycle:** `configure(section: IFVGSection, ctx: PlatformContext)` stores tuned defaults (min FVG 8 ticks, parent window 24 bars, proximities 80 ticks, post-inversion expiry 30 bars — `ifvg-strat.md:327-340`). `reset()` clears all setup state (Do-Not-Break rule 2: one setup at a time, `:1390`).
- **Consumption — `on_bar_closed(bar, ctx) -> StrategyStep`:** the multi-stage state machine. It maintains a `SetupState{setup_id, phase, direction, status, evidence}` (PROPOSED) whose `phase` walks the doc's lifecycle: `scanning → htf_tapped → parent_locked → inverted → armed → invalidated/expired` (`ifvg-strat.md:601-611`, §9 State-Machine Summary). `evidence` carries the audit chain the doc *requires* — which HTF FVG, which parent TF, lock point, opposing gap, inversion bar, final entry gap (`ifvg-strat.md:751-789`, §12 Trade Audit). Each closed bar may: arm a setup, advance/lock a parent, register an inversion, invalidate (parent full-fill/structural break, `:454-465`), or emit a `DecisionEvent`. This is exactly the arming/locking/invalidation the §2 `SetupState` was designed to express.
  > Archetype 1 collapses to a degenerate `SetupState` (single phase: touch → decide), so the *same* `on_bar_closed` signature serves both — the interface is not over-fit to either.
- **Barrier — R-relative:** the plugin returns a `DecisionEvent{..., barrier}` whose `Barrier` is the §2 `r_relative` variant (PROPOSED). Per the doc, `stop_price(entry, dir)` = the manipulation swing (lowest 1m low / highest 1m high from parent retest through entry ± 1-tick buffer, `ifvg-strat.md:293-305, 647-655`); `target_price(entry, dir)` = entry ± 1R, where 1R = |entry − stop| (`ifvg-strat.md:348, 683-687`). Contrast Archetype 1's CURRENT fixed-point barriers, which the `fixed_points` `Barrier` variant wraps — verbatim, `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/decisions/outcomes.py:127-136`:
  > ```python
  > def resolve_outcome(
  >     entry_points: float,
  >     direction: Direction,
  >     forward_bars: Sequence[Bar],
  >     tick_size: float,
  >     *,
  >     tp_points: float,
  >     sl_points: float,
  >     trap_mfe_min: float,
  > ) -> OutcomeResult:
  > ```
  > The R-relative plugin does NOT fork the labeler. It derives per-setup `tp_points`/`sl_points` from R (`sl_points = |entry − swing|`, `tp_points = 1 * sl_points`) and reuses the *shared* MAE-first kernel unchanged — CURRENT, `outcomes.py:63-71`:
  > ```python
  > def classify_mae_first(
  >     max_mfe: float,
  >     max_mae: float,
  >     *,
  >     tp_points: float,
  >     sl_points: float,
  >     trap_mfe_min: float,
  >     forced: bool = False,
  > ) -> str | None:
  > ```
  > So "R-relative" is a per-setup barrier-to-points projection feeding the same `classify_mae_first`/`resolve_outcome` money path — no platform labeler edit.

---

### 5.2 Step 2 — Register the plugin

In the same `plugin.py`, the author decorates the class (PROPOSED):
```python
@register("ifvg_smc")
class IFVGPlugin:
    ...
```
`@register` (in `strategy_core/strategies/registry.py`, PROPOSED) adds the class to a module-level table keyed by `strategy_id`; `get_strategy(strategy_id)` looks it up. §2 explicitly RECOMMENDS this greppable, single-sourced-inside-SC registry over Python entry-points, "so both the SHA-pinned TL and the unpinned-floating QL see it identically" — which directly addresses the asymmetric-binding risk in the evidence (TL pins `strategy-core` by SHA at `backend/pyproject.toml:19`; QL's `strategy_core` import is undeclared/unpinned).

Registration is the *only* "wiring" step, and it is a decorator in the author's own file — not an edit to a central registry list, not a config map elsewhere. Importing the package (which the registry's package `__init__` does) is what populates the table. **Zero platform edits.**

The payoff downstream: PROPOSED, `model_registry.activate` gains `plugin_cls = get_strategy(contract.strategy_id)`, promoting `strategy_id` from label to fail-closed router. The activation seam it slots into is already fail-closed and atomic — CURRENT, `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/model_registry.py:238-255`:
```python
    def activate(self, model_id: str) -> ActiveModel:
        ...
        if not is_safe_model_id(model_id):
            raise ModelNotFoundError("unknown model id")
        directory = self._resolve_bundle_dir(model_id)
        contract = self._load_contract(directory)
        model = self._load_and_validate_model(directory, contract)
        active = ActiveModel(model_id=model_id, model=model, contract=contract)
        with self._lock:
            self._active = active
        return active
```
An unknown `strategy_id` makes `get_strategy` raise, the prior active model is untouched (the swap only happens after full validation), so registering a *new* strategy cannot destabilize the existing one.

---

### 5.3 Step 3 — Contribute the contract section (typed `SectionModel`)

The author writes `strategy_core/strategies/ifvg/section.py` (PROPOSED) — an `extra="forbid"` Pydantic model `IFVGSection` holding only Archetype-2 fields: timeframe toggles (1H/4H, 3m–30m), `min_fvg_ticks`, `parent_reaction_window_bars`, `parent_priority`, the proximity thresholds, `post_inversion_max_bars`, the SL model + buffer, TP multiple (R), BE trigger mode, and the enabled NY sessions (all enumerated in `ifvg-strat.md:309-368`). The platform `StrategyEnvelope` carries the strategy-neutral fields (`contract_version`, `platform_version`, `strategy_id`, `strategy_version`, `instrument`/`tick_size`/`point_value`, `model`, `class_map`, `data_requirements`, `provenance`, and `section: dict`).

The loader (PROPOSED, extended from CURRENT `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/contract/loader.py:28-77`) validates the envelope, fail-closes `contract_version`/`platform_version`, resolves `plugin = get_strategy(envelope.strategy_id)`, then does `section = plugin.SectionModel.model_validate(envelope.section)`. The CURRENT version-binding hook it generalizes — verbatim, `loader.py:62-70`:
```python
    if expected_engine_version is not None:
        declared_engine = payload.get("engine_version")
        if declared_engine != expected_engine_version:
            raise ContractError(
                f"unsupported engine_version {declared_engine!r}; "
                f"expected {expected_engine_version!r}"
            )
```
PROPOSED, this becomes a `platform_version` check (pinned once by both consumers) plus a registry-equality `strategy_version` check, replacing the single global `ENGINE_VERSION = "strategy_core_engine_v3"` (CURRENT, `strategy_core/__init__.py:54`). Because Archetype 2's section is its *own* model, it never collides with Archetype 1's `TouchReversalSection` — and the author never touches the canonical `StrategyContract` (CURRENT, `schema.py:246-278`). This is the structural fix for the three TL contract divergences: there is no second hand-written schema to drift, so a section field the author adds cannot break a sibling strategy's parse.

---

### 5.4 Step 4 — Contribute features + label policy + emitted events

- **`feature_spec()`** (PROPOSED): Archetype 2 declares its own feature names (e.g. parent-TF rank, HTF-distance ticks, manipulation-swing depth, bars-to-inversion). The platform's QL emitter generates the contract's `feature_set` *from* `feature_spec()` (per §2: "QL emitter generates the contract FROM the plugin … killing the third-format drift"), so the author defines feature names once and they flow to the bundle automatically. Strategy-specific feature *functions* live in the author's `features.py`; the six current engine features (CURRENT, `decisions/features.py` `__all__` at `:58-65`) are Archetype-1-owned and are NOT inherited unless reused.
- **`label_policy()`** (PROPOSED): declares `barrier_mode="r_relative"` (vs Archetype 1's `fixed_points`). The 3-class MAE-first ladder, `classify_mae_first`, is shared kernel — Archetype 2 reuses it via the per-setup R→points projection from §5.1; it does not redefine labels.
- **`emitted_event_types()`** (PROPOSED): declares the typed ws payload schemas this strategy emits. This matters because the ws transport is version-frozen — CURRENT, `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/api/dto.py:24` `MESSAGE_VERSION = "ws.v1"` with the `Envelope` (`:214-219`) and `ApiModel` `extra="forbid"` (`:42`). Per §2, strategy deltas ride a **generic** frame whose `payload` is the plugin's own typed event — so Archetype 2's rich audit events (active HTF zone, locked parent, opposing gap, inversion marker, setup phase — exactly the audit surface the doc demands at `ifvg-strat.md:774-793`) serialize through the existing envelope without adding a new top-level `MessageType` literal. The author registers schemas; they do **not** edit the frozen `MessageType` enum. Zero transport edits.

---

### 5.5 Step 5 — Stamp a parity test from the shared template

§2 splits the parity-harness into a **framework**: candle/level parity stays platform (already locked — CURRENT `tests/test_candle_parity.py`, `validation/test_duckdb_streaming_parity.py`), while **decision/feature/label parity becomes per-plugin**. The author copies the shared template into `strategy_core/strategies/ifvg/tests/test_ifvg_parity.py` (PROPOSED) and fills in the strategy-specific golden: a fixed bar/trade stream → expected `SetupState` phase transitions, expected `DecisionEvent` barrier levels (manipulation-swing SL, 1R TP), expected R-relative-projected labels. This mirrors how Archetype 1 is pinned today — e.g. the byte-exact decision parity in `C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_decision_repoint_parity.py` ("6 features max abs diff must be 0") and the golden capture pattern in `C:/Users/gonza/Documents/Claude-Quant-Lab/scripts/phase8_1_golden.py` (`--mode compare` byte-compares golden vs engine).

The template is owned by the platform; the *stamp* (fixtures + expected values) is owned by the author. The author's test cannot regress Archetype 1 because it imports only the `ifvg` plugin. Conversely, the platform's standing candle/level parity tests guard the one shared surface Archetype 2 leans on (the new TIME `BarSpec`), so a TIME-bar bug surfaces in the platform suite, not silently in strategy N.

---

### 5.6 Litmus result — the diff for adding Archetype 2

| Touched (author-owned, under `strategy_core/strategies/ifvg/`) | NOT touched (platform / other strategies) |
|---|---|
| `plugin.py` — `IFVGPlugin` + `@register("ifvg_smc")` (steps 1–2) | `runtime/state.py` event loop (`:262-290`) — calls `on_bar_closed`, never named |
| `section.py` — `IFVGSection` `extra="forbid"` (step 3) | `contract/schema.py` `StrategyContract` (`:246-278`) — envelope only |
| `features.py` — strategy features (step 4) | `candles/streaming.py` — TIME-bar capability built once, then declared |
| `tests/test_ifvg_parity.py` — stamped template (step 5) | `services/model_registry.py` `activate` (`:238-255`) — generic router |
| (registration via decorator import) | `api/dto.py` `ws.v1` `MessageType` (`:24-38`) — generic frame |
|  | the existing `touch_reversal` plugin — separate package, untouched |

Both archetypes pass the *same* interface (§2 ARCHETYPE VALIDATION): Archetype 1 = single TICK `BarSpec`, degenerate single-phase `SetupState`, `fixed_points` `Barrier` over `resolve_outcome`, six current features, NY `InferencePolicy`; Archetype 2 = eight TIME `BarSpec`s, full multi-phase `SetupState`, `r_relative` `Barrier` (SL=manipulation swing, TP=1R) reusing `classify_mae_first`. The interface required **no redesign** to admit the harder archetype; the only net-new platform capability is the `BarSpec`/TIME-bar close trigger, which the author *declares* but does not *build*. That is the proof the platform is genuinely pluggable.

---

## 6. Cross-repo impact + dependency/version topology

This section specifies, for all three repos, the target package layout (platform package + strategy-plugin packages + per-repo consumption), what each repo consumes, and the dependency wiring that keeps the three version-aligned *by construction* — i.e. the strategy.json/candle/session/level *format* lives in exactly one place, so there is nothing left to copy and therefore nothing that can drift.

PROPOSED items are labelled. CURRENT facts are quoted/cited from live source.

---

### 6.1 The drift surface today (CURRENT — what we must collapse)

Three repos, three resolution stories. The single-source machinery already exists for the contract format but is only half-adopted, and the candle/session/level format is still copied:

- **Strategy-Core (SC)** is the package. It is the canonical home of the format: version stamps single-sourced in `src/strategy_core/__init__.py:54,57`:
  ```python
  ENGINE_VERSION = "strategy_core_engine_v3"   # __init__.py:54
  CONTRACT_VERSION = "trade_lab_contract_v1"   # __init__.py:57
  ```
  The contract schema + fail-closed loader live in the importable subpackage `src/strategy_core/contract/` (`__init__.py`, `loader.py`, `schema.py`, confirmed present), whose own docstring states the intent verbatim (`contract/__init__.py:1-5`): *"The strategy.json contract: one Pydantic schema + a strict fail-closed loader. Previously duplicated (research had the emitter dict, Trade-Lab had the loader). Now a single definition both repos import, so the contract format cannot drift."* SC declares only leaf libs (`numpy`, `pydantic`, `pyarrow`, `tzdata`; `pyproject.toml:13-18`) — it depends on neither consumer, so it is a clean platform root.

- **Trade-Lab (TL)** pins SC by exact SHA — this is the one binding done right today (`backend/pyproject.toml:19`):
  ```toml
  "strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@fd53e06989084368aa3b89d33eb83bee081b695f",
  ```
  with `allow-direct-references = true` (`backend/pyproject.toml:31`). But TL still carries THREE local copies of formats SC already owns:
  1. **Contract format copy** — `backend/src/trade_lab/domain/contracts/strategy_contract.py` (schema + loader in one file), re-exported via `domain/contracts/__init__.py:8-23`. TL imports `import strategy_core` (line 17) only to read `strategy_core.ENGINE_VERSION` at bind time (lines 232,236,241); it restates `CONTRACT_VERSION = "trade_lab_contract_v1"` locally rather than importing it. This copy has the three known divergences from canonical SC (`engine_version` optional vs required; `LabelPolicy` missing `decision_offset_minutes`; no `research_session_experiment`) and under `extra="forbid"` it **cannot parse a current v3 QL-emitted contract**. The model registry consumes the LOCAL copy, not SC: `model_registry.py:26` `from trade_lab.domain.contracts import ContractError, StrategyContract, load_strategy_contract`.
  2. **Candle/session/level format copies** — `domain/candles.py` (`CandleEngine` at `:103`, `Candle`/`CandleCloseReason` DTOs), `domain/sessions.py` (`SessionClassifier` at `:55`, `SessionName`, `classify_session` at `:35`), `domain/levels.py` (`SessionLevelEngine` at `:118`, `LevelKind`, `DisplayLevel`, `TouchEvent`). These are full legacy reimplementations, and `sessions.py` is on the **divergent Chicago (CT) calendar** — `CT = ZoneInfo("America/Chicago")` (`sessions.py:8`) with end-exclusive wall-clock boundaries (`sessions.py:35-40`) — NOT SC's canonical ET v3 scheme. The streaming hot path now flows through `strategy_core_service.py` (which uses the real SC engine), so these modules survive mostly as **DTO type definitions** consumed by the service/DTO/runtime/inference layers (`strategy_core_service.py:29,33,35`; `api/dto.py:13,16`; `runtime.py:16,27`; `inference/outcome_tracker.py:28`; `observations.py:12-13`).
  3. **A fourth, independent candle duplication in `services/seed.py`** — its own `build_tick_bars_from_frame` (`seed.py:42`) re-implements SC's vectorized batch builder but on CT boundaries (`seed.py:24` `from trade_lab.domain.sessions import CT, classify_session, to_ct`; the comment `seed.py:35-38` pins "Chicago seconds-of-day session boundaries (must match domain.sessions.classify_session)"). This is the seam most likely to drift silently against the engine's ET v3 tick bars.

- **Quant-Lab (QL)** is the asymmetric-binding risk. It imports the engine directly — `engine_decision.py:45-70` (`import strategy_core as sc`, `from strategy_core import ...`, `from strategy_core.constants import ...`) — and the emitter + tests import the SC contract package directly (`tests/agents/test_strategy_contract_nodrift.py:27-28`, `tests/agents/test_strategy_contract_repoint.py:19`, `scripts/run_databento_acceptance.py:151`). **Yet `strategy-core` is NOT a declared dependency anywhere**: `Claude-Quant-Lab/pyproject.toml:12-36` (runtime) and `:38-48` (dev) list pandas/numpy/scipy/pydantic/catboost/fastapi/etc. with **no `strategy-core` and no git URL** (a `Grep` for `strategy.core`/`strategy_core` across QL `*.toml` returns **No matches**). QL resolves `strategy_core` only via an external editable / `PYTHONPATH=src`-style install — unpinned and undeclared. So QL can silently float to a different SC commit than the one TL pins to (`fd53e06…`). This is the structural hole: TL is pinned, QL floats, and the two are supposed to be byte-aligned on the engine + contract.

Net: the contract format is single-sourced in SC and consumed correctly by QL but copied (and diverged) by TL; the candle/session/level format is copied (and diverged onto CT) by TL in two places; and QL's binding to the single source is undeclared. Drift is currently prevented only by *tests* (the parity/no-drift harnesses), not by *construction*.

---

### 6.2 PROPOSED target layout — three package tiers, one format home each

PROPOSED. The split introduces a clean three-tier package topology inside SC, plus a fixed consumption shape per repo. (This builds on the PROPOSED design summary's PROTOCOL/CONTRACT/VERSION/REGISTRY split — it does not invent a different interface.)

**Tier 1 — PLATFORM package (`strategy_core`, the thin waist).** Owns the 6 generic concerns: data ingest (`Trade`/`Quote`/`DataQualityWarning` + sources), the event-sourced loop (`StrategyRuntime.process_event` dispatch kept verbatim, `state.py:229-236`; the hardwired touch block `state.py:271-280` becomes a plugin-hook call), candle aggregation extended from TICK-ONLY to the new `BarSpec {TICK|TIME}` + `CloseReason.INTERVAL` (the one genuinely new platform capability), the contract **envelope** + fail-closed loader (`contract/loader.py:28-77` extended) + version binding, the `RuntimeUpdate→ws.v1` transport framing, and the parity-harness FRAMEWORK (candle/level parity stays platform). It also hosts the **registry** (PROPOSED `strategy_core/strategies/registry.py` with `@register` + `get_strategy(strategy_id)`) so both the SHA-pinned TL and the (now-declared) QL see the same single-sourced router.

**Tier 2 — STRATEGY-PLUGIN packages (live inside SC, e.g. `strategy_core/strategies/touch_reversal/`).** Each plugin owns its typed `SectionModel` (archetype 1 = `TouchReversalSection {session_scheme, level_scheme, touch_rule, feature_windows, label_policy, inference, research_session_experiment}`), its `feature_spec()`/`label_policy()`/`Barrier`, and its decision/feature/label parity tests. Co-locating plugins in SC (vs a separate distribution) is what lets the SHA pin / commit pin cover platform + every plugin in one bump, so consumers cannot mix a platform version with a stale plugin.

**Tier 3 — PER-REPO CONSUMPTION (unchanged repo identities, thinner):**
- **TL** consumes `strategy_core` (platform) for the runtime loop + transport framing, and `strategy_core.contract` for the loader/schema, and `strategy_core.strategies.registry.get_strategy(...)` to turn `strategy_id` into a fail-closed router inside `model_registry.activate` (`model_registry.py:238-255`, today `strategy_id` is an opaque label at `:148`). TL writes NO format.
- **QL** consumes `strategy_core` (engine functions, already does — `engine_decision.py:45-70`) and `strategy_core.strategies.*` to generate the contract FROM the plugin (`feature_spec`/`label_policy`/`SectionModel`) instead of re-assembling a dict by hand in `agents/data_infra/ml/strategy_contract.py`. QL writes NO format — it serializes the plugin's own declarations.

---

### 6.3 What each repo CONSUMES after the split (PROPOSED)

| Repo | Consumes from platform `strategy_core` | Consumes from plugin tier | Local format it KEEPS |
|---|---|---|---|
| **SC** | (is the platform) | (hosts the plugins) | — (the format lives here, once) |
| **TL** | runtime loop (`StrategyRuntime`), `BarSpec`/`CloseReason`, `RuntimeUpdate`/`FeedStatus` DTOs + serializers, `contract.loader.load_strategy_contract` (+ `expected_*_version` hook), `ENGINE_VERSION`→`platform_version`, `CONTRACT_VERSION` (imported, not restated) | `registry.get_strategy(strategy_id)` in `model_registry.activate`; the plugin's `SectionModel` for typed-section validation | NONE of the format. Keeps only: the FastAPI/WS app, `model_registry` selection/activation/checksum machinery, the `ws.v1` envelope wiring, and TL-specific DTO field *names* it maps engine deltas onto (the adapter, `strategy_core_service.py`). The `outcome_tracker` level-price divergence is retired in favor of the engine's honest `trade_price_at`. |
| **QL** | engine functions (already: `build_zones`/`detect_touches`/`resolve_honest_outcome`/the 6 features), `strategy_core.constants`, `contract.schema`/`contract.loader` | the plugin's `feature_spec()`/`label_policy()`/`SectionModel` to BUILD the emitted contract | NONE of the format. Keeps only the per-run *scalars* (`config.*`, `du.*`) it injects into the plugin-generated envelope. |

---

### 6.4 The dependency wiring that makes alignment STRUCTURAL (PROPOSED)

Three changes, each removing a copy or declaring a pin:

**(a) Collapse TL's local contract copy onto the platform contract.** Delete `backend/src/trade_lab/domain/contracts/strategy_contract.py` and repoint `domain/contracts/__init__.py` (today `:8-23` imports from the local file) to re-export from `strategy_core.contract`:
- PROPOSED `from strategy_core.contract.schema import StrategyContract, ContractError, ...` and `from strategy_core.contract.loader import load_strategy_contract`, plus `from strategy_core import CONTRACT_VERSION` (instead of the local restatement at `strategy_contract.py:20`).
- `model_registry.py:26` then imports the SAME `StrategyContract`/`load_strategy_contract`/`ContractError` SC ships. This *automatically* erases all three TL divergences (`engine_version` becomes required, `decision_offset_minutes` is accepted, `research_session_experiment` is accepted) because there is no second schema to diverge — and it makes the canonical loader's `expected_engine_version` hook (`loader.py:28-77`) the single binding path, replacing TL's optional-`engine_version` + warn-unbound behavior. Note the format actually splits at this point into platform `StrategyEnvelope` + plugin `SectionModel` (PROPOSED §2 contract split), but the key wiring fact is identical: TL imports both from SC, writes neither.

**(b) Retire TL's local candles/sessions/levels (and the `seed.py` candle copy).** Replace the DTO/type uses of `domain/candles.py`/`domain/sessions.py`/`domain/levels.py` with the platform `strategy_core` types (`Bar`, `Level`, `Touch`, `SessionInfo`, `CloseReason`, etc.) — the same types `strategy_core_service.py` already maps TO. Concretely:
- the consumers at `api/dto.py:13,16`, `runtime.py:16,27`, `inference/outcome_tracker.py:28`, `observations.py:12-13`, and `strategy_core_service.py:29,33,35` switch to SC types (the service's `_bar_to_trade_lab`/`_level_to_trade_lab`/`_touch_to_trade_lab` adapters at `:275-322` become the only place TL field-renames remain, if any);
- `seed.py`'s private `build_tick_bars_from_frame` (`seed.py:42`) is replaced by SC's canonical `strategy_core.build_tick_bars_from_frame` (`__init__.py:60`), which deletes the CT-boundary seam (`seed.py:24,35-38,77-78`) — the seed path then warms the chart with the SAME ET v3 tick bars the live engine produces.
- This removes the divergent Chicago calendar entirely; the ET v3 `SessionScheme` becomes the only session definition in TL's process.

**(c) Declare + pin the platform in QL the same way TL does.** QL's binding is undeclared today (`Claude-Quant-Lab/pyproject.toml` has no `strategy-core`; confirmed by Grep). PROPOSED: add to `Claude-Quant-Lab/pyproject.toml` runtime `dependencies` (alongside `:12-36`) the identical git-pin shape TL uses (`backend/pyproject.toml:19`), e.g. `"strategy-core @ git+https://github.com/thealgochef/Strategy-Core.git@<SHA>"`, with `allow-direct-references`-equivalent enabled for its build backend. This converts QL from "floats to whatever `PYTHONPATH=src` happens to expose" into "pinned to an explicit SC commit," so QL and TL can be held to the **same** SHA at release.

**Editable/local install for active dev, pinned commit for releases.** PROPOSED operational rule that follows from (a)–(c):
- **Active development:** both consumers install SC editable/local (`pip install -e ../Strategy-Core` or a path/workspace reference) so a format change is exercised against both repos before it is cut. This is the natural extension of QL's current `PYTHONPATH=src` habit, made explicit.
- **Releases:** both consumers pin the **same** SC commit SHA (TL already does; QL gains the pin in (c)). A platform/plugin change is a SC commit; aligning the two consumers is a single SHA bump applied identically to `backend/pyproject.toml:19` and the new QL dependency line. Mismatched SHAs are then visible in two `pyproject.toml` diffs rather than hidden behind an undeclared import.

---

### 6.5 Why no-drift becomes STRUCTURAL, not test-enforced (PROPOSED)

Today drift is held back by *tests* — QL's `test_strategy_contract_nodrift.py` (every structural field == its `strategy_core.constants` value, every contract leaf enumerated), the SC↔TL `test_engine_version_binding.py`, the candle parity suite, the Phase-8.1 golden capture. Those remain valuable, but after the split they guard a system where the format **only exists once**:

- **The contract format lives once** — in `strategy_core.contract` (envelope) + each plugin's `SectionModel`. TL imports it (change (a)); QL generates from the same plugin declarations + `strategy_core.constants` (the emitter at QL `strategy_contract.py` already single-sources structural fields from `k.*`). There is no second hand-written schema to fall behind, so the three TL divergences cannot recur — they were *only* possible because a second schema existed.
- **The candle/session/level format lives once** — in `strategy_core` (`CandleEngine`/`build_tick_bars_from_frame`/`classify_session`/`StrategyLevelState`). TL deletes its copies (change (b)), including the CT seed seam, so the ET v3 sessions + tick-bar definition cannot diverge across the two TL paths or across repos.
- **The version stamps live once** — `platform_version` (replacing the global `ENGINE_VERSION = "strategy_core_engine_v3"`, `__init__.py:54`) plus per-plugin `strategy_version`/`strategy_id`, all defined in SC and fail-closed in the shared loader. Both consumers import them; neither restates them (eliminating TL's local `CONTRACT_VERSION` restatement at `strategy_contract.py:20`). Retuning the touch barriers bumps only `touch_reversal`'s `strategy_version`; the platform pin and other bundles stay valid — removing today's any-change-bumps-the-whole-engine-and-resyncs-both-consumers coupling.
- **The pin is symmetric** — both `pyproject.toml`s reference the same SC commit (change (c)). Alignment is enforced at install/resolve time by the package manager, not by a green test run.

The result: there is nothing left to copy. The format (contract, candles, sessions, levels, versions) is defined exactly once in SC, both consumers import or generate from that one definition, and both pin the same commit. Version alignment is a property of the dependency graph — a single SHA shared by two `pyproject.toml` files — rather than a property that a parity test happens to still pass.

---

### 6.6 Files cited (all absolute)

- `C:/Users/gonza/Documents/Strategy-Core/pyproject.toml` (`:13-18` deps)
- `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/__init__.py` (`:54,57` version stamps; `:60` `build_tick_bars_from_frame`; `:67-68` contract re-exports)
- `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/contract/__init__.py` (`:1-5` "cannot drift" docstring)
- `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/contract/loader.py` (`:28-77` loader + `expected_engine_version` hook)
- `C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/contract/schema.py` (canonical schema)
- `C:/Users/gonza/Documents/Trade-Lab/backend/pyproject.toml` (`:19` SHA pin; `:31` allow-direct-references)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/contracts/__init__.py` (`:8-23` local re-export)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/contracts/strategy_contract.py` (`:17,20,232,236,241` local copy + SC import for ENGINE_VERSION only)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/candles.py` (`:103` `CandleEngine`)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/sessions.py` (`:8` CT zone; `:35,55` `classify_session`/`SessionClassifier`)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/levels.py` (`:118` `SessionLevelEngine`)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/seed.py` (`:22,24,35-38,42,77-78` local CT candle builder)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/model_registry.py` (`:26` local-contract import; `:148` opaque `strategy_id`; `:238-255` activate)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/strategy_core_service.py` (`:29,33,35` domain-type imports)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/api/dto.py` (`:13,16` domain-type imports)
- `C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/runtime.py` (`:16,27` domain-type imports)
- `C:/Users/gonza/Documents/Claude-Quant-Lab/pyproject.toml` (`:12-36,38-48` — NO `strategy-core`)
- `C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/engine_decision.py` (`:45-70` direct SC import)
- `C:/Users/gonza/Documents/Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/strategy_contract.py` (the emitter, single-sources from `k.*`)
- `C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_strategy_contract_nodrift.py` (`:27-28` direct `strategy_core.contract` import)

---

## 7. Incremental migration sequence (strangler-fig)

This is an ORDERED sequence of small, individually-reviewable, behavior-preserving steps. Each step lists **(goal)**, **(invariant preserved)**, **(parity harnesses that MUST stay green)**, and **(rollback)**. The strategy keeps trading and the drift net stays green after *every* step. No big-bang. Sequencing runs lowest-risk-scaffolding → retrofit-behind-interface → collapse-TL-copy → retire-TL-locals → version-split → time-bar support.

The single hardwired strategy seam we are working toward replacing is the touch block at `state.py:271-280` (verbatim, confirmed live):

```python
        for bar in candle_update.completed:
            if bar.timeframe_ticks != self.decision_timeframe:
                continue
            zones = self._zones_for_detection(bar.trading_day)
            detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
            for touch in detected:
                self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))
            touches.extend(detected)
```

The `process_event` dispatch (`state.py:229-236`) and the registry `activate` swap (`model_registry.py:238-255`, atomic, fail-closed) are kept verbatim throughout and are the two load-bearing seams the whole sequence routes around.

---

### Phase A — Pure scaffolding (new code only, alongside; zero behavior change)

**Step A1 — Introduce the `StrategyPlugin` Protocol + `BarSpec`/`SetupState`/`DecisionEvent`/`Barrier` types in `strategy_core`, unused.**
- *Goal:* Land the PROPOSED `runtime_checkable Protocol StrategyPlugin` and the supporting dataclasses (`BarSpec{kind: TICK|TIME, size, label}`, `SetupState`, `DecisionEvent`, `Barrier` Protocol with `fixed_points`|`r_relative`) in a new module (PROPOSED `strategy_core/strategies/__init__.py`) with NO call sites. Nothing imports them yet.
- *Invariant:* `StrategyRuntime`, `CandleEngine`, `StrategyLevelState`, `detect_touches`, `resolve_outcome` are untouched; `state.py:271-280` still runs the hardwired touch fold. Touch behavior is byte-identical.
- *Harnesses (all must stay green, all currently passing):* the SC golden unit suite — `tests/test_runtime_state.py`, `tests/test_runtime_touches.py`, `tests/test_runtime_touch_zones.py`, `tests/test_runtime_levels.py`, `tests/test_touch.py`, `tests/test_zones.py`, `tests/test_outcomes.py`, `tests/test_features.py`, `tests/test_sessions.py`, `tests/test_honest_entry.py`, `tests/test_candle_parity.py`, `tests/test_contract.py` — must be unaffected (new module is unimported). TL `tests/test_strategy_core_acceptance.py` and `tests/test_strategy_core_dependency.py` unaffected.
- *Rollback:* Delete the new module. Nothing else references it.

**Step A2 — Introduce the registry (`@register` + `get_strategy(strategy_id)`) in `strategy_core/strategies/registry.py`, empty.**
- *Goal:* Land the PROPOSED greppable, single-sourced registry inside SC (chosen over entry-points so the SHA-pinned TL and the unpinned-floating QL resolve it identically). It starts with zero registered strategies and is imported nowhere.
- *Invariant:* No dispatch path consults the registry; the single fixed pipeline still runs unconditionally. `strategy_id` remains the opaque label it is today (`model_registry.py:148`).
- *Harnesses:* same SC golden suite as A1 (must be unaffected — registry unimported). TL/QL suites unaffected.
- *Rollback:* Delete `registry.py`.

**Step A3 — Author `TouchReversalSection` SectionModel + a `TouchReversalPlugin` that *wraps the existing functions*, registered but not yet wired into the runtime.**
- *Goal:* Implement archetype 1 as a `StrategyPlugin`: `required_bars()` returns a single TICK `BarSpec` at the decision timeframe; `on_bar_closed` internally calls the *same* `build_zones → detect_touches` it does today; `label_policy()` declares `fixed_points` barrier reusing `resolve_outcome` (tp=15/sl=30 from `outcomes.py:127-136`); `feature_spec()` declares the six current features. `@register` it as `strategy_id="touch_reversal"`. Add a new SC unit test asserting the plugin's `detect_touches` output equals a direct `detect_touches` call on the same bars+zones.
- *Invariant:* The runtime does not yet call the plugin — `state.py:271-280` is still the live path. The plugin is provably a behavior-identical mirror, verified by the new test, not yet load-bearing.
- *Harnesses:* full SC golden suite (A1 list) stays green; the new plugin-equivalence test must pass. `tests/test_touch.py`, `tests/test_zones.py`, `tests/test_outcomes.py`, `tests/test_features.py` pin that the wrapped functions are unchanged.
- *Rollback:* Unregister/delete the plugin + SectionModel + new test. Runtime is unaffected (never wired).

---

### Phase B — Retrofit touch behind the interface (the one behavior-sensitive swap)

**Step B1 — Add an optional `plugin` param to `StrategyRuntime.__init__`, defaulting to `None`; when `None`, run the exact current `state.py:271-280` block.**
- *Goal:* Thread a keyword-only `plugin: StrategyPlugin | None = None` into the existing keyword-only `__init__` (`state.py:173-199`). When `plugin is None`, `_process_trade` executes the verbatim hardwired touch fold (no change). The branch is dead in production until B2.
- *Invariant:* Default construction (`plugin=None`) produces byte-identical `RuntimeUpdate` deltas. TL's service constructs the runtime exactly as today (`strategy_core_service.py:99-111`, still `plugin`-less) so it takes the `None` path.
- *Harnesses:* `tests/test_runtime_state.py`, `tests/test_runtime_touches.py`, `tests/test_runtime_touch_zones.py`, `tests/test_runtime_levels.py` (all exercise the default path); TL `tests/test_strategy_core_acceptance.py` (cross-runtime touch equality) and `tests/test_strategy_core_replay_integration.py`. The SC GATE pair `validation/test_production_pair_parity.py` + `validation/test_duckdb_streaming_parity.py` must stay green (default path = current engine bars). Decision-layer net: `validation/test_decision_diff.py` green.
- *Rollback:* Remove the param; restore the single hardwired block. One-file revert.

**Step B2 — Route `_process_trade` through `plugin.on_bar_closed` when a plugin is present, and construct `StrategyRuntime` with the registered `TouchReversalPlugin` in a feature-flagged path.**
- *Goal:* Replace `state.py:271-280` with a call to `plugin.on_bar_closed(bar, ctx)` returning a `StrategyStep{setups, decisions, features}`, mapping its touches back onto the existing `RuntimeUpdate.touches` field. Flip the construction site (behind a flag/env, default OFF) so the plugin path is exercised by tests and a canary before becoming default.
- *Invariant:* For `strategy_id="touch_reversal"`, the plugin-routed `RuntimeUpdate` is byte-identical to the `None`-path update (same touches, same `_touched_zone_keys` accounting, same decision-timeframe gating). This is the load-bearing equivalence — the drift net proves it, not inspection.
- *Harnesses (the drift net — MUST be green, never "unknown" after this step):* SC GATE `validation/test_production_pair_parity.py`; supporting `validation/test_duckdb_streaming_parity.py`; decision net `validation/test_decision_diff.py` + standing `tests/test_runtime_touches.py`/`tests/test_runtime_touch_zones.py`; TL `tests/test_strategy_core_acceptance.py` (run BOTH flag states — plugin path must equal direct-`StrategyRuntime` touches). Run `validation/parity_harness.py` / `validation/parity_harness_v2.py` (real-data money-path) and `validation/decision_diff_harness.py` on the plugin path before flipping the default.
- *Rollback:* Flip the flag back to OFF (default `plugin=None`). Production instantly returns to the verbatim hardwired path; the registry/plugin stay dormant. This is the safety net for the entire migration — every later phase keeps this OFF-switch intact.

**Step B3 — Make the plugin path the default for `strategy_id="touch_reversal"`; remove the dead hardwired duplicate only after a full green soak.**
- *Goal:* Default the flag ON; delete the now-duplicated inline touch block, leaving `plugin.on_bar_closed` as the sole path. The `None` fallback is retained as the rollback escape hatch (plugin defaults to the registered touch plugin).
- *Invariant:* Same RuntimeUpdate contract; touch strategy behavior unchanged.
- *Harnesses:* same drift net as B2 — `validation/test_production_pair_parity.py`, `validation/test_decision_diff.py`, `validation/test_duckdb_streaming_parity.py`, TL `test_strategy_core_acceptance.py`, plus the full SC golden suite. None may go red or unknown.
- *Rollback:* Re-flag to the `None`/hardwired path (kept in git history one commit back); revert the deletion commit.

---

### Phase C — Collapse Trade-Lab's contract copy onto the shared envelope

**Step C1 — Repoint TL `model_registry` import from the local contract copy to `strategy_core.contract`, keeping today's flat `StrategyContract` shape.**
- *Goal:* Change `model_registry.py:26` (`from trade_lab.domain.contracts import ContractError, StrategyContract, load_strategy_contract`) to import the canonical SC loader/schema. This *first* fixes the three known divergences by deletion-of-duplicate: SC `LabelPolicy` has `decision_offset_minutes` (`schema.py:161`), SC has `ResearchSessionExperiment` (`schema.py:187-198`), and SC `engine_version` is required (`schema.py:256`) — so a current QL-emitted v3 contract parses.
- *Invariant:* `model_registry.activate` (`model_registry.py:238-255`) stays atomic + fail-closed; `_validate_model_against_contract` (feature name/order/class-count/tick-size) and `_verify_checksum` unchanged. `strategy_id` still read opaquely (`:148`). The SC loader's `expected_engine_version` hook reproduces TL's fail-close (`loader.py:28-77`).
- *Harnesses:* TL `tests/test_engine_version_binding.py` (matching loads / mismatch rejected / legacy loads unbound) must stay green — re-point it at the SC loader semantics; TL `tests/test_strategy_contract.py` (retarget or retire); QL `tests/agents/test_strategy_contract_nodrift.py` and `test_strategy_contract_repoint.py` (emitter round-trips the SC loader) stay green. Drift net (B-phase) unaffected.
- *Rollback:* Revert the import to TL's local copy (`strategy_contract.py` still present). One-line revert.

**Step C2 — Delete TL's local `strategy_contract.py` once nothing imports it.**
- *Goal:* Remove the third-format copy entirely (`domain/contracts/strategy_contract.py`), eliminating the drift source permanently.
- *Invariant:* No behavior change — C1 already routed loads through SC.
- *Harnesses:* grep confirms zero importers; TL `tests/test_engine_version_binding.py` (on SC loader) green; QL contract tests green; B-phase drift net unaffected.
- *Rollback:* Restore the file from git + revert C1's import.

---

### Phase D — Retire Trade-Lab's local candles / sessions / levels duplications

**Step D1 — Retire TL's local outcome tracker in favor of the engine's honest decision-time fill.**
- *Goal:* Replace `services/inference/outcome_tracker.py` LEVEL-price entry (`entry_points = float(Decimal(prediction.level_price_ticks) * self._tick_size)`) with the engine's `resolve_honest_outcome`/`trade_price_at` path, killing the known divergence.
- *Invariant:* The inference seam stays SOFT — `runtime.py:313-346` still returns `()` with no active model and swallows exceptions off the hot path. Predictions/outcomes still attach in the TL-local `RuntimeUpdate` (`runtime.py:38-63`); the ws contract is unchanged.
- *Harnesses:* TL `tests/test_outcome_tracker.py` (retarget to the honest-entry result), `tests/test_touch_direction_fix.py` (authoritative Core direction still carried); SC `tests/test_honest_entry.py` and the Phase-8.1 golden `scripts/phase8_1_golden.py --mode compare` (golden vs engine byte-equal) pin that the relocated orchestration is identical. B-phase drift net unaffected.
- *Rollback:* Revert to the local tracker (kept one commit back); inference seam tolerates either since it is failure-soft.

**Step D2 — Confirm TL holds no local candle/session/level recompute, then assert it via test.**
- *Goal:* The service already owns no strategy meaning (`strategy_core_service.py:1-7`: "must not recompute session/level/touch strategy meaning"). Add/keep a guard test that TL routes all candle/session/level/touch computation through `StrategyRuntime` and never re-derives them.
- *Invariant:* TL remains a thin adapter; session names `"asia"/"london"` and v3 windows come only from SC `classify_session`/`StrategyLevelState`.
- *Harnesses:* TL `tests/test_strategy_core_service.py` (path-free snapshot; trade/quote→DTO mapping), `tests/test_strategy_core_acceptance.py`, `tests/test_strategy_core_replay_integration.py`. B-phase drift net unaffected.
- *Rollback:* N/A (assertion-only); if the guard test surfaces a hidden recompute, fix it before proceeding.

---

### Phase E — Version split (platform_version vs per-plugin strategy_version)

**Step E1 — Introduce `platform_version` alongside `ENGINE_VERSION`, both stamped, loader fail-closes on either.**
- *Goal:* Add a `platform_version` stamp in SC `__init__.py` (next to `ENGINE_VERSION = "strategy_core_engine_v3"`, `:54`) and have the loader fail-close on it exactly as it does `engine_version` today (`loader.py:64-70`). Keep `ENGINE_VERSION` emitted/checked in parallel during the transition.
- *Invariant:* Existing v3 bundles still load (both stamps present and matching). `CONTRACT_VERSION = "trade_lab_contract_v1"` unchanged, so cross-boundary parseability holds.
- *Harnesses:* SC `tests/test_contract.py`, TL `tests/test_engine_version_binding.py`, QL `tests/agents/test_strategy_contract_nodrift.py` (every structural emitted field still single-sourced from `strategy_core.constants`) + `test_strategy_contract_repoint.py`. Drift net unaffected.
- *Rollback:* Drop `platform_version` checks; revert to `ENGINE_VERSION`-only binding.

**Step E2 — Add per-plugin `strategy_version`/`strategy_id`, fail-closed via registry-lookup equality; turn `strategy_id` into a router.**
- *Goal:* Loader resolves the plugin via `get_strategy(contract.strategy_id)` and checks `strategy_version` equality; `model_registry.activate` (`:238-255`) gains `plugin_cls=get_strategy(contract.strategy_id)`, turning the opaque label (`:148`) into a fail-closed router. Retuning touch barriers now bumps only `touch_reversal`'s `strategy_version`; the platform pin and other bundles stay valid.
- *Invariant:* Unknown/mismatched `strategy_id`/`strategy_version` fails activation closed, leaving the prior active model in place (atomic swap preserved, `:253-254`). Existing single `touch_reversal` bundle activates exactly as before.
- *Harnesses:* TL `tests/test_engine_version_binding.py` (extend to strategy_version mismatch); SC `tests/test_contract.py`; QL contract tests; B-phase drift net (touch behavior under `touch_reversal` unchanged).
- *Rollback:* Revert `activate` to opaque-label behavior and drop the registry-equality check; loader falls back to `platform_version`-only binding from E1.

**Step E3 — Decompose the flat `StrategyContract` into `StrategyEnvelope` + typed `SectionModel`; emit from the plugin.**
- *Goal:* Split the 20-field flat contract (`schema.py:246-278`) into the PROPOSED platform-owned `StrategyEnvelope` + a `TouchReversalSection` (`session_scheme/level_scheme/touch_rule/feature_windows/label_policy/inference/research_session_experiment`). Loader validates the envelope, fail-closes versions, resolves the plugin, then `section = plugin.SectionModel.model_validate(envelope.section)` (each section `extra="forbid"`). The QL emitter generates the section FROM the plugin's `feature_spec`/`label_policy`/`SectionModel`, killing the third-format drift at the source.
- *Invariant:* The fully-assembled contract for `touch_reversal` carries the same effective fields the flat schema did; model/feature/class-count/tick-size validation (`model_registry.py:332-348`) unchanged.
- *Harnesses:* QL `tests/agents/test_strategy_contract_nodrift.py` (the leaf-coverage guard — every `SectionModel` leaf must be single-sourced; a new uncovered field FAILS) and `test_strategy_contract_repoint.py`; SC `tests/test_contract.py`; TL `tests/test_engine_version_binding.py`. Drift net unaffected.
- *Rollback:* Keep emitting/accepting the flat contract (both code paths retained one release); revert the loader to flat `model_validate`.

---

### Phase F — Time-bar candle support (the one genuinely new platform capability)

**Step F1 — Extend the candle data shape with a `BarSpec`/`kind` and add `CloseReason.INTERVAL`, with TICK behavior unchanged.**
- *Goal:* Generalize `CandleEngine` from TICK-only (close trigger `candle.trade_count == timeframe`, `streaming.py:180-181`; `CloseReason {COMPLETE, END_OF_DAY}`, `types.py:51-55`) to accept a `BarSpec{kind: TICK|TIME, size, label}`. Add a `CloseReason.INTERVAL` member. TICK specs route through the existing unchanged code path; TIME is a new, separately-tested close trigger (elapsed-time / clock boundary).
- *Invariant:* For all-TICK timeframes, every bar is byte-identical to today — the new `BarSpec`/`INTERVAL` code is inert on the TICK path. The day-rollover `END_OF_DAY` freeze (`streaming.py`) is untouched.
- *Harnesses:* `tests/test_candle_parity.py` (batch `build_tick_bars_from_frame` vs streaming, byte-identical) is the hard gate — TICK output must not move; `validation/phase4b_validate.py` (vectorized == itertuples); the SC GATE `validation/test_production_pair_parity.py` + `validation/test_duckdb_streaming_parity.py` (streaming == DuckDB bars) must stay byte-for-byte. Decision net `validation/test_decision_diff.py` green.
- *Rollback:* Remove the `BarSpec`/`INTERVAL` branch; `CandleEngine` reverts to tick-only. No production bundle requests TIME bars yet, so nothing depends on it.

**Step F2 — Mirror the TIME close trigger into the vectorized batch path and pin it with a new parity test.**
- *Goal:* Add the equivalent TIME-bucketing to `build_tick_bars_from_frame` (`batch.py:38-193`, currently `cumcount() // timeframe`, `batch.py:124`) so streaming and batch agree on TIME bars too. Add a TIME-bar parity test alongside `test_candle_parity.py`.
- *Invariant:* Batch and streaming produce identical TIME bars; TICK bars remain byte-identical (the existing parity lock).
- *Harnesses:* `tests/test_candle_parity.py` (extended with TIME cases — both kinds must match); `validation/phase4b_validate.py`; the GATE pair stays green on the TICK production pair.
- *Rollback:* Remove the batch TIME path + its test; streaming TIME (F1) can stand alone until re-mirrored, but no bundle uses it.

**Step F3 — Validate archetype 2 (HTF-FVG/iFVG) end-to-end on the same interface as a NEW plugin, behind its own `strategy_id`.**
- *Goal:* Register a second plugin whose `required_bars()` returns the eight TIME `BarSpec`s (1m..4H), a multi-phase `SetupState` state machine (scanning/htf_tapped/parent_locked/inverted/armed/invalidated/expired), and an `r_relative` Barrier (`stop_price=manipulation swing`, `target_price=entry±1R`) reusing `classify_mae_first` by deriving per-setup tp/sl from R. It is selected only by its own `strategy_id`; `touch_reversal` is untouched.
- *Invariant:* The platform interface needs NO redesign (the only new capability is the F1/F2 TIME-bar trigger). `touch_reversal` production behavior is unchanged — the new plugin coexists, routed by `strategy_id` (E2) and version-split (E1/E3).
- *Harnesses:* per-plugin decision/feature/label parity becomes a NEW harness for the iFVG plugin (the platform candle/level parity — `test_candle_parity.py`, the GATE pair — still guards the shared platform); `touch_reversal`'s drift net (B/F phases) must remain green throughout, proving coexistence.
- *Rollback:* Unregister the iFVG plugin; no bundle activates it, so production is unaffected.

---

**Net invariant across all phases:** at every step the touch strategy keeps trading via the same `RuntimeUpdate`/`ws.v1` contract; the drift net (`validation/test_production_pair_parity.py`, `validation/test_decision_diff.py`, `validation/test_duckdb_streaming_parity.py`, `tests/test_candle_parity.py`, TL `tests/test_strategy_core_acceptance.py`) is green and never "unknown"; and the B2 plugin-OFF flag (default `plugin=None` → verbatim `state.py:271-280`) remains the universal rollback until B3, after which the immediately-prior commit is the escape hatch.

---

## 8. Risk register

This register enumerates every parity / golden harness in the evidence inventory BY NAME with its path and what it guards, then maps the highest-risk moves in the §7 sequence onto the specific mitigation that keeps each harness green. The §7 moves referenced are the four genuinely new/invasive ones implied by the PROPOSED design: **(M1) extract the hardwired touch block** at `state.py:271-280` behind a plugin hook; **(M2) add the `BarSpec`/TIME-bar close trigger** (`CloseReason.INTERVAL`) to the candle engine — the one new platform capability; **(M3) split the flat `StrategyContract` (schema.py:246-278)** into `StrategyEnvelope` + typed `SectionModel`, and repoint the QL emitter / TL local copy onto it; **(M4) split `ENGINE_VERSION` into `platform_version` + per-plugin `strategy_version`** and turn `strategy_id` into a registry router in `model_registry.activate` (`model_registry.py:238-255`).

### 8.1 Harness inventory — name, path, what it guards

**Strategy-Core `validation/` (money-path harnesses & gates)**

| Harness | Path | Guards |
|---|---|---|
| production-pair parity (GATE, phase 4e) | `C:/Users/gonza/Documents/Strategy-Core/validation/test_production_pair_parity.py` | Research DuckDB side-signed-order bars == Trade-Lab WIRE-order streaming bars on order/membership-sensitive core fields. The real production pair. |
| duckdb-streaming parity | `C:/Users/gonza/Documents/Strategy-Core/validation/test_duckdb_streaming_parity.py` | Research DuckDB batch bars == engine STREAMING bars byte-for-byte on the same side-signed order (supports the GATE). |
| decision-diff (standing test) | `C:/Users/gonza/Documents/Strategy-Core/validation/test_decision_diff.py` | 147t trade-price bar residual reaching the DECISION layer under the honest rule → NO label flips, same survive/drop partition, feature diffs below epsilon. |
| decision-diff harness (phase-4f Part-2) | `C:/Users/gonza/Documents/Strategy-Core/validation/decision_diff_harness.py` | RESEARCH vs TRADE-LAB 147t trade-price bars under engine-v3 honest decision-time labeling; measures whether the ~1% bar residual reaches levels/zones/touches/labels/features. |
| parity harness (port-fidelity) | `C:/Users/gonza/Documents/Strategy-Core/validation/parity_harness.py` | Stage-by-stage `strategy_core` vs canonical CQL on REAL book-mid data (zones/sessions/touches/labels/interaction must_match; trade-price interaction expected_differ; 3 approach must_match). |
| parity harness v2 | `C:/Users/gonza/Documents/Strategy-Core/validation/parity_harness_v2.py` | Full-range (2025-07-01..09-05) parity with deterministic candle Stage 0 + Chicago-localized window fix; engine==canonical money-path. |
| phase4b validate | `C:/Users/gonza/Documents/Strategy-Core/validation/phase4b_validate.py` | Vectorized `build_tick_bars_from_frame` == old `.itertuples()` emit exactly; 18:00-ET trading-day boundary; benchmark. |
| phase4d liveorder | `C:/Users/gonza/Documents/Strategy-Core/validation/phase4d_liveorder.py` | Whether the LIVE WIRE order reproduces the proven composite DuckDB order (COMP vs TE vs PHYS). |

**Strategy-Core `tests/` (golden units)**

| Harness | Path | Guards |
|---|---|---|
| candle parity | `C:/Users/gonza/Documents/Strategy-Core/tests/test_candle_parity.py` | Batch (`build_tick_bars_from_frame`) vs streaming (`CandleEngine`) field-for-field identical on the same synthetic stream, spanning the 18:00-ET rollover and the CT closed-window drop path (docstring `:1-17`, `astuple` compare `:21`). |
| strategy-contract golden | `C:/Users/gonza/Documents/Strategy-Core/tests/test_contract.py` | Promoted `strategy.json` schema + fail-closed loader incl. required `engine_version` binding; one-mutation negatives. |
| touch golden | `C:/Users/gonza/Documents/Strategy-Core/tests/test_touch.py` | First-touch semantics vs canonical `dashboard_utility_builder.py:414-440` (closed-interval straddle, first-touch-per-zone, low→LONG/high→SHORT). |
| zones golden | `C:/Users/gonza/Documents/Strategy-Core/tests/test_zones.py` | `build_zones` byte-for-byte vs canonical `_build_zones` (`<=` boundary, ties→LOW, mean rep price, chained merge vs last level). |
| outcomes golden | `C:/Users/gonza/Documents/Strategy-Core/tests/test_outcomes.py` | MAE-first labeler vs `dashboard_utility_labeling.py:44-108`; both-breach→LOSS guard. |
| features golden | `C:/Users/gonza/Documents/Strategy-Core/tests/test_features.py` | The 3 interaction + 3 approach formulas hand-computed vs canonical sources. |
| sessions golden | `C:/Users/gonza/Documents/Strategy-Core/tests/test_sessions.py` | ET classification + 18:00-ET boundary; v3 windows (asia 19:00→02:45 xmid, london 03:00→08:00, ny 09:00→17:00). |
| honest-entry golden | `C:/Users/gonza/Documents/Strategy-Core/tests/test_honest_entry.py` | `resolve_honest_outcome` traded path + all four drop arms (flatten/cutoff/no_fill/no_forward). |
| runtime-state | `C:/Users/gonza/Documents/Strategy-Core/tests/test_runtime_state.py` | `StrategyRuntime` event-at-a-time state machine over trades/quotes. |
| runtime-touches | `C:/Users/gonza/Documents/Strategy-Core/tests/test_runtime_touches.py` | Touches fire on completed-bar RANGE intersection not exact trade price, and the availability gate blocks pre-session-close self-touch (`:7-14`, `:17-27`). |
| runtime-touch-zones (audit #3) | `C:/Users/gonza/Documents/Strategy-Core/tests/test_runtime_touch_zones.py` | `_zones_for_detection` merges ALL levels then gates each merged zone on MAX availability (no pre-filter): one merged zone at mean 101.25, fires once after MAX avail, never re-fires (`:23-83`). |
| runtime-levels | `C:/Users/gonza/Documents/Strategy-Core/tests/test_runtime_levels.py` | Runtime level-state machine / prior-day summary handling. |
| (runtime suite, in scope) | `tests/test_runtime_live.py`, `test_runtime_replay.py`, `test_runtime_updates.py`, `test_data_ordering.py`, `test_databento_live_source.py`, `test_databento_parquet_source.py` | Live/replay loop, RuntimeUpdate deltas, wire ordering, source adapters. |

**Trade-Lab `backend/tests/`**

| Harness | Path | Guards |
|---|---|---|
| strategy-core acceptance | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_strategy_core_acceptance.py` | TL `ApplicationRuntime` touch output == a direct `StrategyRuntime` run on the same trades; the merged-zone/availability asia-high scenario (`:30-51`). |
| engine-version binding | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_engine_version_binding.py` | Fail-closed engine_version binding: match loads, mismatch rejected, legacy (no field) loads unbound — reads the real fixture, mutates, writes tmp. |
| strategy-core service | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_strategy_core_service.py` | `StrategyCoreService` produces a path-free snapshot; trade/quote → DTO mapping. |
| strategy-core dependency | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_strategy_core_dependency.py` | The `strategy_core` dependency imports and exposes a `strategy_core_engine_*` ENGINE_VERSION. |
| replay integration | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_strategy_core_replay_integration.py` | End-to-end replay through `ApplicationRuntime` over a fake historical source. |
| touch-direction-fix | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_touch_direction_fix.py` | Authoritative Core `Touch.direction` carried, not re-derived from `level_kind`. |
| outcome-tracker | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_outcome_tracker.py` | TL-local MAE-first tracker (LEVEL-price entry — the known divergence the repoint retires). |
| TL local contract | `C:/Users/gonza/Documents/Trade-Lab/backend/tests/test_strategy_contract.py` | TL's local divergent contract loader. |
| serialization / api contract | `tests/test_serialization_contract.py`, `tests/test_api_contract.py` | The `RuntimeUpdate`→`ws.v1` Envelope wire shape (`MESSAGE_VERSION="ws.v1"`, `extra="forbid"`). |

**Quant-Lab `tests/agents/` + phase-8.1 golden script**

| Harness | Path | Guards |
|---|---|---|
| decision-repoint parity | `C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_decision_repoint_parity.py` | Standing BOOK-MID parity: `engine_decision` (book-mid mode) == legacy CQL decision code EXACTLY — zones, touches, labels, 6 features "max abs diff must be 0", integrated rows. |
| strategy-contract no-drift | `C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_strategy_contract_nodrift.py` | Every structural emitted field == its `strategy_core.constants` value, PLUS a coverage guard that enumerates EVERY `StrategyContract` leaf via `_model_leaf_paths` over `model_fields` (`:174-191`) and FAILS on any uncovered leaf (`:278-285`); emitted contract re-loads through the shared SC loader fail-closed. |
| strategy-contract repoint | `C:/Users/gonza/Documents/Claude-Quant-Lab/tests/agents/test_strategy_contract_repoint.py` | The emitter is literal-free + `engine_version`-stamped and round-trips through the shared SC schema/loader binding; pure config→dict. |
| phase8_1 golden | `C:/Users/gonza/Documents/Claude-Quant-Lab/scripts/phase8_1_golden.py` | `--mode golden` (inline pre-refactor orchestration) vs `--mode engine` (`strategy_core.resolve_honest_outcome`) byte-compared field-by-field via `--mode compare`; guards that relocating the honest-entry orchestration into the engine changed nothing. Companion: `scripts/decision_repoint_proof.py`. |

### 8.2 Highest-risk moves → which harness each endangers → specific mitigation

**M1 — Extract the hardwired touch block (`state.py:271-280`) behind a plugin hook.** Most endangers: **runtime-touch-zones (audit #3)**, **runtime-touches**, **runtime-state**, **strategy-core acceptance**. These pin exact runtime side effects: the merge-all-then-gate-on-MAX-availability zone composition, `representative_price==101.25`, the `_touched_zone_keys` first-touch-per-cluster-per-day dedup, range-intersection (not exact-price) firing, and TL↔SC cross-runtime touch identity. Any change to *when/where* `detect_touches` runs or how `_touched_zone_keys` is updated breaks them.
- **Mitigation:** Keep `process_event` dispatch (`state.py:229-236`) and the decision-timeframe gate (`bar.timeframe_ticks == self.decision_timeframe`, `state.py:272-273`) verbatim. Move the *body* of the touch block into the default `touch_reversal` plugin's `on_bar_closed` WITHOUT altering the call shape: still `detect_touches((bar,), zones, tick_size=..., trading_day=bar.trading_day)`, still flip `_touched_zone_keys` via the same `_touch_zone_key_from_touch`, still source zones from `_zones_for_detection` (merge-all). The plugin must surface the same `Touch` objects into `RuntimeUpdate.touches`. Land M1 as a pure refactor with the plugin pre-wired as the only strategy so these four harnesses pass byte-identically BEFORE any second plugin or interface generalization. Do not touch the availability-gate ordering (`touch.py:93`) — runtime-touches `:17-27` and audit #3 `:60-63` assert no fire before MAX availability.

**M2 — Add `BarSpec`/TIME-bar close trigger (`CloseReason.INTERVAL`).** Most endangers: **candle parity**, **duckdb-streaming parity**, **production-pair parity (GATE)**, **phase4b validate**, **decision-diff**. `test_candle_parity.py` compares `Bar` via `astuple` field-for-field (`:21`) across streaming vs batch; the production GATE and duckdb-streaming parity are byte-for-byte on bar fields and ordering. Adding a new enum member and a new close path risks (a) changing `Bar`/`CloseReason` shape or default field ordering, (b) introducing a code path that the batch builder (`build_tick_bars_from_frame`) does not mirror, breaking batch↔streaming parity.
- **Mitigation:** Make TICK the unchanged default — the new INTERVAL trigger must be DEAD for any TICK `BarSpec`, so every existing tick-bar test exercises the identical `if candle.trade_count == timeframe` path (`streaming.py:180-181`) and emits `CloseReason.COMPLETE`/`END_OF_DAY` exactly as today (`types.py:51-55`). Append `CloseReason.INTERVAL` as a NEW member without reordering the existing two and without adding/reordering `Bar` fields (preserve `astuple` order so candle parity's tuple compare is unaffected). Time-bar parity is a NEW per-plugin obligation, not retrofitted into the existing tick harnesses: only archetype-2 (iFVG) adds a time-bar parity case. Confirm `parity_harness.py`/`parity_harness_v2.py`/`phase4b_validate.py` still run TICK-only inputs so the engine==canonical money-path gate is untouched.

**M3 — Split the flat `StrategyContract` into `StrategyEnvelope` + typed `SectionModel`; repoint the QL emitter and TL local copy.** Most endangers: **strategy-contract no-drift**, **strategy-contract repoint**, **strategy-core acceptance/contract golden (`test_contract.py`)**, **engine-version binding**, **TL local contract / serialization tests**. The no-drift coverage guard enumerates every leaf of `StrategyContract` via `_model_leaf_paths(StrategyContract)` over `model_fields` (`test_strategy_contract_nodrift.py:174-191`) and FAILS on any leaf with no constant/allow-list source (`:282-285`); restructuring the model into envelope+section moves every leaf's dotted path (e.g. `touch_rule.zone_proximity_pts` → `section.zone_proximity_pts`) and will trip this guard wholesale. It also re-loads the emitted dict through the shared SC loader fail-closed (`:27`), so the emitter and schema must change in lockstep.
- **Mitigation:** Update the no-drift constant-map AND `_model_leaf_paths` traversal in the SAME commit as the schema split so the leaf set the guard expects matches the new envelope/section shape — keep the *coverage* property (every leaf sourced) intact, only re-key the dotted paths. The QL emitter (`Claude-Quant-Lab/.../ml/strategy_contract.py`) must emit the new envelope+section nesting and stay literal-free (all structural values still from `k.*`) so repoint passes. Crucially, this split is the OPPORTUNITY to fix the three TL divergences (TL local `LabelPolicy` missing `decision_offset_minutes`, missing `research_session_experiment`, optional `engine_version`): retire the TL hand-written copy (`Trade-Lab/.../domain/contracts/strategy_contract.py`) and repoint `model_registry.py:26` onto the SC `strategy_core.contract` package, then update `test_strategy_contract.py` / `test_strategy_core_service.py` to the shared schema. Because every section is `extra="forbid"`, validate that the QL-emitted section round-trips before flipping `model_registry` over — `test_strategy_core_acceptance.py` and the replay integration test exercise the activate path end-to-end and will catch a section that fails to parse.

**M4 — Split `ENGINE_VERSION` into `platform_version` + per-plugin `strategy_version`; make `strategy_id` a registry router.** Most endangers: **engine-version binding**, **strategy-core dependency**, **strategy-contract no-drift/repoint**, **model_registry activation (acceptance + replay integration)**. `test_engine_version_binding.py` asserts the EXACT fail-closed semantics on a field named `engine_version` (match loads / mismatch rejected / legacy unbound); `test_strategy_core_dependency.py` asserts a `strategy_core_engine_*` `ENGINE_VERSION` is exposed. Renaming/splitting the version field and turning `strategy_id` from an opaque label (`model_registry.py:148`) into a `get_strategy(contract.strategy_id)` router in `activate` (`model_registry.py:238-255`) is a fail-close behavior change.
- **Mitigation:** Preserve the loader's fail-closed comparison shape (the `expected_*_version` hook at `loader.py:64-70`) — `platform_version` inherits the exact match/mismatch/absent logic `engine_version` has today, so `test_engine_version_binding.py` ports by field rename only, with the legacy-unbound arm kept. Keep `ENGINE_VERSION` (or an alias) exported from `strategy_core/__init__.py:54` until `test_strategy_core_dependency.py` is updated, so the dependency smoke test never sees a missing symbol mid-migration. Introduce the registry (`strategy_core/strategies/registry.py`) with `touch_reversal` pre-registered so `get_strategy(strategy_id)` resolves the existing single strategy; the router must be ADDITIVE in `activate` — an unknown `strategy_id` fails closed (raise, leaving `self._active` unchanged per `:244-245`), and a known one resolves to today's behavior, so the acceptance and replay-integration paths see identical output.

**Cross-cutting (all moves) — the ws transport.** Any move that adds a delta type or payload field endangers **serialization/api contract** tests: the Envelope is frozen at `MESSAGE_VERSION="ws.v1"` with `extra="forbid"` (`api/dto.py:24,42,214-219`) and the `MessageType` Literal enumerates exactly 12 types. Mitigation: route plugin-emitted events through a GENERIC frame whose `payload` is the plugin's typed event (per the PROPOSED design) so no new top-level `MessageType` member is added under `ws.v1`; the envelope still does not carry `engine_version`/`strategy_id` at the frame level (`strategy_id` rides only inside `model.status`), so M3/M4 need not touch the wire version.

**Cross-cutting (QL only) — the undeclared `strategy_core` dependency.** Every SC-side schema/version change (M2/M3/M4) endangers QL silently because `strategy-core` is NOT a declared dependency in `Claude-Quant-Lab/pyproject.toml` (no git URL, no lock, no `.pth`) — QL floats to whatever SC commit is on `PYTHONPATH=src`, while TL is SHA-pinned at `backend/pyproject.toml:19`. Asymmetric binding means the no-drift/repoint tests can pass against a *different* SC than the one TL pins. Mitigation: as part of M3/M4, pin QL to the same SC SHA as TL (declare it in `pyproject.toml`) so both consumers validate against one platform version; otherwise a leaf-path rename in the no-drift coverage guard can be green in QL and broken in TL simultaneously.

---

## 9. Decisions needed from the owner before implementation

Every item below is a FORK the owner must resolve before code is written. Each carries my recommended default plus the trade-off, but the choice is the owner's. Citations are verbatim from current source; everything labelled PROPOSED is target design, not present code.

---

### 9.1 — Strategy-plugin interface shape: `Protocol` vs `ABC` vs callable-bundle

**Context.** No strategy abstraction exists today (negative confirmed by grep across all three repos). The only "strategy" is the hardwired touch pipeline inside `StrategyRuntime._process_trade` (`C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/runtime/state.py:262-290`), with the strategy logic baked in at lines 271-280:

```python
        for bar in candle_update.completed:
            if bar.timeframe_ticks != self.decision_timeframe:
                continue
            zones = self._zones_for_detection(bar.trading_day)
            detected = detect_touches((bar,), zones, tick_size=self.tick_size, trading_day=bar.trading_day)
            for touch in detected:
                self._touched_zone_keys.add(self._touch_zone_key_from_touch(touch, zones))
            touches.extend(detected)
```

The §2 PROPOSED design names a `runtime_checkable Protocol StrategyPlugin`. The fork is whether it is a structural `Protocol`, a nominal `ABC` base class, or a flat callable/dataclass bundle.

- **Option A (RECOMMENDED): `runtime_checkable` Protocol.** Plugins satisfy it structurally; archetype 1 and archetype 2 can be wholly independent classes with no import of a shared base. Matches the existing dependency-light, duck-typed style (the engine already composes subsystems by call shape, not inheritance). Trade-off: `runtime_checkable` checks method *presence* only, not signatures — a wrong signature fails at call time, not registration time, so registry-time validation must be explicit.
- **Option B: `abc.ABC`.** Compile-time enforcement of the method set; clearer error if a method is missing. Trade-off: forces every plugin to import and subclass an SC type, coupling QL/TL plugin authors to an SC class hierarchy and breaking the current "engine is stdlib-light" boundary.
- **Option C: callable bundle / dataclass of functions.** Maximally simple. Trade-off: cannot express the multi-stage `SetupState` lifecycle (arm/lock/invalidate) cleanly — archetype 2 needs methods that mutate setup state across events, which is awkward as loose functions.

**Recommendation: Option A (Protocol), with a one-time registry-time assertion** (e.g. verify `required_bars()` returns `BarSpec`s and `SectionModel` is a `BaseModel` subclass) so the structural looseness is caught at `@register` import, not in the hot path.

---

### 9.2 — Registry mechanism: in-package registry module vs setuptools entry-points

**Context.** No registration mechanism exists (`entry_points`/`register_strategy`/`STRATEGY_REGISTRY`/`@register` all returned zero hits across the three `pyproject.toml`s and `src/` trees). Today TL pins SC by git SHA (`backend/pyproject.toml:19`) while QL imports `strategy_core` **undeclared and unpinned** (`engine_decision.py:45-70` imports it; QL `pyproject.toml:12-48` does not list it — the asymmetric-binding risk in §2b).

- **Option A (RECOMMENDED): in-package registry module** `strategy_core/strategies/registry.py` with a `@register` decorator + `get_strategy(strategy_id)`. Single-sourced inside SC, so the SHA-pinned TL and the floating QL resolve the SAME registry by construction; it is greppable; it ships with the engine pin.
- **Option B: setuptools entry-points.** Plugins register via `[project.entry-points]` in their own packages; SC discovers them at runtime. Trade-off: discovery depends on what is *installed* in each environment, which is exactly the QL-vs-TL asymmetry that bites us today — QL could float a different plugin set than TL. It also adds install-time machinery (none of the three repos use entry-points now) and is harder to grep.

**Recommendation: Option A.** It directly counters the undeclared-dependency drift and keeps strategy resolution deterministic across both consumers. (Sub-decision deferred to the dependency policy in 9.6: this only works if QL's `strategy_core` dependency is *declared*.)

---

### 9.3 — How the contract's strategy SECTION is versioned (and where the version line is drawn)

**Context.** Today there is ONE global stamp pair, single-sourced in SC `__init__.py` (re-confirmed verbatim):

```python
ENGINE_VERSION = "strategy_core_engine_v3"   # __init__.py:54
CONTRACT_VERSION = "trade_lab_contract_v1"   # __init__.py:57
```

`ENGINE_VERSION` fail-closes in the loader (`contract/loader.py:28-77`, `expected_engine_version` hook). The coupling: ANY engine change (even retuning touch barriers) bumps the single `ENGINE_VERSION` and invalidates EVERY bundle across BOTH consumers. The §2 PROPOSED split is `platform_version` (one line, both consumers pin) + per-plugin `strategy_version`/`strategy_id` (fail-closed via registry equality).

The fork is the *granularity* of section versioning:

- **Option A (RECOMMENDED): two-axis — `platform_version` + per-plugin `strategy_version`.** Platform-contract changes bump `platform_version` (fail-closed in loader exactly like `engine_version` today); a plugin retune bumps only that plugin's `strategy_version`. Retuning touch tp/sl no longer invalidates the FVG bundle or the platform pin. Trade-off: two version surfaces to reason about; the loader must check both (platform via literal equality, strategy via registry lookup).
- **Option B: keep one global version.** Simplest; one number. Trade-off: preserves the current any-change-resyncs-both-consumers coupling — the exact pain this refactor exists to remove.
- **Option C: per-SECTION semver inside the section model.** Each section model self-versions. Trade-off: over-engineered for two strategies; multiplies the version-matrix the loader must validate.

**Recommendation: Option A.** Also decide the **bump policy in writing**: does a *backward-compatible* section field addition bump `strategy_version` (I recommend yes — `extra="forbid"` on each section, see §1 divergences, means any added key is breaking unless the consumer schema also moves). This is the owner's call because it sets the cadence at which bundles must be re-emitted.

---

### 9.4 — Does TIME-bar candle support land in THIS refactor or a follow-up?

**Context.** This is the single largest scoping fork. The engine is **TICK-ONLY** — proven, not incidental:

```python
            if candle.trade_count == timeframe:
                completed.append(candle.freeze(complete=True, reason=CloseReason.COMPLETE))
                del current[timeframe]
```
(`C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/candles/streaming.py:180-181`)

`CloseReason` has exactly two members, `COMPLETE` and `END_OF_DAY` (`types.py:51-55`) — no `INTERVAL`/`TIME` close trigger anywhere in `streaming.py` or `batch.py`. The validation message is literally `"tick timeframes must be positive"` (`streaming.py:108`). Archetype 2 needs TIME bars at SEVEN+ resolutions: per `docs/ifvg-strat.md` §4.2, HTF 1H/4H, parents 3m/5m/10m/15m/30m, execution 1m — and §4.1 says it is "designed for a 1-minute chart" with non-1m charts "invalid." Archetype 1 needs none of this (single TICK decision bar). The §2 design calls the `BarSpec {kind: TICK|TIME, size, label}` + `CloseReason.INTERVAL` trigger "the ONE genuinely new platform capability."

- **Option A (RECOMMENDED for THIS refactor): ship the plugin interface + contract/version/registry split NOW; declare `BarSpec` in the Protocol surface (`required_bars()` already returns `tuple[BarSpec]`) but land the TIME-bar *engine implementation* as a fast-follow.** Archetype 1 is fully expressible and shippable with TICK-only candles; the interface is *validated against archetype 2 on paper* (which §2's ARCHETYPE VALIDATION already does) without forcing the elapsed-time close-trigger work into the critical path. The byte-identical streaming↔batch parity (`tests/test_candle_parity.py`) and the production-pair gates (`validation/test_production_pair_parity.py`) must continue to pass untouched, which is easier if the candle engine is not simultaneously being rewritten.
- **Option B: build TIME bars in THIS refactor.** One landing, archetype 2 immediately runnable end-to-end. Trade-off: net-new close-trigger logic in BOTH candle paths (streaming AND the vectorized `build_tick_bars_from_frame`, `batch.py:38-193`), a new `CloseReason` member, new day-rollover-vs-interval-edge interaction, and a parity proof for the new path — all while refactoring the runtime seam. High blast radius on the money-path harnesses.

**Recommendation: Option A.** Decouple interface-shape risk from new-capability risk. The owner should confirm there is no near-term commitment to *run* archetype 2 that forces Option B; if archetype 2 is genuinely 6+ months out, do not let its candle needs gate the interface refactor.

---

### 9.5 — Package and naming: platform package name, strategy package layout, `strategy_id` scheme

**Context.** Today `strategy_id` is **opaque and non-routing** — read off the contract and carried as a label only: discovery sets `ModelBundle.strategy_id = contract.strategy_id` (`C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/services/model_registry.py:148`) and there is no `strategy_id`-driven dispatch (selection is by allowlisted directory name via `is_safe_model_id`). The §2 design turns it into a fail-closed router (`plugin_cls=get_strategy(contract.strategy_id)` in `activate`). That only works if the scheme is stable and registry-keyed.

Three sub-forks:

- **(a) Platform package name.** RECOMMEND keeping `strategy_core` as the platform package (it is already the SHA-pinned dep in TL and the import in QL; renaming ripples through `backend/pyproject.toml:19`, `engine_decision.py:45-70`, and every `import strategy_core` site). Do NOT rename in this refactor; the "platform vs strategy" distinction is expressed by sub-packages (`strategy_core/strategies/...`), not a new top-level name. Trade-off: the name `strategy_core` slightly under-sells its new role as a platform, but the churn cost of renaming outweighs the clarity gain.
- **(b) Strategy package layout.** RECOMMEND `strategy_core/strategies/<strategy_id>/` co-located inside SC (e.g. `strategies/touch_reversal/`, `strategies/ifvg/`), each exporting its plugin class + typed `SectionModel`. Keeps the registry single-sourced (9.2 Option A) and lets QL's emitter generate the contract FROM the plugin's `SectionModel`/`feature_spec`/`label_policy`. Trade-off: strategies live in the engine repo rather than their own packages — fine for two first-party strategies, revisit if third-party strategies ever appear.
- **(c) `strategy_id` scheme.** RECOMMEND a stable, registry-keyed slug distinct from the bundle directory name and from `strategy_version` — e.g. `touch_reversal`, `ifvg`. Today the bundle dir (`is_safe_model_id`, `model_registry.py:58-68`) and `strategy_id` are independent; keep them independent but make `strategy_id` the registry key. Do NOT encode the version into `strategy_id` (version is the separate 9.3 axis). Trade-off: requires a one-time decision that existing production bundles (e.g. the `NQ_2026...` dirs) get their `strategy_id` set to `touch_reversal` so they resolve through the new router.

**Recommendation:** keep `strategy_core`; layout `strategy_core/strategies/<id>/`; `strategy_id` = stable lowercase slug, registry-keyed, version-free.

---

### 9.6 — Editable-vs-pinned dependency policy (and closing the QL undeclared-dep hole)

**Context.** This is a CONFIRMED current defect, not hypothetical. TL pins SC by git SHA (`backend/pyproject.toml:19`). QL imports `strategy_core` but does NOT declare it — `engine_decision.py:45-70` imports the engine; QL `pyproject.toml:12-36` (runtime) and `:38-48` (dev) list pandas/numpy/scipy/pydantic/catboost/fastapi but **no `strategy-core`, no git URL**; no `requirements*.txt`, `uv.lock`, `setup.py`, or `.pth`; `tests/conftest.py` does no `sys.path` insertion. QL resolves SC only via an external editable / `PYTHONPATH=src` install — so QL can silently float to a different SC commit than the one TL is pinned to. The registry decision (9.2) and the router (`get_strategy`) are only deterministic if both consumers see the same SC.

- **Option A (RECOMMENDED): pin SC by SHA in BOTH consumers for anything that emits or activates a contract; allow editable installs only for local SC development behind an explicit dev extra.** Make QL declare `strategy-core @ git+...@<sha>` in its `pyproject.toml`, matching TL's pin. Trade-off: every SC bump now requires bumping two pins in lockstep — but that lockstep is exactly the guarantee that the emitter (QL) and the runtime (TL) agree on the registry, the section schemas, and `platform_version`.
- **Option B: both editable.** Lowest friction for a solo developer iterating across all three repos. Trade-off: reproduces today's silent-drift risk and makes "which SC produced this bundle" unanswerable from the repo state — directly at odds with the fail-closed contract philosophy (`test_strategy_contract_nodrift.py`).

**Recommendation: Option A** — declare and SHA-pin SC in QL to match TL; gate editable behind a dev-only extra. This is a prerequisite, not a nicety, for the registry/router design.

---

### 9.7 — (Surfaced by §2) Reconcile the THREE contract copies: repoint TL onto SC vs maintain the local schema

**Context.** §2 (contract evidence) found TL keeps a third hand-written schema copy (`C:/Users/gonza/Documents/Trade-Lab/backend/src/trade_lab/domain/contracts/strategy_contract.py`) that **cannot parse a current v3 QL-emitted contract** under `extra="forbid"`, on three confirmed divergences: (1) `engine_version: str | None = Field(default=None, ...)` (`strategy_contract.py:168`) is OPTIONAL vs REQUIRED in SC (`schema.py:256`); (2) TL `LabelPolicy` (`strategy_contract.py:95-103`) is MISSING `decision_offset_minutes`, which SC has (`schema.py:161`) and the QL emitter emits (`strategy_contract.py:191`); (3) TL has NO `ResearchSessionExperiment` model/field at all, but QL emits the `research_session_experiment` key (emitter `:204`). The §2 design fixes this by deleting the TL hand-written schema and validating via SC's `strategy_core.contract` (envelope + per-plugin `SectionModel.model_validate`).

- **Option A (RECOMMENDED): delete TL's local schema; TL imports the SC envelope loader and validates the section through the plugin's `SectionModel`.** Eliminates the second hand-written schema by construction, so the three divergences cannot recur. Requires TL's `model_registry` (`model_registry.py:26` currently `from trade_lab.domain.contracts import ...`) to repoint onto `strategy_core.contract`. Trade-off: TL gains a hard schema dependency on SC at the contract layer (acceptable given 9.6 Option A's pin).
- **Option B: keep TL's local copy but auto-generate it from SC.** Trade-off: still two schemas, still drift-prone; just moves the drift to the generator.

**Recommendation: Option A**, and bundle the loader-shape unification with it: SC's loader checks engine/platform version BEFORE `model_validate` via an injected `expected_*` hook (`loader.py:28-77`), whereas TL's checks AFTER and hardcodes `strategy_core.ENGINE_VERSION` (`strategy_contract.py:230-242`). Standardize on the SC hook shape.

---

### 9.8 — (Surfaced by §2/§5) Retire TL's local outcome tracker onto the engine's honest-entry path?

**Context.** TL re-implements the MAE-first ladder LOCALLY with a **different entry reference** than the engine: `OutcomeTracker` uses LEVEL-price entry — `entry_points = float(Decimal(prediction.level_price_ticks) * self._tick_size)` (`services/inference/outcome_tracker.py:107`) — whereas the engine's `resolve_honest_outcome` (`decisions/honest_entry.py:76-89`) uses an injected `trade_price_at` callable at `touch.bar_ts_utc + decision_offset_minutes`. This is a known correctness divergence the v3 repoint is meant to retire (MEMORY phase8/phase9; §5). It also intersects archetype 2: the §2 Barrier Protocol must express BOTH today's fixed `tp=15/sl=30` (`outcomes.py:127-136`, `constants.py:139-141`) AND R-relative SL=manipulation-swing/TP=1R (`docs/ifvg-strat.md` §11.2, §11.5, §6.3) — and the tracker is where barrier evaluation lives on the live side.

- **Option A (RECOMMENDED): retire the local tracker; route live outcome resolution through the engine via a `Barrier`-aware path in this refactor.** Single source of truth for label/outcome semantics across batch (QL) and live (TL); makes the live path honest-entry-correct; and is the natural place to introduce the `Barrier {kind: fixed_points | r_relative}` abstraction so archetype 2's R-relative barriers have a home. Trade-off: touches the live hot path and the `prediction.created`/`prediction.resolved` ws frames — but those frames stay `ws.v1`-compatible because the *payload* shape need not change for archetype 1.
- **Option B: defer; keep the local tracker for now.** Lower blast radius this refactor. Trade-off: the level-vs-trade-price divergence persists, and archetype 2's R-relative barrier has nowhere to live, so the Barrier Protocol stays unvalidated on the live side.

**Recommendation: Option A if 9.4 lands the Barrier abstraction; otherwise B as an explicit, time-boxed deferral.** This is genuinely the owner's call on scope appetite — it is correctness-positive but expands the refactor into the inference/transport layer.

---

### 9.9 — (Surfaced by §2) Session-scheme ownership: hardcoded `"asia"`/`"london"` and the ET-vs-CT divergence

**Context.** Two facts collide. (1) The platform's level tracker hardcodes session NAMES: `self._ranges = {"asia": _Range(), "london": _Range()}` (`C:/Users/gonza/Documents/Strategy-Core/src/strategy_core/runtime/levels.py:49`, repeated at `:56,:74,:90`) — a different session set is NOT pure config today. (2) Archetype 2's sessions differ from archetype 1's: `docs/ifvg-strat.md` §6.4 uses Chicago-implied windows (Asia 16:00–01:45, London 02:00–07:00, NY 08:00–14:00) gating *final entry only*, whereas SC v3 is ET (asia 19:00–02:45, london 03:00–08:00, ny 09:00–17:00; `constants.py:170-179`), and SC even carries a non-canonical `TRADE_LAB_CT_SESSION_SCHEME` (`constants.py:185-194`) only to *document* the divergence TL must migrate off.

The fork: does session/level tracking stay platform-owned (with the session set parameterized) or become a per-plugin concern?

- **Option A (RECOMMENDED): keep PDH/PDL/range tracking platform-owned but make the session NAME set data-driven from the `SessionScheme` rather than hardcoded.** Archetype 1's `level_scheme.session_levels` (`schema.py:113-118`) already declares which session levels it wants; the level state should iterate the scheme's sessions instead of literal `"asia"/"london"`. Trade-off: a focused change to `StrategyLevelState` (and its `reset`, which already does NOT clear `_summaries`/`_static_levels` — `levels.py:52-56`), plus a parity re-confirm against `tests/test_runtime_levels.py`.
- **Option B: move session/level tracking into the plugin.** Maximally flexible for archetype 2's different session windows. Trade-off: archetype 1 would have to re-host the v3 availability-guard look-ahead logic (the engine-v3 `available_from` gate, `levels.py:102-114`) that was hard-won (MEMORY: levels-rth-lookahead-rootcause), risking regression of the gate that fixed the 71%-look-ahead bug.

**Recommendation: Option A** — parameterize the session set, keep the availability-guard machinery platform-owned. Separately, the owner must ratify that archetype 2's Chicago windows are migrated onto an ET `SessionScheme` (consistent with the `TRADE_LAB_CT_SESSION_SCHEME`-is-only-for-documentation stance), so both archetypes share one timezone convention rather than reintroducing the CT/ET split.

---

### 9.10 — (Surfaced by §2) Quote handling: does the platform start feeding Quotes to plugins?

**Context.** Today quotes are nearly inert: `_process_quote` (`state.py:256-260`) only updates `_last_quote`/`_last_event_ts_utc`/feed status — quotes do NOT feed candles or levels, consistent with `CandleEngine.process_trade` accepting `Trade` only. But one current feature already consumes quotes: `app_max_spread(quotes, tick_size)` (`decisions/features.py:206`) is the lone feature reading `Quote`s. The §2 `PlatformContext` exposes `trade_price_at`/`session_at`/`closed_bars` but the evidence does not show a quote accessor.

- **Option A (RECOMMENDED): keep quotes platform-buffered (as today) and expose a `quotes_in_window(...)` accessor on `PlatformContext` for plugins/feature specs that need them.** Preserves the current trade-driven candle/level invariant (and its parity gates) while still serving `app_max_spread`. Trade-off: one more `PlatformContext` method to specify; must define the retention window so the buffer is bounded (cf. the existing `recent_closed_bar_limit`).
- **Option B: leave quotes inert, plugins never see them.** Simplest. Trade-off: `app_max_spread` (a current shipped feature) loses its data source under the plugin split — a silent regression.

**Recommendation: Option A.** Small surface addition that keeps an existing feature working; the owner should confirm the buffer window so retention is explicit, not unbounded.