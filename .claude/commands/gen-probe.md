---
description: >-
  Authenticated, timed generate_page call via ~/.hf_token (owner PRO quota — the only path
  that actually runs; anonymous quota=0). Prints elapsed + output URLs; on failure auto-pulls
  /hf-logs tail. USE WHEN proving a fix on the live Space works end-to-end.
argument-hint: "--text TEXT [--image-desc DESC] [--lang hebrew|english]"
---

# /gen-probe — authenticated, timed live generation

Calls `generate_page` on the live HF Space with the **owner token** (PRO quota). This is the
explicit GPU path — do not run casually. Use it to prove a geometry or pipeline fix actually
works on the deployed Space, not as a spot-check (use `/space-probe` for that).

**GPU rule:** anonymous quota = 0, so `/verify-generate --gpu` is useless. This command is the
correct way to run a real generation test. Still — don't burn it just to see if it works;
confirm with `/stl-bench` offline first.

**$ARGUMENTS** = `--text TEXT [--image-desc DESC] [--lang hebrew|english]`

## Steps

**Step 1 — read token (never print)**
```bash
T=$(cat ~/.hf_token 2>/dev/null) || { echo "no ~/.hf_token — abort"; exit 1; }
```

**Step 2 — submit generation (authenticated)**
```bash
ROOT="https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space"
TEXT="${ARG_TEXT:-שלום}"
DESC="${ARG_IMAGE_DESC:-a simple flower}"
LANG="${ARG_LANG:-hebrew}"

# engine-2.0 /generate_page: [text, variations, image_desc, object_class, language]
EVENT=$(curl -sf -X POST "$ROOT/gradio_api/call/generate_page" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $T" \
  -d "{\"data\":[\"$TEXT\", {}, \"$DESC\", \"flower\", \"$LANG\"]}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['event_id'])")
echo "Submitted — event_id: $EVENT"
START=$(date +%s)
```

**Step 3 — stream result with wall-clock timing**
```python
import sys, json, time

lines = sys.stdin.read().splitlines()
elapsed = int(time.time()) - int(sys.argv[1])   # START passed as arg

for i, line in enumerate(lines):
    if line == "event: complete":
        raw = lines[i+1] if i+1 < len(lines) else ""
        try:
            data = json.loads(raw.removeprefix("data: "))
            print(f"PASS ({elapsed}s) — {len(data)} output(s)")
            for j, item in enumerate(data):
                url = item.get("url") if isinstance(item, dict) else item
                print(f"  output[{j}]: {str(url)[:120]}")
        except Exception as e:
            print(f"PASS-ish ({elapsed}s) — complete but bad JSON: {raw[:100]} | {e}")
        sys.exit(0)
    if line == "event: error":
        err = lines[i+1] if i+1 < len(lines) else "?"
        print(f"FAIL ({elapsed}s) — {err[:200]}")
        print("→ auto-pulling /hf-logs run tail…")
        sys.exit(1)

print(f"FAIL ({elapsed}s) — no complete event (timeout or stream ended early)")
sys.exit(1)
```

```bash
curl -sf --max-time 300 "$ROOT/gradio_api/call/generate_page/$EVENT" \
  | python3 stream_result.py $START
```

**Step 4 — on FAIL: auto-pull log tail**

If Step 3 exits non-zero, immediately run `/hf-logs run` to surface the traceback.
Do not ask first — the log window closes fast after a crash.

## Expected timing

| Phase | Normal |
|---|---|
| Cold start (model load) | 60–120 s first call |
| Warm (model cached) | 20–60 s |
| > 5 min | ZeroGPU timeout or geometry hang (boolean union?) |

PASS confirms: auth path works, SSE delivery intact, geometry pipeline produces output.
Output URLs are temporary HF-hosted file links (expire after ~1 h).
