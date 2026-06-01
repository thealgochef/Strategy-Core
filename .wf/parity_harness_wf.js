export const meta = {
  name: 'strategy-core-parity-4a',
  description: 'Phase 4a parity gate: prove strategy-core reproduces the canonical research pipeline on real data. Additive only; no edits to either repo.',
  phases: [
    { title: 'Pin', detail: 'resolve open items vs canonical (read-only)' },
    { title: 'Harness', detail: 'build + run the standalone parity harness on real days' },
    { title: 'Audit', detail: 'adversarial re-derivation, additive-only proof, candle benchmark' },
  ],
}

const ROOT = 'C:/Users/gonza/Documents/Strategy-core'
const CQL = 'C:/Users/gonza/Documents/Claude-Quant-Lab'
const CQL_SRC = CQL + '/src'
const TL = 'C:/Users/gonza/Documents/Trade-Lab'
const DATA_DIR = 'C:/Users/gonza/Documents/Trade-Dashboard/data/databento'
const BUILDER = CQL_SRC + '/alpha_lab/agents/data_infra/ml/dashboard_utility_builder.py'
const LABELER = CQL_SRC + '/alpha_lab/agents/data_infra/ml/dashboard_utility_labeling.py'
const TICKSTORE = CQL_SRC + '/alpha_lab/agents/data_infra/tick_store.py'
const APPROACH = CQL_SRC + '/alpha_lab/experiment/features.py'
const DAYS = "['2025-06-02','2025-06-03','2025-06-04','2025-06-05','2025-06-06']"

const ENV = `Environment (verified working): python 3.13, duckdb 1.4.4, numpy, pandas, catboost all installed. strategy-core is pip-installed editable (import strategy_core works). The research package alpha_lab is NOT importable by default — you MUST do \`import sys; sys.path.insert(0, r"${CQL_SRC}")\` BEFORE importing alpha_lab, else a different partial copy shadows it. Run python via Bash with no special cwd needed once sys.path is set inside the script. Bars build fast (~0.5s/day).`

// ── Phase 1: Pin open items ────────────────────────────────────────────────
phase('Pin')

const PIN = {
  type: 'object', additionalProperties: false,
  required: ['item', 'decision', 'engine_matches', 'evidence', 'notes'],
  properties: {
    item: { type: 'string' },
    decision: { type: 'string' },
    engine_matches: { type: 'boolean', description: 'does strategy-core already match canonical for this item' },
    evidence: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['file_line', 'quote'],
      properties: { file_line: { type: 'string' }, quote: { type: 'string' } } } },
    notes: { type: 'string' },
  },
}

const pinTouchTs = `Read-only investigation. Pin the TOUCH TIMESTAMP semantics of the canonical research pipeline.
${ENV}
Question: when the canonical pipeline records a touch event, is the touch timestamp the bar's OPEN time or CLOSE time?
This anchors the 5m interaction and 30m approach feature windows; getting it wrong shifts every window.
Trace it: ${BUILDER} _detect_touches (414-440) records touch["bar_ts"] = the bar's pandas index (bars_et.index).
Those bars come from ${BUILDER} _build_bars_for_date -> store.build_tick_bars. Read ${TICKSTORE} build_tick_bars
(451-540) and report what the bar index timestamp (\`bar_time\`) is: FIRST(ts_event) [open] or LAST(ts_event) [close]?
Then state whether strategy-core's detect_touches (which stamps Touch.bar_ts_utc = bar.close_ts_utc) matches.
Also confirm a streaming consumer can reproduce it without look-ahead (a touch is only known at bar close).
Set item="touch_timestamp", decision to OPEN or CLOSE with the exact bar_time SQL expression, engine_matches accordingly.`

const pinAbsorptionSize = `Read-only investigation. Pin the SIZE semantics of the canonical int_absorption_ratio feature.
${ENV}
Question: int_absorption_ratio sums "volume" at-level vs through-level. What "size" does canonical sum — TRADE size, or
the size column of BOOK events? Trace it: ${BUILDER} _compute_interaction_features (446-538) gets its rows from
store.query_tick_feature_rows then reads ticks["size"] (around line 511-530). Read ${TICKSTORE} query_tick_feature_rows
(230-306): for the has_book (MBP) case, what rows does it return (is there an action='T' trade filter?) and what is the
\`size\` column? Conclude whether canonical absorption sums book-event sizes over book rows (bid>0&ask>0) or trade sizes.
Also note: strategy-core's int_absorption_ratio (post the ratified TRADE-PRICE decision) sums TRADE size over trades, so it
intentionally DIFFERS from canonical here — confirm that and explain why (price-vs-level reference + row population both change).
Set item="absorption_size", decision to the canonical source ("book_event_size" or "trade_size"), engine_matches=false with a note that the divergence is the deliberate trade-price standardization, not a bug.`

const pins = await parallel([
  () => agent(pinTouchTs, { label: 'pin:touch_ts', phase: 'Pin', schema: PIN }),
  () => agent(pinAbsorptionSize, { label: 'pin:absorption_size', phase: 'Pin', schema: PIN }),
])

// ── Phase 2: Build + run harness ───────────────────────────────────────────
phase('Harness')

const HARNESS = {
  type: 'object', additionalProperties: false,
  required: ['ran_ok', 'report_path', 'days_processed', 'stages', 'must_match_all_pass', 'summary'],
  properties: {
    ran_ok: { type: 'boolean' },
    report_path: { type: 'string' },
    harness_path: { type: 'string' },
    days_processed: { type: 'array', items: { type: 'string' } },
    stages: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['stage', 'scope', 'total', 'matched', 'mismatched'],
      properties: {
        stage: { type: 'string' },
        scope: { type: 'string', enum: ['must_match', 'expected_differ'] },
        total: { type: 'integer' },
        matched: { type: 'integer' },
        mismatched: { type: 'integer' },
        divergence_summary: { type: 'string', description: 'for expected_differ stages: distribution of |engine-canonical|' },
        example_mismatch: { type: 'string', description: 'for must_match stages: a concrete day/touch/values example, or empty' },
      } } },
    must_match_all_pass: { type: 'boolean' },
    summary: { type: 'string' },
  },
}

const harnessPrompt = `Build a STANDALONE parity harness that proves strategy-core reproduces the canonical research pipeline on REAL data, then run it. This is a money-path gate — be rigorous and report mismatches HONESTLY (never hide or fudge to make must-match pass).

${ENV}

HARD CONSTRAINT: additive only. Do NOT edit, create, or delete ANY file under ${CQL} or ${TL}. Only write under ${ROOT}/validation/. You import the research code read-only.

WRITE: ${ROOT}/validation/parity_harness.py  (and it writes its report to ${ROOT}/validation/_out/PARITY_REPORT.md).

DAYS (contiguous, so prior-day levels accumulate): ${DAYS}
DATA_DIR = r"${DATA_DIR}", symbol "NQ".
PRODUCTION CONFIG (the deployed model's params): MLPipelineConfig(training_mode='dashboard_utility', instrument='NQ',
  tick_size=0.25, dashboard_utility=dict(bar_type='147t', interaction_window_minutes=5, approach_window_minutes=30,
  include_approach_features=True, tp_points=15.0, sl_points=30.0, trap_mfe_min=5.0, level_proximity_pts=0.5)).

KEY INSIGHT that makes this clean: the canonical pipeline runs ENTIRELY on BOOK-MID bars
(${TICKSTORE} build_tick_bars:504 price=(bid_px_00+ask_px_00)/2.0; bar timestamp = LAST(ts_event) = CLOSE time, :524).
Book mids are exact multiples of 0.125 (verified: a high of 21459.125). So you can represent canonical book-mid bars
LOSSLESSLY as strategy_core.Bar with tick_size=0.125: low_ticks=round(low/0.125), high_ticks=round(high/0.125). Feeding
IDENTICAL bars to both pipelines means any zones/touches/labels difference is a PORT BUG, while feature differences are
the deliberate trade-price change.

OPEN-ITEM RESOLUTIONS (already pinned — apply them): touch timestamp = bar CLOSE (LAST(ts_event)); strategy-core's
detect_touches uses bar.close_ts_utc which matches. Absorption size: canonical = book-event size over book rows; the
engine (trade-price) uses trade size — that is the deliberate divergence, do NOT try to make it match.

Canonical functions to import (read ${BUILDER}, ${LABELER}, ${APPROACH} for exact signatures/behavior):
  from alpha_lab.agents.data_infra.ml import dashboard_utility_builder as B
  from alpha_lab.agents.data_infra.ml import dashboard_utility_labeling as L
  from alpha_lab.agents.data_infra.ml.config import MLPipelineConfig
  B._build_bars_for_date(data_dir, 'NQ', date_str, u) -> OHLCV df ; B._ensure_et_index(df)
  B._compute_levels_for_date(bars_et, date_str, prev_ny_hl, prev_asia_hl, prev_london_hl) -> list[dict{name,price,side}]
  B._get_session_hl_for_date(...) to carry prev-day session H/L across days (mirror build_utility_dataset loop, builder:84-126)
  B._build_zones(levels) -> list[dict{representative_price,names,side,touched}]   (NOTE: _detect_touches MUTATES zone['touched']; build FRESH zones for detection vs comparison)
  B._detect_touches(bars_et, zones) -> list[dict{bar_ts,representative_price,direction,level_type,date}]
  B._compute_interaction_features(touch, data_dir, 'NQ', u) -> dict{int_time_beyond_level,int_time_within_2pts,int_absorption_ratio} or None (<5 ticks)
  B._compute_approach_features(touch, data_dir, 'NQ', u) -> dict incl app_large_trade_vol_pct, app_avg_trade_size, app_max_spread
  L.label_touch_event(touch, forward_bars, u) -> dict{label,label_encoded,max_mfe,max_mae,...}

Engine API: strategy_core.{build_zones, detect_touches, classify_session, resolve_outcome, int_time_beyond_level,
  int_time_within_2pts, int_absorption_ratio, app_large_trade_vol_pct, app_avg_trade_size, app_max_spread, Level, Bar,
  Side, Direction, make_bar_id, RESEARCH_SESSION_SCHEME, CloseReason}.

PIPELINE per day (carry prev_ny_hl/prev_asia_hl/prev_london_hl across days like build_utility_dataset):
  bars=_build_bars_for_date(...); bars_et=_ensure_et_index(bars); levels=_compute_levels_for_date(bars_et,date,prev...).
  Build engine Bars from bars_et rows: tf=147, tick_size=0.125, trading_day=date.fromisoformat(date_str),
  bar_index=i, close_ts_utc=bars_et.index[i].to_pydatetime() (tz-aware UTC — convert from ET), open_ts_utc=same,
  open/high/low/close_ticks=round(val/0.125), volume=int(row.volume), trade_count=147, is_complete=True, close_reason=COMPLETE.

STAGES — diff and tally (a "match" = exactly equal; floats compared with abs tol 1e-9):
  A. ZONES  [must_match]: _build_zones(levels) vs build_zones(engine Levels). Compare count, representative_price,
     side (HIGH/LOW), names tuple. Per zone.
  B. SESSIONS [must_match]: for every bar timestamp in bars_et.index, compare strategy_core.classify_session(ts_utc).session
     to the canonical session via _slice_session masks (asia: t>=18:00 or t<01:00; london: 01:00<=t<08:00; ny_rth:
     09:30<=t<16:15; else 'none'). ET wall-clock. Tally per-bar matches (sample up to ~5000 bars/day is fine).
  C. TOUCHES [must_match]: _detect_touches(bars_et, fresh canon zones) vs detect_touches(engine Bars, fresh engine zones,
     tick_size=0.125, trading_day=...). Compare count and, per touch in order: close timestamp (instant-equal),
     direction (LONG/SHORT), representative_price, level_type. THIS is the core port-fidelity proof.
  D. LABELS [must_match]: for each canonical touch, canonical forward = bars_et[bars_et.index > touch['bar_ts']];
     rth_cutoff=pd.Timestamp(f"{date} 16:15:00", tz='US/Eastern'); forward=forward[forward.index < rth_cutoff];
     canon=L.label_touch_event(touch, forward, u). Engine: resolve_outcome(entry_points=touch['representative_price'],
     direction=Direction(touch['direction']), forward_bars=engine Bars built from that same forward df (tick_size=0.125),
     tick_size=0.125, tp_points=15, sl_points=30, trap_mfe_min=5). Compare label, label_encoded, round(max_mfe,4),
     round(max_mae,4). Skip touches with empty forward.
  E. INTERACTION FORMULA FIDELITY [must_match]: prove the int_* FORMULA is a faithful port by feeding IDENTICAL inputs.
     For each kept touch (canonical features not None), get the canonical book rows the builder uses:
     create a TickStore(data_dir) (from alpha_lab.agents.data_infra.tick_store import TickStore), register the touch's
     date(s), call store.query_tick_feature_rows('NQ', event_ts_utc, event_ts_utc+5min) -> book rows (ts_event, price=mid, size).
     Build engine Trade objects: Trade(event_ts_utc=row.ts_event(UTC), price_ticks=round(row.price/0.125), size=int(row.size)).
     Compute engine int_time_beyond_level / int_time_within_2pts (level_points=touch rep, direction, tick_size=0.125) and
     int_absorption_ratio over these. Compare to canonical B._compute_interaction_features(touch,...) (same window/source).
     These MUST MATCH (identical inputs + faithful formula) — this isolates formula fidelity from the price-source change.
  F. INTERACTION TRADE-PRICE DIVERGENCE [expected_differ]: now feed real TRADE prints. Query trades for the same [event_ts, +5m)
     window from the day's parquet with the SAME filters canonical uses for its base/trades: front-month (dominant symbol where
     symbol NOT LIKE '%-%', pick by count) AND bid_px_00>0 AND ask_px_00>0 AND action='T'; Trade(price_ticks=round(price/0.25),
     size). Compute engine int_* over trade PRICE (tick_size=0.25). Report the distribution of |engine_trade - canonical_book|
     per feature (mean/median/max). Do NOT assert equality. Do NOT revert the engine to book-mid.
  G. APPROACH FEATURES [must_match for the 3 in the model]: canonical via B._compute_approach_features(touch,...). Engine:
     for the [event_ts-30m, event_ts) window with front-month filter: base = rows bid>0&ask>0; trades = base AND action='T'.
     app_avg_trade_size(trades), app_large_trade_vol_pct(trades) over Trade(size); app_max_spread(quotes) where quotes are the
     base rows as Quote(bid_price_ticks=round(bid_px_00/0.25), ask_price_ticks=round(ask_px_00/0.25)), tick_size=0.25.
     Compare app_large_trade_vol_pct, app_avg_trade_size, app_max_spread to canonical (abs tol 1e-6). (Ref-independent -> must match.)
     If any mismatch, report it honestly with the values — do not hide.

For trade/quote extraction (stages F,G) use a fresh duckdb.connect(':memory:') over the day's parquet
read_parquet(r"${DATA_DIR}/NQ/{date}/mbp10.parquet"); resolve the dominant front-month symbol exactly like
build_tick_bars does (symbol NOT LIKE '%-%', GROUP BY symbol ORDER BY count DESC LIMIT 1). Note the approach window may
cross into the previous calendar day's file — register the previous day's parquet too (canonical does, builder:566-567).

REPORT (${ROOT}/validation/_out/PARITY_REPORT.md): a table of stages with scope/total/matched/mismatched; for every
must_match mismatch, a concrete example (day, touch ts, canonical value, engine value); for expected_differ, the divergence
distribution; the two pinned open-item resolutions; the days processed and total touch count. End with a one-line VERDICT:
"PORT FIDELITY PROVEN" only if every must_match stage is 100% matched, else "MISMATCH — see stage X".

PROCESS: write the harness, run it (\`python ${ROOT}/validation/parity_harness.py\`), debug until it runs cleanly and emits
the report. Iterate on real errors. Then return the structured summary (stages with real counts). must_match_all_pass =
every must_match stage 100%. Report ran_ok=true only if the script completed and wrote the report.`

const harness = await agent(harnessPrompt, { label: 'build+run harness', phase: 'Harness', schema: HARNESS })

// ── Phase 3: Adversarial audit + benchmark ─────────────────────────────────
phase('Audit')

const AUDIT = {
  type: 'object', additionalProperties: false,
  required: ['check', 'pass', 'detail'],
  properties: {
    check: { type: 'string' },
    pass: { type: 'boolean' },
    findings: { type: 'array', items: { type: 'string' } },
    detail: { type: 'string' },
  },
}

const BENCH = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'identical', 'detail'],
  properties: {
    ran: { type: 'boolean' },
    duckdb_seconds: { type: 'number' },
    numpy_seconds: { type: 'number' },
    speed_ratio: { type: 'number', description: 'duckdb_seconds / numpy_seconds (>1 means numpy faster)' },
    bars_compared: { type: 'integer' },
    identical: { type: 'boolean', description: 'do DuckDB book-mid bars and a numpy rebuild agree on count/timestamps' },
    detail: { type: 'string' },
  },
}

const auditReDerive = `Adversarially audit the parity harness's MUST-MATCH claims by INDEPENDENTLY re-deriving one touch from scratch — do not trust the harness code.
${ENV}
Read ${ROOT}/validation/_out/PARITY_REPORT.md and ${ROOT}/validation/parity_harness.py. Pick ONE touch from day 2025-06-03
(or any processed day). WITHOUT reusing the harness's engine-vs-canonical comparison code, independently:
(1) rebuild that day's book-mid bars (B._build_bars_for_date + _ensure_et_index), levels, and zones two ways — via
    canonical B._build_zones and via strategy_core.build_zones — and confirm the zone the touch fired on is identical.
(2) confirm the touch fires at the same bar (closed interval bar_low<=rep<=bar_high) and same close timestamp under both.
(3) recompute the label both ways (L.label_touch_event vs strategy_core.resolve_outcome on the same forward bars) and
    confirm label + mfe/mae agree.
Report pass=true only if your INDEPENDENT re-derivation agrees with the harness's must-match=pass claim. If you find the
harness overstated a match (e.g. it skipped touches, used loose tolerances, or compared the wrong fields), pass=false with specifics.
check="independent_touch_rederivation".`

const auditAdditive = `Verify the parity work was ADDITIVE ONLY — no modification to either production repo — and audit the diff scoping.
${ENV}
(1) Run \`git -C ${CQL} status --porcelain\` and \`git -C ${TL} status --porcelain\`. Compare to a baseline: the harness must
    NOT have created/edited/deleted any tracked or untracked file in either repo. (The repos had pre-existing modifications
    before this task; your job is to confirm the PARITY HARNESS added nothing new there — look for any file under
    alpha_lab/.../ml/ or trade_lab/ that looks like harness output, caches written by the run, etc. Note: the canonical
    builder may write ml_utility_*.parquet CACHE files into the DATA dir (${DATA_DIR}) — that is the research data dir, NOT
    the repo, and is acceptable; flag it but it is not a repo modification.)
(2) Audit the diff SCOPING in ${ROOT}/validation/parity_harness.py: confirm it asserts MUST-MATCH only on zones, sessions,
    touches, labels, interaction-formula-fidelity, and the 3 approach features — and that it does NOT assert equality on the
    trade-price interaction divergence (stage F), and did NOT revert the engine to book-mid to force a pass.
check="additive_only_and_scoping". pass=false if any repo file was modified by the harness or the scoping is wrong.`

const benchPrompt = `Run the optional DuckDB-vs-numpy candle benchmark (spec §7 open decision) — additive, read-only on data.
${ENV}
For 2025-06-03 (NQ): (1) time the canonical DuckDB tick-bar build — B._build_bars_for_date(data_dir,'NQ','2025-06-03',u)
with bar_type='147t' (book-mid path). (2) Build a numpy/pandas equivalent: load the day's front-month book-mid rows
(ts_event, mid=(bid_px_00+ask_px_00)/2, size, filtered bid>0&ask>0 + dominant symbol) into a DataFrame ordered by ts, then
group every 147 rows (rn//147, HAVING count==147) computing first/max/min/last(mid)+sum(size)+last(ts) — i.e. replicate the
DuckDB bars in pandas. Time it. (3) Compare: same bar COUNT, same close timestamps, same OHLC (book mids, exact on 0.125
grid). Report duckdb_seconds, numpy_seconds, speed_ratio, bars_compared, identical (true if count+timestamps+OHLC agree).
This informs whether research can adopt the engine's numpy batch builder or must keep DuckDB as a verified-equivalent fast path.
Do NOT edit either repo. check is implicit; fill the BENCH schema.`

const audit = await parallel([
  () => agent(auditReDerive, { label: 'audit:re-derive', phase: 'Audit', schema: AUDIT }),
  () => agent(auditAdditive, { label: 'audit:additive', phase: 'Audit', schema: AUDIT }),
  () => agent(benchPrompt, { label: 'bench:duckdb-vs-numpy', phase: 'Audit', schema: BENCH }),
])

return { pins, harness, audit }
