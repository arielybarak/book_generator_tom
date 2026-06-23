# `.claude/` tooling review

A critical look at TOM's AI infra (`.claude/`) — what would make me faster/cheaper, and what to cut.
Written after a multi-session debug of "website won't generate," grounded in where I actually burned
time and tokens.

## The headline gap

Every existing tool targets **pre-deploy source hygiene** — sync drift, vendored copies, geometry
printability, nikud parity. **Nothing targets the *running* Space.** Yet ~100% of this session's
cost was *runtime*: a ZeroGPU duration cap, a `gr.File` crash, `@gradio/client` hanging off the HF
iframe, CORS, file-serving 403s, log access. The toolkit is built for the half of the lifecycle
that rarely breaks and silent on the half that just ate three sessions.

The proposed additions all close that runtime gap.

---

## Add these (priority order)

### 1. `/hf-logs` command  — *highest value*
**Why:** the single most useful thing this session was the HF container log
(`GET https://huggingface.co/api/spaces/{repo}/logs/run`, `Authorization: Bearer <token>`, SSE,
JSON-per-line `data:` frames). I rediscovered the endpoint by trial (`/logs/container` → 404,
`/logs/run` → 200) and hand-wrote the SSE decoder. That's pure waste — it should be one command.
**What:** read token from `~/.hf_token` (never print it), fetch `run` + `build` logs, decode the
`data:` frames, tail N lines, optional `grep` for `Traceback|Error|GPU`. Args: `[run|build] [grep]`.
**Saves:** the exact 20 minutes + several tool calls I spent today; turns "what crashed?" into one call.

### 2. `zerogpu-web-bridge` skill — *highest value*
**Why:** this is the knowledge that would have collapsed the whole saga to one step. It is deep,
non-obvious, and currently lives only in an ephemeral memory file.
**What it encodes:**
- The browser `@gradio/client` **cannot** drive a ZeroGPU job off the HF iframe (the GPU token
  postMessage handshake never happens) → it hangs. Use Gradio's plain REST instead:
  `POST /gradio_api/call/<api_name> {"data":[...]}` → `{event_id}`, then
  `GET /gradio_api/call/<api_name>/<event_id>` → SSE to `event: complete`.
- **`@spaces.GPU(duration=N)` → ZeroGPU reserves ≈`N×1.5`, capped by the *caller's* quota.**
  Anonymous (the public site) has a low cap; authenticated (HF UI / Python+token) is higher — so a
  too-high duration "works in testing, fails in prod." Keep `duration` small (SD-25-step ≈ fits 60).
- File outputs: `gr.File` copies to `/tmp/gradio` (served); `gr.Image` serves in place → 403 on HF.
- ZeroGPU model cache is wiped on rebuild → first call cold-loads.
- CORS: Gradio's `CustomCORSMiddleware` reflects the request Origin **only when host ≠ localhost**
  (so it "just works" on `*.hf.space`, never locally).
**Saves:** prevents re-deriving any of the five dead-ends I hit. This is the crown jewel.

### 3. `/space-probe` command — *high value*
**Why:** I wrote ~8 ad-hoc curl/Playwright scripts to ask "is the contract intact?" Codify them.
**What (read-only, zero GPU):** `/config` reachable, `/gradio_api/info` named endpoints, a CPU
round-trip via `/gradio_api/call/ping_assets` (POST→event_id→SSE→file), CORS preflight from the
Vercel origin, and a `/gradio_api/file=` fetch. PASS/FAIL per check.
**Saves:** instant "is it the backend, the CORS, or the frontend?" triage without touching the GPU.

### 4. `web-backend-contract` skill — *medium*
**Why:** `web/CLAUDE.md` documents the contract as prose, but it isn't an activatable skill and is
now **stale** (it still says the frontend uses `@gradio/client` / `/generate_page`; it now uses
`/gradio_api/call` + an SSE reader + the `.hf.space` credentials-strip fetch shim + ROOT-slug
computation). A skill that activates on `web/src/api/hfClient.js` edits and states the *current*
contract would stop the docs/code drift. (At minimum: fix `web/CLAUDE.md`.)
**Saves:** the next person (or me) won't reintroduce the hanging client.

### 5. `tools/space_browser_test.mjs` + a `browser-testing` note — *medium*
**Why:** browser E2E against the live Space needs a fragile incantation
(`LD_LIBRARY_PATH=/tmp/alsa_extract/... node --input-type=module`, esm.sh client import, the
production-page-for-real-origin trick). I rebuilt it from scratch each time in `/tmp`.
**What:** a checked-in, parameterized script (endpoint, data) + 4 lines on the runtime setup.
**Saves:** ~one rebuild per debugging session; makes E2E reproducible instead of tribal.

### 6. `/verify-generate` command — *medium, gated*
**Why:** "did the fix actually work?" had no cheap answer. **Defaults to CPU** (`ping_assets`/
`slow_ping`) for transport confidence; only hits real `generate_page` (GPU) with an explicit
`--gpu` flag — respecting the standing "don't burn GPU for testing" rule.

---

## Cut / trim these

### Delete: `agents/deploy-readiness-reviewer.md`  — *redundant*
It checks the same two things as the **`/check-sync` command** (vendored-copy sync + nikud parity)
plus app_file. An agent spawn re-derives context cold — the expensive path — to produce what a
command already produces cheaply. One-dev repo doesn't need a heavyweight twin. Keep `/check-sync`;
fold the "right app_file?" check into it; delete the agent.

### Reconsider: `agents/geometry-auditor.md` — *weakly justified*
Overlaps the `tactile-stl-geometry` skill (skill = rules, agent = audit). Less duplicative than #1
above, but it's still a full agent spawn for something a `/geo-check` command (or just the skill +
a read) would do for a fraction of the tokens. Recommend converting to a command, or deleting until
geometry work is actually frequent. As-is it has never fired.

**Pattern:** two read-only agents for a small solo project is over-provisioned. Agents are the
costly path (cold re-derivation); commands carry the same checklists for less. Prefer commands.

### Keep (good as-is)
- `hooks/sync-guard.py` — narrow, advisory, never blocks. Correct.
- skills `hebrew-braille-nikud`, `image-dxf-generation`, `tactile-stl-geometry` — solid domain refs.
- commands `/deploy-hf`, `/check-sync`, `/new-page` — fine. (`/deploy-hf` note below.)

### Tune: `/deploy-hf` + `sync-guard` blind spot
Both are built around "edit repo-root `src/`/`config.yaml` → `sync_to_space.sh` → push." But the
**app file `hf_space/gradio_app_lithophane.py` is canonical in the submodule and edited directly** —
that was *most* of this session's edits, and `sync_to_space.sh` is irrelevant for it. `/deploy-hf`
should branch: *app-file-only change* → just `commit + push from hf_space/` (no sync); *src/config
change* → the sync path. Today it implies a sync step that an app-file fix doesn't need.

---

## One-line verdict
Tooling is well-built but aimed at the wrong half: **strong on "will this deploy cleanly," absent on
"why is the deployed thing broken."** Add `/hf-logs` + `zerogpu-web-bridge` + `/space-probe`, delete
one agent, and the toolkit would match where the work actually is.

> **Status:** `/hf-logs` (command) and `zerogpu-web-bridge` (skill) are **built** (scored 99/100).
> The notes below are for a fresh agent building the rest (#3–#6) — it can't see the chat that
> produced them.

---

## Appendix — Build notes (exact facts for the remaining tools)

A fresh agent has none of the session context. Everything needed to build #3–#6 is here, plus
pointers. Authoritative live code: `web/src/api/hfClient.js` (the working client) and
`hf_space/gradio_app_lithophane.py` (the Space). Deepest narrative: the memory file
`website-generate-hang-debug.md` (may not be visible to a subagent — don't depend on it).

### Constants
- **Space repo id:** `MLightning/text2STL-engine-2.0-superMX-bottom`
- **Space origin (ROOT):** `https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space`
  (slug = id lowercased, every non-alphanumeric run → `-`).
- **Owner token:** file `~/.hf_token` (user-provided). **Never print it**; read into a var:
  `T=$(cat ~/.hf_token)` then `-H "Authorization: Bearer $T"`. Don't pass tokens through chat.
- **Gradio:** pinned `6.3.0`. **Hardware:** `zero-a10g` (ZeroGPU). **Model:** `segmind/SSD-1B`,
  25 steps. **GPU duration:** `@spaces.GPU(duration=60)` (ZeroGPU reserves ≈ `duration × 1.5`,
  capped by the *caller's* quota; anonymous = low).

### HF API (token-auth, reachable from this env)
- whoami (token check): `GET https://huggingface.co/api/whoami-v2`
- runtime/hardware/sha: `GET https://huggingface.co/api/spaces/{repo}/runtime`
- **logs (SSE, JSON `data:` frames, field `.data`):** `…/logs/run` (runtime) and `…/logs/build`
  (deploy). **NOT** `…/logs/container` (404). Decode: keep lines starting `data: `, `json.loads`,
  take `.data`, `"".join(...)`, splitlines. (This is exactly what `/hf-logs` does.)

### The web↔Space call contract (for `/space-probe`, #6, and contract checks)
Named endpoints (`GET {ROOT}/gradio_api/info` → `named_endpoints`):
`/generate_page` (GPU), `/ping_assets` (CPU, instant), `/slow_ping` (CPU, 22s) — the last two are
**GPU-free** and ideal for probes.
Two-step REST call (no `@gradio/client`):
1. `POST {ROOT}/gradio_api/call/{name}` body `{"data":[...]}` → `{"event_id": "..."}`
2. `GET {ROOT}/gradio_api/call/{name}/{event_id}` → SSE; lines `event: <type>` then `data: <json>`.
   Types: `heartbeat` (ignore — keeps long jobs alive), `complete` (its `data:` = output array),
   `error` (throw). `generate_page` data in = `[raw_text, variations, image_desc, object_class]`,
   out = `[image, stl]` (each a file object; `.url` = `…/gradio_api/file=/tmp/gradio/...`).
- **CORS** is correct on the real host (Gradio reflects Origin when host ≠ localhost); a CPU probe:
  `OPTIONS {ROOT}/gradio_api/call/ping_assets` with `Origin: https://book-generator-tom.vercel.app`
  → expect `access-control-allow-origin: <that origin>`.
- **Wake check:** `GET {ROOT}/config` returns JSON when awake, HTML when asleep/building.

### Browser E2E harness (for #5 — the Playwright/SSE setup)
Node + Playwright run incantation (the system libs live in a temp extract):
`LD_LIBRARY_PATH=/tmp/alsa_extract/usr/lib/x86_64-linux-gnu node --input-type=module < script.mjs`
(run from `web/`). To exercise the **real** browser path: `chromium.launch` →
`page.goto('https://book-generator-tom.vercel.app/')` (real origin + the app's credentials-strip
fetch shim) → in `page.evaluate`, `fetch` the `/gradio_api/call/...` 2-step flow and read the SSE
via `res.body.getReader()`. Use `slow_ping` (CPU 22s) to validate transport with **zero GPU**.
Note: `/tmp` venvs (`/tmp/gsrv` gradio 6.3.0, `/tmp/gctest` gradio_client) and `/tmp/alsa_extract`
are ephemeral — a fresh env may need to recreate them (`uv`, not system pip which is broken).

### Don't-burn-GPU rule
The owner is emphatic: never call `generate_page` (GPU) just to test. Use `ping_assets`/`slow_ping`
for transport, `/hf-logs` for failures. `/verify-generate` (#6) must default to CPU; gate real GPU
behind an explicit `--gpu` flag.
