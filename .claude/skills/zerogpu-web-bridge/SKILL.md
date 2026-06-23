---
name: zerogpu-web-bridge
description: >-
  @gradio/client hangs off-iframe on TOM's ZeroGPU Space — use /gradio_api/call REST+SSE.
  Anonymous duration cap breaks prod silently. gr.File not gr.Image (→403). USE WHEN
  editing hfClient.js, @spaces.GPU(duration=), or debugging hang/CORS/403.
---

# ZeroGPU ↔ web bridge

How the Vercel site (`web/`) talks to the ZeroGPU Gradio Space (`hf_space/`). This is the
*runtime* contract — orthogonal to the deploy/sync rules in [[hf-space-sync-deploy]] and the
pipeline in CLAUDE.md. Every rule here was paid for by a silent production failure.

## When to Activate This Skill
- Editing `web/src/api/hfClient.js`, or the Space's web-facing endpoints (`generate_page`,
  `ping_assets`, `slow_ping`) in `hf_space/gradio_app_lithophane.py`.
- "Site won't generate" / hangs forever / "immediately wrote something went wrong" / blank image.
- Changing `@spaces.GPU(duration=…)`, a `gr.File`/`gr.Image` output, or CORS.
- Calling the Space from any browser / third-party origin.

## Call the Space via Gradio's REST API — NOT @gradio/client
The browser `@gradio/client` only gets ZeroGPU scheduled through a `postMessage` token
handshake with `huggingface.co`, which **only happens inside the HF iframe**. A standalone
site (Vercel) isn't in that iframe → GPU jobs submit but never run → the client hangs with no
error. The Python client works because it uses a different (non-iframe) path.

Use Gradio's built-in 2-step REST API (same path the Python client uses, no handshake):
1. `POST {ROOT}/gradio_api/call/{api_name}` body `{"data":[...]}` → `{ "event_id": ... }`
2. `GET  {ROOT}/gradio_api/call/{api_name}/{event_id}` → SSE; read to `event: complete`,
   whose `data:` is the output array. Ignore `event: heartbeat` (keeps long jobs alive);
   throw on `event: error`.

`ROOT = https://{slug}.hf.space`, slug = Space id lowercased, every non-alphanum run → `-`.
Reference impl: `web/src/api/hfClient.js` (`generatePage` + `readResultStream`). Inputs for
`generate_page`: `[raw_text, variations, image_desc, object_class]`; outputs `[image, stl]`
(each a file object with `.url`).

## Keep @spaces.GPU(duration=…) small — the anonymous cap is the trap
ZeroGPU reserves **≈ duration × 1.5** and rejects it if it exceeds the **caller's** quota.
The public site calls **anonymously** (low cap); HF UI / Python-with-token have a higher cap.
So a big duration *passes your authenticated test and fails on the live site* with
`"The requested GPU duration (Xs) is larger than the maximum allowed"` → SD never runs.
Keep it tight: a 25-step SSD-1B run on the `zero-a10g` fits `duration=60` (→ ~90 requested).

## Gotchas
- **gr.File, not gr.Image, for web outputs.** `gr.File` copies the file into `/tmp/gradio`
  (whitelisted/served); `gr.Image` serves in place from `temp_gen/` → **403** on HF.
  `allowed_paths=` / `GRADIO_ALLOWED_PATHS` are ignored on HF — don't rely on them.
- **Fail loud when SD didn't run.** If the GPU call is rejected, `generate_page_assets` leaves
  no PNG and returns a dead path → `gr.File.postprocess` does `Path(missing).stat()` →
  `FileNotFoundError` → raw 500 / instant `event: error`. The web handler must `raise gr.Error`
  (user-facing) when the image/STL file is missing instead of returning the path.
- **CORS just works on HF, never locally.** Gradio's `CustomCORSMiddleware` reflects the
  request Origin only when the server host ≠ localhost — so cross-origin works on `*.hf.space`
  but a local test shows no `Access-Control-Allow-Origin`. Don't "fix" CORS for the local case.
- **Model cache is wiped on every Space rebuild** → the first call after a deploy cold-loads
  the model. Combined with the small duration, the first post-deploy generation can time out;
  it succeeds on retry (cache now warm). A clean `gr.Error` makes that retry-able.
- **Sleeping Space**: a cold/asleep Space serves HTML, not JSON. `hfClient.js` polls `/config`
  (`wakeUp`) before submitting. A `SyntaxError: Unexpected token '<'` in the browser = it got
  the HTML shell where it expected JSON (Space asleep, or the route 404'd to the SPA).
- **Read the actual error** with the `/hf-logs` command — Gradio hides tracebacks from clients
  (`data: null`); the Space's `logs/run` has the real Python stack.
