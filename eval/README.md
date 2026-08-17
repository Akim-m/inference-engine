# eval — accuracy-regression harness

Freezes troke's current output on fixed inputs and fails on drift of the clinical
**decision** fields. The seatbelt for every speed/scale/department change.
See `docs/superpowers/specs/2026-06-24-accuracy-harness-design.md`.

## Run

The full troke stack (API + worker + vLLM) must be up. Then:

```bash
export TROKE_API_KEY=<an eval key>          # mint via POST /v1/admin/keys
export TROKE_BASE_URL=http://127.0.0.1:8000 # optional, this is the default

# first time / after a deliberate, reviewed change to expected output:
python3 eval/run.py --bless

# the gate (exit 0 = clean, exit 1 = a hard decision-field regression):
python3 eval/run.py
```

## What fails vs flags

- **HARD fail (exit 1):** `severity` / enum `confidence` drift, a parse regression
  (`structured` was non-null in baseline, null now), or a status change.
- **soft flag (exit 0):** free-text wording drift (difflib < 0.85), dermatology
  float-confidence beyond ±0.10. Expected when batching perturbs wording; review,
  don't block.

## Cases

- `cases/queries.json` — text/query cases per domain (Phase 1, no external data).
- `cases/images.json` + `cases/images/<domain>/…` — image fixtures (Phase 2, optional;
  add files then re-`--bless`).

## Workflow around a change

```bash
python3 eval/run.py            # confirm green on current baseline
# ... make the change (e.g. turn on multi-worker batching) ...
python3 eval/run.py            # must stay green on decision fields
```
