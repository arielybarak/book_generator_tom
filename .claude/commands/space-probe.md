---
description: >-
  Zero-GPU health check for TOM's HF Space: wake, endpoints, CPU ping_assets,
  CORS from Vercel, file serving. PASS/FAIL per layer. USE when site won't generate.
argument-hint: ""
---

Run a read-only probe against the live Space. **No GPU, no generation.** Each check
is PASS or FAIL; the first FAIL pinpoints the broken layer.

**Constants:**
```
ROOT=https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space
ORIGIN=https://book-generator-tom.vercel.app
```

---

## Check 1 — Wake / config reachable

```bash
ROOT=https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space
curl -sf "$ROOT/config" -o /dev/null -w "HTTP %{http_code}\n"
```

- `HTTP 200` + JSON → PASS (Space awake).
- `HTTP 200` + HTML, `000`, or non-JSON → FAIL (sleeping / rebuilding). If FAIL here, remaining checks will also fail; wait for the Space to wake.

---

## Check 2 — Named endpoints present

```bash
curl -sf "$ROOT/gradio_api/info" | python3 -c "
import sys, json
d = json.load(sys.stdin)
eps = list(d.get('named_endpoints', {}).keys())
print('Endpoints:', eps)
want = {'generate_page', 'ping_assets', 'slow_ping'}
got = {e.lstrip('/') for e in eps}   # Gradio lists names with a leading '/'
missing = want - got
print('PASS' if not missing else f'FAIL: missing {missing}')
"
```

Expect at minimum: `generate_page`, `ping_assets`, `slow_ping`.

---

## Check 3 — CPU round-trip via ping_assets (zero GPU)

Use the 2-step REST call (see [[zerogpu-web-bridge]] — never `@gradio/client`):

```bash
ROOT=https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space

EVENT=$(curl -sf -X POST "$ROOT/gradio_api/call/ping_assets" \
  -H "Content-Type: application/json" \
  -d '{"data":[]}' | python3 -c "import sys,json; print(json.load(sys.stdin)['event_id'])")

echo "event_id: $EVENT"

curl -sf "$ROOT/gradio_api/call/ping_assets/$EVENT" | python3 -c "
import sys
lines = sys.stdin.read().splitlines()
for i, line in enumerate(lines):
    if line == 'event: complete':
        data = lines[i+1] if i+1 < len(lines) else ''
        print('PASS — complete data:', data[:120])
        break
    if line == 'event: error':
        print('FAIL — error:', lines[i+1] if i+1 < len(lines) else '?')
        break
else:
    print('FAIL — no complete event in response')
"
```

If FAIL: run `/hf-logs` to see the Python traceback.

---

## Check 4 — CORS preflight from Vercel origin

```bash
ROOT=https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space
ORIGIN=https://book-generator-tom.vercel.app

curl -si -X OPTIONS "$ROOT/gradio_api/call/ping_assets" \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
| grep -i "access-control"
```

Expect `access-control-allow-origin: $ORIGIN` (or `*`). Missing header = FAIL; the
frontend's `fetch` calls will be CORS-blocked in the browser. (CORS works on the real
host — never locally; see [[zerogpu-web-bridge]].)

---

## Check 5 — File serving (if ping_assets returned a file URL)

Parse the `url` from Check 3's `complete` data line, then:

```bash
FILE_URL="<url from complete data — looks like .../gradio_api/file=/tmp/gradio/...>"
curl -sI "$FILE_URL" -w "\nHTTP %{http_code}\n" | grep "HTTP\|content-type"
```

- `HTTP 200` → PASS (file served from `/tmp/gradio/`, correct path).
- `HTTP 403` → FAIL (file served from `temp_gen/` or another non-whitelisted path; the
  output must use `gr.File`, not `gr.Image` — see [[zerogpu-web-bridge]]).

If `ping_assets` returns a 1×1 placeholder, skip this check.

---

## Summary

Report a PASS/FAIL table for all five checks, then one sentence naming the first
failed layer (or "all green — backend healthy"). If any check failed, suggest the
next diagnostic step (`/hf-logs`, `/verify-generate`, or CORS fix).
