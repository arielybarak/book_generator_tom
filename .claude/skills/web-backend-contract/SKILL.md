---
name: web-backend-contract
description: >-
  TOM hfClient.js contract: Gradio 2-step REST (never @gradio/client), CORS
  credentials-strip shim, wakeUp, SSE decoder. USE WHEN editing
  web/src/api/hfClient.js or web-facing Space endpoints.
---

# Web ↔ Space call contract

`web/src/api/hfClient.js` is the **only** file that talks to the Space. This skill
describes its current implementation so edits don't re-introduce past failures.

## Why NOT @gradio/client

`@gradio/client` hangs in the browser when calling a ZeroGPU Space from a standalone
site. The GPU-token `postMessage` handshake with `huggingface.co` only fires inside the
HF iframe — off-iframe the job submits but never runs. See [[zerogpu-web-bridge]].

## The 2-step Gradio REST API (current impl)

```
POST {ROOT}/gradio_api/call/{api_name}
  body: {"data": [...positional inputs...]}
  → {"event_id": "..."}

GET  {ROOT}/gradio_api/call/{api_name}/{event_id}
  → SSE stream: event: heartbeat | generating | complete | error
    complete data: JSON array of outputs
```

`ROOT = https://{slug}.hf.space`  
slug = Space id lowercased, every non-alphanum run → `-`.  
(`SPACE = MLightning/text2STL-engine-2.0-superMX-bottom`, slug already computed in `hfClient.js`)

### generate_page inputs / outputs
- **Inputs (positional):** `[raw_text, variations, image_desc, object_class]`
  - `raw_text`: Hebrew string
  - `variations`: `{ "<charIndex>": "<key>" }` nikud choices (keys from `web/src/lib/nikud.js`)
  - `image_desc` / `object_class`: short picture hint (Hebrew or English)
- **Outputs:** `[image, stl]` — each a Gradio file object `{ url: "…/gradio_api/file=/tmp/gradio/…" }`

Normalize output with `fileUrl(item)` (handles `{ url }`, `{ path }`, or plain string).

### Probe endpoints (CPU — for `/space-probe` and `/verify-generate`)
- `ping_assets` — instant CPU, same REST shape as `generate_page`, mirrors one output file
- `slow_ping` — CPU, ~22 s, stress-tests long SSE connections

## CORS shim (credentials-strip fetch patch)

HF's edge doesn't set `Access-Control-Allow-Credentials: true`, so any credentialed
cross-origin request is rejected. The patch in `hfClient.js`:

```js
if (url && url.includes('.hf.space')) init = { ...init, credentials: 'omit' }
```

Applied once at module load (`window.__hfFetchPatched` guard). **Do not remove it.**
Note: CORS reflects the request Origin only when `host ≠ localhost` on HF; local dev
shows no CORS header even with the shim — that's correct, not a bug.

## wakeUp poll

Before submitting a job, `wakeUp()` polls `GET {ROOT}/config` (returns JSON when awake,
HTML when sleeping/rebuilding). It retries up to 10× with 5 s gaps, emitting a `'waking'`
status event each retry. If the Space never wakes, the job submission will likely fail;
the caller surfaces the error normally.

## SSE decoder (readResultStream)

`readResultStream(url, signal)` streams the GET response line by line:
- `event: heartbeat` → ignore (keeps long ZeroGPU jobs alive over the wire)
- `event: generating` → ignore
- `event: complete` → parse `data:` line as JSON → resolve the promise
- `event: error` → parse error detail → throw
- Stream ends before `complete` → throw `'Result stream ended before completion'`

Buffer correctly across chunk boundaries — the decoder maintains a `buffer` string and
a `lastEvent` variable, consuming `\n`-terminated lines.

## Timeout

`GENERATE_TIMEOUT_MS = 8 * 60 * 1000` (8 min). Covers ZeroGPU cold-model load (~1–3 min
on a cold Space) plus the 25-step SSD-1B inference. Controlled by an `AbortController`
passed to both the POST and the SSE GET.

## File URL gotcha

`gr.Image` outputs in the Space serve from `temp_gen/` → **403** on HF (not in the
whitelist). Outputs must use `gr.File` so they land in `/tmp/gradio/` (whitelisted).
If you see `fileUrl(item)` returning a non-`/tmp/gradio/` URL, the Space-side output
type is wrong — fix it there, not in `hfClient.js`.

## What NOT to change

- Do not re-introduce `@gradio/client` — it hangs.
- Do not add `credentials: 'include'` to any `.hf.space` fetch — CORS will reject it.
- Do not bump `duration=` above 60 on `@spaces.GPU` without understanding the anonymous
  quota cap (see [[zerogpu-web-bridge]] for the full rule).
