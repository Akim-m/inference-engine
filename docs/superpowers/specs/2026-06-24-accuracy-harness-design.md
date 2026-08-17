# Accuracy-Regression Harness — Design

**Date:** 2026-06-24
**Status:** approved (inline), Phase 1 implemented
**Why:** "Never lose accuracy" is unverifiable today — there is no eval, baseline, or
regression gate (only the regex *parser* is unit-tested). This harness makes accuracy
a measured, enforced property so that every later change (multi-worker batching,
fp8 tuning, new departments, multi-user) is provably accuracy-safe.

## Approach: regression baseline (frozen snapshot)

Freeze the current model's output on a fixed set of inputs as the reference
(`baseline.json`). Any future change that drifts the **clinical decision fields**
fails the gate; free-text wording drift is soft-flagged (temp=0 batching can perturb
wording without changing the decision). This protects *future* changes; it does not
judge absolute clinical correctness (a separate, data-hungry problem — out of scope).

## Layout (`eval/`, not `tests/` — hits the live stack, slow)

- `eval/cases/queries.json` — `{domain: [question, ...]}` (Phase 1, no external data)
- `eval/cases/images.json` + `eval/cases/images/<domain>/…` — image fixtures (Phase 2, optional)
- `eval/baseline.json` — blessed reference outputs, committed
- `eval/run.py` — run cases end-to-end against the live API; `--bless` to capture, else gate
- `eval/README.md` — usage

## Scoring (per case)

| Field type | Rule | On drift |
|---|---|---|
| `status` (completed/failed) | exact | hard fail |
| `structured` null-now-but-not-in-baseline | — | hard fail (parser regression) |
| Categorical decision (`severity`, enum `confidence`) | case-insensitive exact | **hard fail** |
| Float `confidence` (dermatology) | within ±0.10 | soft flag |
| Free text (`findings`, `impression`, `answer`, `condition`, …) | difflib ratio ≥ 0.85 | soft flag |

`run.py` exits non-zero iff any **hard fail** → usable as a pre/post-change gate.

## Run model

End-to-end against `TROKE_BASE_URL` (default `http://127.0.0.1:8000`) with a dedicated
eval API key, **one case in flight at a time** so the baseline itself is stable.
Stdlib only (urllib, difflib, json) — no added RAM/deps.

## Phasing

- **Phase 1 (now):** text/query baselines for all 5 domains. Zero external data.
- **Phase 2 (deferred):** ~1–3 fixed images per domain. Source: fetch openly-licensed
  public-domain images if clean, else wait for user-provided fixtures.

## Relationship to scalability

This is the gate for the scalability work: before turning on multi-worker batching we
`--bless` the baseline; after, we re-run — categorical decision fields must hold (hard),
proving batching/concurrency didn't move the clinical output.

## Out of scope (YAGNI)

Absolute clinical correctness, LLM-judge grading, embedding similarity (RAM), CI wiring.
