#!/usr/bin/env python3
"""troke accuracy-regression harness. Stdlib only.

Runs a fixed set of cases through the LIVE troke API, captures structured+raw output,
and compares against a blessed baseline. Exits non-zero on drift of the clinical
*decision* fields (severity, enum confidence) or a parse regression; soft-flags
free-text wording drift (temp=0 batching can perturb wording, not the decision).

Usage:
  TROKE_API_KEY=<key> python3 eval/run.py --bless    # capture / refresh the baseline
  TROKE_API_KEY=<key> python3 eval/run.py            # gate: check current vs baseline

Env: TROKE_BASE_URL (default http://127.0.0.1:8000), TROKE_API_KEY (required).
"""
import argparse
import difflib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_URL = os.environ.get("TROKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("TROKE_API_KEY", "")

SIM_THRESHOLD = 0.85          # free-text drift soft-flag threshold
FLOAT_TOL = 0.10              # dermatology float-confidence tolerance
HARD_ENUM_FIELDS = {"severity", "confidence"}  # decision fields; confidence may be float (derm)
POLL_EVERY = 3
POLL_MAX = 60                 # ~3 min per case


def _post_json(path, payload):
    req = urllib.request.Request(
        BASE_URL + path, data=json.dumps(payload).encode(), method="POST",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(path):
    req = urllib.request.Request(BASE_URL + path, headers={"X-API-Key": API_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def submit_query(domain, question):
    return _post_json(f"/v1/{domain}/query", {"question": question})["job_id"]


def submit_analyze(domain, image_path, question):
    boundary = "----trokeeval0xC0FFEE"
    p = Path(image_path)
    parts = [
        (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
         f'filename="{p.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        + p.read_bytes() + b"\r\n"
    ]
    if question:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; '
                      f'name="question"\r\n\r\n{question}\r\n').encode())
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        BASE_URL + f"/v1/{domain}/analyze", data=b"".join(parts), method="POST",
        headers={"X-API-Key": API_KEY, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["job_id"]


def poll(job_id):
    for _ in range(POLL_MAX):
        j = _get(f"/v1/jobs/{job_id}")
        if j["status"] in ("completed", "failed"):
            return j
        time.sleep(POLL_EVERY)
    return {"status": "timeout"}


def run_case(case):
    if case["kind"] == "query":
        jid = submit_query(case["domain"], case["question"])
    else:
        jid = submit_analyze(case["domain"], case["image"], case.get("question", ""))
    res = poll(jid)
    out = {"status": res.get("status")}
    if res.get("status") == "completed":
        r = res.get("result") or {}
        out["structured"] = r.get("structured")
        out["raw"] = r.get("raw", "")
    return out


def load_cases():
    cases = []
    queries = json.loads((ROOT / "cases" / "queries.json").read_text())
    for domain, qs in queries.items():
        for i, question in enumerate(qs):
            cases.append({"id": f"query/{domain}/{i}", "kind": "query",
                          "domain": domain, "question": question})
    img_file = ROOT / "cases" / "images.json"
    if img_file.exists():
        for domain, items in json.loads(img_file.read_text()).items():
            for i, it in enumerate(items):
                cases.append({"id": f"analyze/{domain}/{i}", "kind": "analyze", "domain": domain,
                              "image": str(ROOT / "cases" / "images" / it["file"]),
                              "question": it.get("question", "")})
    return cases


def compare(base, cur):
    """Return (hard_fails, soft_flags) — lists of human-readable drift strings."""
    hard, soft = [], []
    if base.get("status") != cur.get("status"):
        return [f"status {base.get('status')} -> {cur.get('status')}"], soft
    bs, cs = base.get("structured"), cur.get("structured")
    if bs is not None and cs is None:
        return ["structured parsed in baseline but is null now (parse regression)"], soft
    if bs is None and cs is None:
        ratio = difflib.SequenceMatcher(None, base.get("raw", ""), cur.get("raw", "")).ratio()
        if ratio < SIM_THRESHOLD:
            soft.append(f"raw drift (sim {ratio:.2f})")
        return hard, soft
    for field, bval in bs.items():
        cval = cs.get(field)
        if cval is None:
            hard.append(f"{field}: present in baseline, missing now")
            continue
        if field == "confidence" and isinstance(bval, (int, float)) and not isinstance(bval, bool):
            try:
                if abs(float(cval) - float(bval)) > FLOAT_TOL:
                    soft.append(f"{field}: {bval} -> {cval}")
            except (TypeError, ValueError):
                hard.append(f"{field}: {bval} -> {cval}")
        elif field in HARD_ENUM_FIELDS:
            if str(cval).strip().lower() != str(bval).strip().lower():
                hard.append(f"{field}: '{bval}' -> '{cval}'")
        else:
            ratio = difflib.SequenceMatcher(None, str(bval), str(cval)).ratio()
            if ratio < SIM_THRESHOLD:
                soft.append(f"{field}: sim {ratio:.2f} ('{str(bval)[:40]}' -> '{str(cval)[:40]}')")
    return hard, soft


def _submit_case(case):
    if case["kind"] == "query":
        return submit_query(case["domain"], case["question"])
    return submit_analyze(case["domain"], case["image"], case.get("question", ""))


def run_concurrent(cases, inflight):
    """Submit `inflight` cases at once so vLLM actually batches them, then poll all
    to terminal. 429-tolerant (the per-key rate/pending limits self-throttle us).
    Proves the clinical output is unchanged when requests are batched vs. serial."""
    subset = cases[:inflight]

    def submit(case):
        for _ in range(15):
            try:
                return case["id"], _submit_case(case)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(3)
                    continue
                raise
        return case["id"], None

    with ThreadPoolExecutor(max_workers=inflight) as ex:
        submitted = dict(ex.map(submit, subset))

    results, pending = {}, {cid: jid for cid, jid in submitted.items() if jid}
    while pending:
        for cid, jid in list(pending.items()):
            try:
                j = _get(f"/v1/jobs/{jid}")
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    continue          # rate-limited this cycle; retry next loop
                raise
            if j["status"] in ("completed", "failed"):
                out = {"status": j["status"]}
                if j["status"] == "completed":
                    r = j.get("result") or {}
                    out["structured"], out["raw"] = r.get("structured"), r.get("raw", "")
                results[cid] = out
                del pending[cid]
                print(f"  {cid}: {out['status']}", flush=True)
        if pending:
            time.sleep(4)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bless", action="store_true", help="capture/refresh the baseline")
    ap.add_argument("--concurrent", action="store_true",
                    help="submit cases concurrently to force vLLM batching (gate only)")
    ap.add_argument("--inflight", type=int, default=8,
                    help="how many cases to submit at once in --concurrent mode")
    args = ap.parse_args()
    if not API_KEY:
        sys.exit("TROKE_API_KEY not set")

    cases = load_cases()
    if args.concurrent and not args.bless:
        n = min(len(cases), args.inflight)
        print(f"running {n} cases CONCURRENTLY (forces vLLM batching) against {BASE_URL} ...", flush=True)
        results = run_concurrent(cases, args.inflight)
    else:
        print(f"running {len(cases)} cases serially against {BASE_URL} ...", flush=True)
        results = {}
        for c in cases:
            results[c["id"]] = run_case(c)
            print(f"  {c['id']}: {results[c['id']].get('status')}", flush=True)

    if args.bless:
        (ROOT / "baseline.json").write_text(json.dumps(results, indent=2, sort_keys=True))
        print(f"\nblessed {len(results)} cases -> eval/baseline.json")
        return

    base_path = ROOT / "baseline.json"
    if not base_path.exists():
        sys.exit("no baseline.json — run with --bless first")
    base = json.loads(base_path.read_text())
    total_hard = total_soft = 0
    for cid, cur in results.items():
        if cid not in base:
            print(f"\n{cid}:\n  soft  NEW case, no baseline (run --bless to add)")
            total_soft += 1
            continue
        hard, soft = compare(base[cid], cur)
        total_hard += len(hard)
        total_soft += len(soft)
        if hard or soft:
            print(f"\n{cid}:")
            for h in hard:
                print(f"  HARD  {h}")
            for s in soft:
                print(f"  soft  {s}")
    print(f"\n=== {total_hard} hard-fail, {total_soft} soft-flag across {len(results)} cases ===")
    sys.exit(1 if total_hard else 0)


if __name__ == "__main__":
    main()
