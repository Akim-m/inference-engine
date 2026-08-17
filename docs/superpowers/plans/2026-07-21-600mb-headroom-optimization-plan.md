# 600 MB Headroom Optimization Plan (VRAM + RAM)

**Date:** 2026-07-21 · **Branch:** vllm-fp8-inference · **Executor:** Opus agent
**Goal:** ≥600 MiB free in BOTH system RAM and GPU VRAM **at all times** (incl. transient
host spikes), while using as much of each resource as is *useful*. Serial service is
fixed: `--max-num-seqs 1`, `WORKER_REPLICAS=1` — do not change.

**Restart script (reusable, already tested):**
`/tmp/claude-0/-home-akim-Coding-troke/d884959b-26e5-41d4-89c8-9d78381fac7d/scratchpad/restart_vllm.sh <util> <max_model_len> <max_num_seqs>`
— pkills old vLLM, relaunches with documented env (HF_HUB_OFFLINE=1 etc.), updates
`logs/pids.txt`, waits for :8001, prints KV size + nvidia-smi. On failure prints
DIED/TIMEOUT + log tail and exits 2/1.

---

## 0. The core tension, resolved

- **VRAM model (empirical, this session):** GPU total 8188 MiB; nvidia-smi shows a fixed
  ~231 MiB driver reserve, so `free ≈ 7957 − used`. Used tracks util:
  `used ≈ util × 8159` (fits 0.80→6510 and 0.85/4096/1→6935; the 0.85/2048/4 point is
  ~170 MiB off, so treat the model as ±150–200 MiB and **verify empirically**).
  KV cost ≈ **0.136 MiB/token** (measured 0.80→0.85 delta: 2,974 tokens per 409 MiB;
  matches Gemma3-4B arch: 34 layers × 4 KV heads × 256 head-dim × 2 B × K&V = 136 KiB).
- **Spike evidence (HANDOVER.md ~L128–135):** at util 0.85 with only ~800 MiB slack, an
  invisible Windows-host VRAM spike exhausted it → `dxgkio_make_resident: -12` ENOMEM →
  "CUDA error: unknown error", killing vLLM. **Observed spike class: ≥800 MiB.**
- **Key structural fact:** with `--max-num-seqs 1`, KV tokens beyond `max-model-len` can
  NEVER be used (one sequence, prefix caching off). And the app hard-caps request size
  server-side: chat history ≤2800 chars (`config.py: chat_memory_char_budget`),
  question ≤500 chars (`app/schemas.py`), output ≤512 tokens
  (`config.py: max_output_tokens`), 1 image ≈ 256 tokens. Worst-case request ≈
  **2,200–2,400 tokens** → `max-model-len 4096` already gives ~1.7× headroom; a bigger
  context is *unusable* by this app.
- **Therefore:** "use as much as is useful" does NOT mean max util. Reserved-but-idle KV
  does nothing and raises crash risk; free VRAM is the only spike absorber. The true
  optimum is a **lean** config: KV sized to `max-model-len 4096` + margin, and the rest
  left free so the 600 MiB floor survives an 800 MiB-class spike. Steady-state ~750–850
  free (util ~0.88) would honor the floor only against ≤150–250 MiB spikes — the
  documented spike would breach it and could reproduce the exact ENOMEM crash.

## 1. Recommended target config (PRIMARY)

```
--gpu-memory-utilization 0.78  --max-model-len 4096  --max-num-seqs 1
```

**Predicted:** used ≈ 6,360 MiB → **free ≈ 1,590 MiB**; KV pool ≈ **5,260 tokens**
(≥4,096 needed to start, ~1,160 spare tokens against model error).
**Spike math:** 1,590 − 800 (documented spike class) = **790 ≥ 600** → the floor holds
even during a crash-class host spike. Only ~160 MiB (~1,160 idle KV tokens) is
"wasted" vs. a perfectly-tight fit — cheap insurance against the ±150–200 MiB model error.
**Optional squeeze:** if measured KV at 0.78 comes in ≥5,100 tokens (model confirmed),
one step to **0.77** (predicted free ≈ 1,675, KV ≈ 4,660) is allowed. Never accept
KV < 4,600 tokens (block rounding + margin over max-model-len); at KV < 4,096 vLLM
refuses to start anyway ("max seq len is larger than KV cache" error).

**Alternative A — max-context (documented, not recommended):** util **0.88**,
predicted free ≈ 775 (band 750–850), KV ≈ 11,280 tokens → then set
`--max-model-len 11264` so the pool is fully usable. Buys a context the app's own
caps can never fill, and leaves only ~150–250 MiB of spike absorber above the floor —
a documented-class spike breaches 600 and can ENOMEM-kill vLLM.

**Alternative B — aggressive "exactly 600 free" (operator's explicit choice only):**
util **0.90**, predicted free ≈ 615, KV ≈ 12,480 → `--max-model-len 12288`. Violates
"at all times" under essentially any host spike. Do not deploy without the operator
explicitly accepting crash risk.

## 2. Iterative tune-and-verify procedure (PRIMARY path)

Execution gotchas (real, hit this session):
- Foreground `sleep` is **blocked** in this shell. The restart script sleeps internally,
  so **run it with `run_in_background: true`** and read its output when it finishes
  (it ends with `READY pid=…` + KV line + nvidia-smi, or `DIED`/`TIMEOUT` + log tail).
  Any ad-hoc wait loop must also be backgrounded.
- Never `pkill -f "worker.start"` (self-matches and kills the shell). Use
  `pkill -9 -f 'worker[.]start'`. Worker restart is NOT needed for vLLM tuning; if you
  must relaunch it:
  `cd /home/akim/Coding/troke && setsid nohup env WORKER_REPLICAS=1 .venv/bin/python -m worker.start > logs/worker.log 2>&1 < /dev/null &`

Steps:

1. **Pre-check queue is idle** (avoid failing a live job mid-restart):
   ```bash
   redis-cli llen rq:queue:troke-jobs   # want 0
   ```
2. **Restart at target util** (background run; ~2–4 min):
   ```bash
   bash /tmp/claude-0/-home-akim-Coding-troke/d884959b-26e5-41d4-89c8-9d78381fac7d/scratchpad/restart_vllm.sh 0.78 4096 1
   ```
3. **Read the two numbers that matter:**
   ```bash
   nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
   grep "GPU KV cache size" /home/akim/Coding/troke/logs/vllm.log | tail -1
   curl -s -o /dev/null -w '%{http_code}' localhost:8001/v1/models   # want 200
   ```
4. **Adjust ±0.01 and re-run step 2 until free lands in band:**
   - Target band (primary): **free 1,450–1,700 MiB** and **KV ≥ 4,600 tokens**.
   - Script prints `DIED` with "max seq len (4096) is larger than the maximum number of
     tokens that can be stored in KV cache" → util **+0.01**, retry.
   - free < 1,450 → util **−0.01**. free > 1,700 AND KV ≥ 5,100 → optionally **−0.01**
     (floor: KV ≥ 4,600). Expect convergence in ≤3 restarts.
5. **max-model-len:** stays **4096** on the primary path (already ≈ useful KV capacity —
   no second restart needed). *Alternative A only:* after free lands in 750–850 at util
   0.88, read the KV token count, round DOWN to a multiple of 256, re-run
   `restart_vllm.sh 0.88 <that_value> 1`, and re-verify free ≥ 750 (a max-model-len
   change can shift profiling/activation memory slightly).
6. If at any point vLLM dies with `make_resident`/"CUDA error: unknown error" →
   go to Rollback (§5) immediately.

## 3. RAM (no action needed)

- Measured now: total 11,960 MiB, **available ≈ 6,941 MiB** — the 600 MB RAM floor is
  satisfied with ~11× margin. **`available` is the correct metric**, not the `free`
  column (322–609 MiB): Linux deliberately uses idle RAM as page cache
  (buff/cache ≈ 6,900 MiB) and reclaims it on demand. A low `free` column is healthy,
  not a constraint — do not "fix" it.
- Swap 685/3072 MiB used = cold pages parked at some earlier pressure moment; benign,
  not growing. Leave it.
- **Keep `WORKER_REPLICAS=1`** (serial service; also the RAM lever stays untouched).
  vLLM RSS (~2.4 GiB EngineCore + ~2.2 GiB parent) is unaffected by the util flag
  (util governs VRAM, not RAM). Nothing in this plan increases RAM usage.

## 4. Verification gate (after final restart — ALL must pass)

```bash
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
   # free ≥ 600 hard; expect 1,450–1,700 (primary)
free -m                                        # 'available' ≥ 600 (expect ~6,900)
grep "GPU KV cache size" /home/akim/Coding/troke/logs/vllm.log | tail -1   # ≥ 4,600 tokens
curl -s -o /dev/null -w '%{http_code}' localhost:8001/v1/models            # 200
curl -s -o /dev/null -w '%{http_code}' localhost:8000/chat                 # 200
tail -5 /home/akim/Coding/troke/logs/worker.log   # shows Listening on troke-jobs (worker untouched)
```

**End-to-end smoke (mandatory):** submit one real /chat query and confirm a full
request (history injection + 512-token generation) completes without OOM, and that
free VRAM stays ≥600 *during* generation:

```bash
curl -s -X POST localhost:8000/chat/api/query -H 'Content-Type: application/json' \
  -d '{"question":"What are common radiographic signs of pneumonia?"}'
# → {"job_id": "..."} ; while it runs:
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader   # free ≥ 600 mid-inference
# poll (re-run a few times; no sleep loops in foreground):
curl -s localhost:8000/chat/api/jobs/<job_id>    # → status finished, non-null raw
```

## 5. Rollback

Known-safe hardened fallback (the post-incident config):
```bash
bash /tmp/claude-0/-home-akim-Coding-troke/d884959b-26e5-41d4-89c8-9d78381fac7d/scratchpad/restart_vllm.sh 0.80 2048 1
```
Or return to the current live config: `restart_vllm.sh 0.85 4096 1`.
Trigger rollback on: ENOMEM/`make_resident`/"CUDA error: unknown error", repeated load
failures, or free VRAM observed < 600 at the final config.

## 6. Docs to update IF the config sticks (edit, do NOT commit — developer commits)

1. **`CLAUDE.md`** — the `vllm serve` command block: new
   `--gpu-memory-utilization 0.78 --max-model-len 4096 --max-num-seqs 1`; replace the
   0.80-rationale comment with the new one (serial service; KV sized to the 4096
   usable context; ~1.6 GiB slack so the 600 MiB floor survives ~800 MiB host spikes).
2. **`HANDOVER.md`** — the restart command (~L105–110) and a short tuning note appended
   to the VRAM-incident section (~L128–135): new operating point, measured free, and
   the spike-margin reasoning (steady-state free must exceed floor + observed spike).
3. **`.env.example`** (~L23–27) — `GPU_MEMORY_UTILIZATION=0.78`, `MAX_MODEL_LEN=4096`,
   `MAX_NUM_SEQS=1`; add `WORKER_REPLICAS=1` (documents the serial default; matches
   `config.py: worker_replicas`).
4. Leave everything uncommitted per repo convention.
