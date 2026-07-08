# `.claude/` tooling review

A critical look at TOM's AI infra (`.claude/`) — what would make me faster/cheaper, grounded in
where I actually burned time. Written for a builder agent with **no chat context**: every proposal
below has enough detail to implement cold.

Two debugging eras now inform this:
- **Era 1 (web runtime)** — "site won't generate": ZeroGPU, CORS, `gr.File` 403, log access.
  Produced `/hf-logs`, `/space-probe`, `/verify-generate`, `zerogpu-web-bridge`, `web-backend-contract`.
  **Those are built.** Their notes are retained in the Appendix.
- **Era 2 (geometry/engine, 2026-06-23)** — migrating the deployed product from the heightmap
  engine to the **CadQuery solid** engine. A long marathon of OCCT/geometry bugs. **The current
  toolkit had almost nothing for this.** This section is the new headline.

---

## The new headline gap (Era 2)

Era-1 tooling targets the **web boundary** (transport, CORS, file serving, logs). Era-2's cost was
entirely **inside the geometry pipeline** (`src/dxf_3d.py` + `src/image_funcs.py`): O(N²) booleans,
an OCCT segfault, 10× oversizing, broken layout, skeletonized text, stretched Braille. I diagnosed
every one by **hand-writing throwaway Python** — timing harnesses, STL byte-parsers, per-band
triangle counters, segfault repros — **~15 times**, each rebuilt from scratch. None of it was
captured. And the two relevant skills (`tactile-stl-geometry`, `image-dxf-generation`) describe the
**pre-migration** approach and are now actively wrong.

**The single biggest win would be a local geometry bench** that runs the pipeline offline (no GPU)
and reports timing + STL validity. It would have caught all 8 geometry bugs in seconds each. Second
biggest: **fix `/hf-logs` to show the log *tail*** (see below) — it cost me a dozen manual curls.

---

## Add / fix these (priority order)

### 1. Fix `/hf-logs` — it only shows the HEAD — *highest value, smallest effort*
**Observed all session:** `/hf-logs run` returns the log but truncated to the **startup banner**
(`Application Startup…` + the harmless asyncio `Invalid file descriptor` teardown). The actual
generation + traceback is at the **tail**, which it never showed. I fell back to manual
`curl …/logs/run` + a Python SSE parser + `tail`/`grep` **every single time** I needed the real error.
**What to build:**
- Default to the **tail** (last ~80 meaningful lines), not the head.
- Args: `[run|build] [--tail N] [--grep REGEX] [--follow]`.
- **Noise filter (default on):** drop the asyncio `Invalid file descriptor: -1` / `BaseEventLoop.__del__`
  block and tqdm progress-bar lines (`it/s]`, `B/s]`, `Fetching`, `Loading weights`) — they bury the signal.
- Endpoint quirk: the SSE returns one giant CR-joined string; split on `\r`. (Working parser is in the
  Appendix and in the throwaway I wrote — fold it in.)
**Saves:** ~10 manual log pulls this session; turns "where did it die?" into one call.

### 2. `/stl-bench` (a.k.a. geometry bench) — *highest value, the crown jewel*
**Why:** I wrote this harness ~15 times inline. It is the fastest possible feedback loop for the
engine and needs **no GPU and no deploy** (use a sample image; SD output isn't needed to exercise
DXF→STL).
**What it does**, given a text + optional braille/language + an image (default `outputs/output.png`):
1. Run the real pipeline: `image_to_dxf_exact` → `generate_text_dxf` → `generate_braille_dxf_from_text`
   → `create_one_page_stl_from_dxf`.
2. Report **per-stage timing** (the `[t]` lines already print) + total + **solid count**.
3. **Validate the STL** (parse the binary header yourself — no deps): triangle count; **XY bbox is
   within the plate `[0,W]×[0,H]`** (catches the 10× oversize); **per-band triangle presence**
   (text band y>115, image mid, braille y<35 — catches missing text / empty layers); maxZ per band.
4. **Braille spacing check:** nearest-neighbour dot distance ≈ 2.5 mm (Grade-1).
5. **Run the build in a subprocess** so an OCCT **segfault** (exit 139) is reported, not fatal to the tool.
6. Flags: `--lang hebrew|english`, `--text …`, `--image PATH`, `--time-budget S` (warn if exceeded).
**Would have caught, in seconds, offline:** the O(N²) blow-up, the 2.4 hr fuse, the taper segfault
(#item below), the 10× oversize, the invisible text, the band overlap, the stretched Braille.
**Build note:** the binary-STL XY/Z parser and the per-band counter already exist verbatim in this
session's scratch — they're short (~25 lines). The segfault isolation = `subprocess.run([...], timeout=)`
and check `returncode == -11 / 139`.

### 3. `/gen-probe --gpu` — authenticated, timed, auto-log on failure — *high value*
**Why:** to prove a fix on the live Space I hand-rolled an **owner-token** 2-step generation +
wall-clock timing + a manual `/hf-logs` on failure. (`/verify-generate --gpu` exists but calls the
*anonymous* endpoint, whose quota is 0 → it 2-second-fails and tells you nothing.)
**What:** read `~/.hf_token`; `POST …/gradio_api/call/generate_page` **with `Authorization: Bearer`**
(→ owner PRO quota, the only way to actually run); stream the SSE; print **elapsed** + the output
file URLs; **on `event: error`, auto-pull the run-log tail** (#1) and print the traceback. Args:
`--text --image-desc --lang`. Keep the "don't burn GPU casually" rule — this is the *explicit* GPU path.
**Saves:** the whole hand-rolled curl+time+log dance I repeated several times.

### 4. i18n parity check — extend `/check-sync` — *medium*
**Why:** `web/src/lib/copy.js` now has `{ hebrew, english }`; the keys must stay identical or the UI
shows `undefined`. There's no guard (today `check-sync` only does vendored-copy + nikud parity).
**What:** diff the key sets of `COPY.hebrew` vs `COPY.english` (deep), report missing/extra keys.
Also re-check the existing nikud parity. Cheap, read-only.

### 5. Pre-deploy gate — *high value, prevents the worst cost pattern*
**Why:** this session ran ~8 **deploy → wait for HF rebuild (~2 min) → test → fail → fix** cycles.
Each rebuild also cold-loads the 8.9 GB model. Most failures were catchable **offline**.
**What:** a `/preflight` command (or a PreToolUse/manual gate) that runs before any HF push:
`/stl-bench` (offline, must pass plate-fit + bands + no-skips + time budget) + i18n parity +
`check-sync` + `python -c ast.parse` on the app + `npm run build && npm run lint` for web changes.
Block (advisory) the push if any fail. **This is the highest-leverage process change** — it converts
2-minute remote round-trips into sub-second local ones.

### 6. Golden / regression fixture — *medium*
**Why:** the engine regressed repeatedly (size, layout, text, braille) because there was no baseline.
**What:** a checked-in fixture (a known image DXF + expected invariants) and a `/regress` that runs
`/stl-bench` against it and asserts the invariants (bbox-on-plate, 3 bands present & non-overlapping,
text & braille triangle counts > 0, total time < budget). Run it in `/preflight`.

---

## Skills that are now STALE and must be rewritten (Era-2 invalidated them)

These describe the pre-migration engine and will actively mislead. High priority.

- **`tactile-stl-geometry`** — currently: fillets, boolean union, dome height. **Now must say:**
  - **No boolean union** — features are independent solids in one `Compound`; the *slicer* fuses
    overlaps. OCCT booleans do **not** scale to real line-art (thousands of solids → minutes-hours).
  - **Flat tops** — `extrude(taper=)` **segfaults OCCT on real Hebrew glyph outlines** (reproduced
    on פרח). `STROKE_TAPER_DEG = 0`. Rounded tops require a **crash-isolated subprocess**.
  - **Banded layout** — text(top)/image(mid)/braille(bottom); `layout.*` + `plate.content_margin_mm`
    in `config.yaml`; `layout_content_on_base` scales each layer to its band.
  - **Flushed logs** (`print(flush=True)`) — HF stdout is block-buffered; otherwise the build looks hung.
  - Performance: typical ~50-path page ≈ seconds; ~560-path dense ≈ 60–80 s, all CPU.
- **`image-dxf-generation`** — **now must say:** text uses **filled glyph contours**
  (`_filled_glyphs_to_dxf`, RETR_EXTERNAL) **not** skeletonization (skeletonizing letters → invisible
  broken strokes). Braille is generated **programmatically from Unicode bits at fixed Grade-1 mm**
  (`generate_braille_dxf_from_text`), **not** blob-detection (which stretched short words).
- **`hebrew-braille-nikud`** — add **English** Grade-1 braille (`ENGLISH_BRAILLE_MAP`,
  `english_to_braille`, `text_to_braille(text, language)`); note Hebrew reverses (RTL→LTR), English does not.
- **`web-backend-contract`** — add the **5th `/generate_page` input `language`** (`hebrew|english`),
  threaded through the `/api/generate` proxy; note the new `lib/i18n.jsx` provider.

## New durable knowledge worth a skill or memory
- **OCCT crash-isolation pattern:** any risky CadQuery op (taper/fillet/boolean on user geometry)
  can segfault the whole worker. Run it in a `subprocess` with a timeout; treat `returncode==-11`
  as "skip this feature," never let it kill the Gradio process. Worth a reusable helper + a memory.
- **ZeroGPU cold start:** rebuild wipes the model cache → first `from_pretrained` inside the 30 s GPU
  window is killed. **Pre-download weights at startup** (CPU, off-GPU) — `predownload_weights()`.
  Add to `zerogpu-web-bridge`.

---

## Still good / unchanged from Era 1
- `hooks/sync-guard.py` — narrow, advisory. Keep.
- `/deploy-hf`, `/check-sync`, `/new-page`, `/space-probe`, `/verify-generate` — keep
  (with #3/#4 upgrades). `/verify-generate` should gain the **authenticated** path (#3) — anonymous = useless now.
- `zerogpu-web-bridge`, `web-backend-contract` — keep, extend per above.

---

## Era 3 — frontend & design tooling (the next frontier, per `web/IMPROVEMENTS.md`)

**Critical reality:** the roadmap is ~80% **frontend** — auth + saved library, generation control,
fulfillment, and above all **accessibility (which IS the product** — blind children and parents).
Yet there is **no frontend tooling at all**, and the one browser harness (`tools/space_browser_test.mjs`)
**doesn't run** — Chromium/`chrome` isn't installed in this env, so I could **not visually verify the
i18n work this session.** For a product whose entire value is a *tactile/visual/screen-reader*
experience, shipping UI blind is the single biggest risk. The items below, in rough priority.

### F1. Browser harness — **env SOLVED 2026-06-24; `/web-verify` command still TODO**
Headless chromium now runs (verified: screenshotted the live Vercel site + RTL Hebrew). Setup in
memory `browser-harness-setup`:
- **Don't use the Playwright MCP** (defaults to `chrome` channel, absent). Drive the **bundled**
  chromium from a node script: `chromium.launch({ headless:true })`.
- `playwright@1.60.0` already a `web/` dep; binaries cached in `~/.cache/ms-playwright/`.
- Only missing lib `libasound.so.2` (no sudo) → persisted at `~/.cache/tom-browser-libs/`.
- Run from `web/`: `LD_LIBRARY_PATH=$HOME/.cache/tom-browser-libs node --input-type=module script.mjs`.

**Still TODO:** wrap into a `/web-verify` command that boots `npm run dev` (or serves `dist/`), walks
the 4-step flow in `dir=rtl` AND `dir=ltr`, and screenshots key states. F2/F4 build on it.

### F2. `/a11y` — accessibility gate (non-negotiable for TOM) — *highest value*
Accessibility is the mission, not a checkbox. **Run axe-core** (or Playwright's `@axe-core/playwright`)
against **every route × both languages**, asserting: focus rings visible, ARIA labels present, color
contrast ≥ AA, full keyboard nav, landmark roles, `prefers-reduced-motion` honored, and **image `alt`
on generated illustrations**. Wire it into `/preflight` so a11y regressions block a deploy. *Creative
TOM-specific check:* a "blind-parent path" — assert the entire create→generate→download flow is
operable with **zero pointer events** (keyboard + screen-reader names only), since a blind parent may
be the author (IMPROVEMENTS §4).

### F3. ~~Mock-backend mode~~ — *de-scoped (owner's call)*
Originally proposed as a velocity unlock. **Cut:** the owner is fine with the real ~30 s generation,
and most upcoming screens (auth, "My Books", onboarding, order flow) **don't call generate at all**,
so a full `VITE_MOCK` mode isn't worth its weight. The **one** surviving need is determinism for
screenshot baselines (real SD output differs every run) — covered as a single checked-in fixture in
**F4**, not a mock layer. Revisit only if the backend becomes a reliability blocker for UI work again.

### F4. Dual-direction visual regression — *kills TOM's recurring bug class*
RTL/LTR mirror bugs recur (this session: `text-right`→`text-start`, arrow direction `←/→`,
header-corner placement). **Screenshot every route in `dir=rtl` AND `dir=ltr`, at mobile + desktop
widths, and diff against committed baselines.** As auth/library pages land, this catches layout drift
and mirror bugs for free. *Creative:* a side-by-side he/en contact sheet per PR so a human can eyeball
"does the English mirror look right?" in one image. **Note:** for the generate/download routes, point
the baseline at **one checked-in fixture** image+STL (real SD output varies per run, which would churn
the diff) — this is the only piece of the cut F3 worth keeping.

### F5. `/i18n-lint` — string coverage, not just key parity — *medium, TOM-specific*
Beyond the `COPY.hebrew`/`COPY.english` key-parity check (item #4 above), **detect hardcoded UI
strings in JSX** — Hebrew or English literals that bypass `t.` (this session had several: `aria-label`
in `StlViewer`, `עמוד`, the timer unit, `תוכן ראשי`). Flag any `>[֐-׿...]<` text node or
`aria-label="…literal…"` not sourced from `t`. Also flag **physical-direction utilities**
(`text-left/right`, `ml-/mr-/pl-/pr-`, `left-/right-`, literal `←/→`) that should be logical
(`text-start/end`, `ms-/me-/ps-/pe-`, `start-/end-`). Cheap static scan; prevents the next mirror bug.

### F6. Design-system + no-jargon guard — *uniquely TOM*
`web/CLAUDE.md` documents two hard constraints that nothing enforces: **(a)** design tokens live in
`src/index.css @theme` (the single source of look), and **(b)** a **no-jargon glossary** (never show
users "STL", "generate", "nikud", "חולם/שורוק/דגש" — say "הקובץ להדפסה", "יוצרים", etc.). **Lint for:**
raw hex colors / ad-hoc spacing not using tokens; and banned jargon terms appearing in `copy.js`.
Keeps the warm, parent-facing tone and the visual system consistent as new screens (auth, library,
order-a-copy) are added by future agents who won't have read the glossary.

### F7. A `tom-design-system` skill — *durable knowledge for the build-out*
Most upcoming work is *new* UI (auth, "My Books", onboarding, order flow). A skill that activates on
`web/src/components/**` edits and encodes TOM's design DNA — Rubik 18px base, brand/accent tokens,
`rounded-card`/`shadow-card`, framer-motion `MotionConfig reducedMotion`, RTL-logical spacing,
warm/non-technical Hebrew tone, accessibility-first — so every new component matches without
re-reading `web/CLAUDE.md`. (Today that knowledge is prose in one file an agent may skip.)

### F8. Browser-side printability check — *reuses the engine, ships a roadmap feature*
IMPROVEMENTS §3 wants in-browser printability warnings (text too long for the band, watertight check,
plate size, est. print time). The geometry truths already live in `src/dxf_3d.py` / `config.yaml`
(band fractions, plate mm). A small shared module + a `/printability` check (or a dev panel) that the
STL preview can surface — turning a backend invariant into user-facing UX. Bridges Era-2 and Era-3.

**Cut/avoid:** don't reach for Storybook or a heavyweight visual-test SaaS yet — for a solo build,
F1+F2+F4 (working headless harness + a11y gate + dual-direction baseline diff) deliver 90% of the
value at a fraction of the setup. Add Lighthouse-CI only when SEO/PWA (IMPROVEMENTS §7) actually starts.

## One-line verdict
Three gaps, three eras. Era-1 (web runtime) is **served**. Era-2 (geometry) is **unserved** — build
`/stl-bench`, fix `/hf-logs` tail, add `/preflight`. Era-3 (frontend/design) is **the upcoming bulk of
the work and the most exposed** — **a product whose value is accessibility has no way to even render a
page for inspection.** Fix the browser harness (F1), make a11y a deploy gate (F2), and add
dual-direction visual regression (F4) *before* the auth/library build-out starts, or that work ships
unverifiable.

---

## Appendix — exact facts for a fresh builder agent

### Constants
- **Space repo id:** `MLightning/text2STL-engine-2.0-superMX-bottom`
- **ROOT origin:** `https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space`
  (slug = id lowercased, non-alphanumeric runs → `-`).
- **Owner token:** `~/.hf_token`. **Never print.** `T=$(cat ~/.hf_token)` → `-H "Authorization: Bearer $T"`.
- **Gradio** pinned `6.3.0`; **hardware** `zero-a10g`; **model** `segmind/SSD-1B`, 25 steps;
  `@spaces.GPU(duration=30)` (ZeroGPU reserves ≈ `duration×1.5`, capped by the *caller's* quota —
  anonymous ≈ 0 now, so probes/gens must use the **owner token** to actually run).

### HF logs (the #1 fix)
- `GET https://huggingface.co/api/spaces/{repo}/logs/run` (runtime) and `/logs/build` (deploy),
  `Authorization: Bearer $T`. **NOT** `/logs/container` (404).
- Body is SSE; keep lines starting `data: `, `json.loads`, take `.data`, join, then `.splitlines()`.
  The joined text is CR-heavy — also split on `\r`. **Show the tail; filter the asyncio + tqdm noise.**

### The `/generate_page` contract (for `/gen-probe`, `/space-probe`)
- Named endpoints (`GET {ROOT}/gradio_api/info`): `/generate_page` (GPU), `/ping_assets` (CPU instant),
  `/slow_ping` (CPU ~22 s).
- 2-step REST (no `@gradio/client`): `POST {ROOT}/gradio_api/call/{name}` `{"data":[...]}` → `{event_id}`;
  `GET {ROOT}/gradio_api/call/{name}/{event_id}` → SSE (`event: complete|error|heartbeat`).
- **Inputs (5, positional):** `[raw_text, variations, image_desc, object_class, language]`
  (`language` ∈ `hebrew|english`, defaults `hebrew`). **Outputs:** `[image, stl]` file objects
  (`.url` = `…/gradio_api/file=/tmp/gradio/...`).
- Wake check: `GET {ROOT}/config` → JSON awake, HTML/500 asleep/rebuilding.

### Geometry pipeline entry points (for `/stl-bench`)
- `src/image_funcs.py`: `image_to_dxf_exact(gray, out)`, `generate_text_dxf(text, out, rtl=)`,
  `generate_braille_dxf_from_text(braille_unicode, out)`.
- `src/language_funcs.py`: `text_to_braille(text, language)`.
- `src/dxf_3d.py`: `create_one_page_stl_from_dxf(txt_dxf, braille_dxf, image_dxf, output)`;
  prints `[t]` per-stage timing + `Layout →` + `Assembled N feature solids`.
- Plate is `cfg["plate"]["width_mm"]×height_mm` (150×150). Bands: text y≈[117,140], image≈[37,113],
  braille≈[10,33] for a 150 plate with 10 mm margin. Binary-STL: 80-byte header, uint32 tri count,
  then per-tri 12-byte normal + 3×12-byte verts + 2-byte attr.

### Don't-burn-GPU rule
Never call `generate_page` casually. CPU probes (`ping_assets`/`slow_ping`) and **offline `/stl-bench`**
cover most needs; gate real generation behind `--gpu` and use the owner token (anonymous quota = 0).
