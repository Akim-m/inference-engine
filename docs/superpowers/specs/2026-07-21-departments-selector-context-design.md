# Departments + chat selector + bigger context — design

Date: 2026-07-21 · Branch: `vllm-fp8-inference` · Status: approved

## Scope (three parts)

### A. Three new departments (→ 13 total): cardiology, hematology, rheumatology
Follow the documented domain recipe (TDD). Analyze schemas mirror the existing
`FINDING / AFFECTED_* / SEVERITY / CONFIDENCE` style; query uses the shared
`ANSWER / CONFIDENCE` format (shared `parse_query`).

| Domain | Analyze fields → parsed keys |
|---|---|
| cardiology | `FINDING`, `AFFECTED_STRUCTURE`, `SEVERITY`, `CONFIDENCE` |
| hematology | `FINDING`, `CELL_LINE`, `SEVERITY`, `CONFIDENCE` |
| rheumatology | `FINDING`, `AFFECTED_JOINT`, `SEVERITY`, `CONFIDENCE` |

Touch points: `worker/prompts.py` (`_ANALYZE`+`_QUERY`), `worker/inference.py`
(`parse_*` + regex + `_ANALYZE_PARSERS`), `app/main.py` (`DOMAINS`), new
`tests/test_routes_{cardiology,hematology,rheumatology}.py`, `tests/test_prompts.py`,
`tests/test_inference.py`, docs.

### B. Chat department selector (per-message dropdown, default General)
- Extract `DOMAINS` to `app/domains.py` (single source of truth; avoids a circular
  import when `chat.py` needs the list). `app/main.py` imports it.
- `GET /chat/api/domains` → the domain list for the dropdown.
- `app/routes/chat.py`: `chat_analyze`/`chat_query` take optional `domain`
  (form field / JSON), validated against `DOMAINS`, **default `general`** on
  missing/invalid (never error). Replaces the hardcoded `_CHAT_DOMAIN`.
- `app/static/chat.html`: dropdown in the composer (default General), populated from
  `/chat/api/domains`, sent with every request. Memory is domain-agnostic text, so a
  mid-conversation switch just changes the next message's specialty; history carries.

### C. Bigger context
- `config.py`: `chat_memory_char_budget` 2800→**8000**, `max_output_tokens` 512→**1024**.
- vLLM `--max-model-len` 4096→**6144** (restart).
- Budget: worst request ≈ 2,000 tok history (8000 chars) + 120 system + 256 image +
  125 question ≈ 2,500 in + 1,024 out ≈ 3,524 total < 6144 < 9,472-token KV pool at
  util 0.85 (1.54× margin). Fits.

## Method
Strict TDD (red→green per step), order A→B→C. After code: one coordinated restart —
API + worker (new code/config) and vLLM (new max-model-len). Then smoke-test a new
department via the selector and confirm a longer answer. Docs (`docs/api.md`,
`README.md`, `CLAUDE.md`) updated same-change. Leave uncommitted (developer commits).

## Notes / decisions
- `max_output_tokens` 1024 only lengthens the free-text "additional context" prose;
  structured parsers read the first labelled lines, so parsing is unaffected.
- Invalid/missing `domain` in the proxy → `general` (graceful, mirrors the
  "never fail on a parse error" convention).
- No new Pydantic `*Structured` schemas required — parsers return dicts into
  `InferenceResult.structured: Optional[dict]` (same as the other 10 domains).
