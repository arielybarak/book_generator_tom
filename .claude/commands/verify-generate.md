---
description: >-
  Confirm TOM's Space after a fix — CPU-only by default (ping_assets, zero GPU).
  --gpu for a real generate_page. USE WHEN checking a fix without burning ZeroGPU.
argument-hint: "[--gpu]"
---

Verify the Space is working. **Default = CPU only (no GPU quota used).**  
Pass `--gpu` only when you need to confirm an actual generation works.

GPU rule: **never call `generate_page` just to test**; use `ping_assets`/`slow_ping`
for transport confidence. The `--gpu` flag exists for the rare case where you've
already confirmed transport is fine and need to prove the full pipeline works.

---

## Step 1 — Wake check (always)

```bash
ROOT=https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space
STATUS=$(curl -sf "$ROOT/config" -o /dev/null -w "%{http_code}")
echo "Wake check: HTTP $STATUS"
```

If not `200`: Space is sleeping. Stop — the checks below will all fail.

---

## Step 2a — CPU transport (default, no --gpu)

Run `ping_assets` (instant CPU, mirrors the REST contract of `generate_page`):

```bash
ROOT=https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space

EVENT=$(curl -sf -X POST "$ROOT/gradio_api/call/ping_assets" \
  -H "Content-Type: application/json" \
  -d '{"data":[]}' | python3 -c "import sys,json; print(json.load(sys.stdin)['event_id'])")
echo "Submitted — event_id: $EVENT"

curl -sf "$ROOT/gradio_api/call/ping_assets/$EVENT" | python3 -c "
import sys
lines = sys.stdin.read().splitlines()
for i,line in enumerate(lines):
    if line == 'event: complete':
        print('PASS — ping_assets complete')
        break
    if line == 'event: error':
        print('FAIL — ping_assets error:', lines[i+1] if i+1 < len(lines) else '?')
        break
else:
    print('FAIL — no complete event')
"
```

PASS here means: Space awake, REST routing intact, SSE delivery works, CPU path up.

Optionally also run `slow_ping` (CPU, 22 s) to verify a longer-lived SSE connection
doesn't drop prematurely (relevant after network/proxy changes):

```bash
EVENT=$(curl -sf -X POST "$ROOT/gradio_api/call/slow_ping" \
  -H "Content-Type: application/json" \
  -d '{"data":[]}' | python3 -c "import sys,json; print(json.load(sys.stdin)['event_id'])")
curl -sf --max-time 60 "$ROOT/gradio_api/call/slow_ping/$EVENT" | tail -5
```

---

## Step 2b — Full generation (only with --gpu flag)

**Only run this if $ARGUMENTS contains `--gpu`.**

⚠ This calls `generate_page` and consumes ZeroGPU quota. Keep `duration=60` on the
Space (`@spaces.GPU(duration=60)`); anonymous callers have a low cap and a higher
duration breaks on the live site even if it works when tested authenticated.

```bash
ROOT=https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space

# Minimal valid inputs: one short Hebrew word, no variations, simple prompt
EVENT=$(curl -sf -X POST "$ROOT/gradio_api/call/generate_page" \
  -H "Content-Type: application/json" \
  -d '{"data":["שלום", {}, "a simple flower", "flower"]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['event_id'])")
echo "generate_page submitted — event_id: $EVENT"

# Stream result — may take 1–3 minutes with cold model
curl -sf --max-time 300 "$ROOT/gradio_api/call/generate_page/$EVENT" | python3 -c "
import sys, json
lines = sys.stdin.read().splitlines()
for i, line in enumerate(lines):
    if line == 'event: complete':
        raw = lines[i+1] if i+1 < len(lines) else ''
        try:
            data = json.loads(raw.removeprefix('data: '))
            print('PASS — got', len(data), 'output(s)')
            for j, item in enumerate(data):
                url = item.get('url') if isinstance(item, dict) else item
                print(f'  output[{j}]:', str(url)[:100])
        except Exception as e:
            print('PASS-ish — complete but bad JSON:', raw[:120], '|', e)
        break
    if line == 'event: error':
        print('FAIL:', lines[i+1] if i+1 < len(lines) else '?')
        break
else:
    print('FAIL — no complete event (timeout or stream ended early)')
"
```

FAIL here → run `/hf-logs run` immediately to see the real Python traceback.

---

## Summary

Report: wake status + Step 2a PASS/FAIL + (if `--gpu` was passed) Step 2b PASS/FAIL.
One sentence on what was verified. If anything failed, name the next diagnostic step.
