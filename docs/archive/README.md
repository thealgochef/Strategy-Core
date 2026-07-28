# Archived window artifacts

Per-work-window review deliverables that used to accumulate untracked at the repo
root. Archived here (committed, filenames unchanged) in the 2026-07-28 housekeeping
window so the evidence cited by `docs/PLATFORM_REFACTOR_PROGRESS.md` survives and
the root stays clean. Where a PROGRESS/DECISIONS entry says a file lives "at the SC
root", read `docs/archive/windows/<same filename>`.

## windows/

- `*_SC_DIFF.txt` — per-window `git diff`/`git log -p` captures exported for owner
  review (D1A→TIMEBAR-FIX). Reproducible from git history; retained because the
  PROGRESS ledger cites many of them as close-out evidence. `WARMFIX_SC_DIFF.txt`
  was recovered from the Trade-Lab repo root (it was produced there during the
  WARM-FIX window), resolving the previously dangling PROGRESS citation.
- `*_GREENLIGHT_REPORT.txt` — push/pin/CI witness records for each window close
  (SEED, WARMFIX, REPORT, EXEC, COCKPIT, COCKPITFIX, PROPSIM, PRESETS, INGEST).
- `DOCSYNC_REPORT.txt` / `TOOLPIN_REPORT.txt` — the paired incident record for the
  ruff 0.16 cold-install red and the `ruff>=0.15,<0.16` ceiling now in
  `pyproject.toml`.
- `ENVFIX_REPORT.txt` — editable-install fix closing the two READER_PIN_RECON risks.
- `ARCH_STATE_RECON.md` — three-repo architecture handoff snapshot (state @ 9d49353);
  supersedes `STATE_RESYNC.md` (2026-07-03 snapshot, kept for the record).
- `b2_context.md` — Phase-B2 design-review bundle. Its header says "DISPOSABLE — do
  not commit", but PROGRESS:129 and Quant-Lab's TIME_BAR_RECON cite it by line
  number, so it is retained as evidence. Line numbers cited elsewhere refer to this
  file's unchanged content.
- `scratch_w3a_reader_proof.py` + `W3A_READER_PROOF.log` — the W3A-READER
  vectorization identity proof (cited by PROGRESS:1475 and docs/DECISIONS.md:132).

## Deleted (not archived) in the same window

Unreferenced raw run output: the four `W3B_0212` debug logs/outs (~76 MB) and their
two uncited scratch scripts, three `_ingest_sc_suite*.out` pytest captures,
`route_seam_report.json` (regenerable by `scripts/route_seam_check.py`), and
`algo-dev.md` (a stray pasted prompt). Rationale: raw logs and regenerable output
carry no citation anywhere; reports/recons/diffs do, and were archived instead.
