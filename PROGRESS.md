# PROGRESS — TOM website (web/) + HF backend endpoint

Living status for the public Hebrew website over the HF Gradio backend.
Durable design/decisions live elsewhere — this file is the **transient snapshot**:
what's done, what's left, and known caveats. Update it as work proceeds.

**Detail lives in:**
- Plan: `~/.claude/plans/thanks-make-a-plan-cosmic-pebble.md`
- Conventions: `web/CLAUDE.md` (API contract, Hebrew no-jargon glossary, RTL/brand)
- Decisions/gotchas: memory `website-frontend`, `hf-deploy-gotchas`, `barak-style`
- Deployed HF app: `hf_space/gradio_app_lithophane.py`

_Last updated: 2026-06-11._

## ✅ Done (code-complete; `npm run build` + ESLint clean)
- **Frontend** `web/` — React 19 + Vite + Tailwind v4 (tokens in `src/index.css @theme`),
  framer-motion, three.js. 4-step flow in `src/App.jsx`: Landing → BookBuilder → GenerateStep
  → DownloadStep. Components in `src/components/` (+ `ui/`); friendly nikud chips
  (`NikudChooser` + `lib/nikud.js`); 3D `StlViewer`; client `src/api/hfClient.js`; copy `src/lib/copy.js`.
- **Backend** — hidden `/generate_page` endpoint added to `hf_space/gradio_app_lithophane.py`
  (deployed) and `hf_space/gradio_app.py`. Compiles. **NOT pushed to HF yet.**
- **Setup** — `web/CLAUDE.md`, `web/fixtures/sample-book.json`, memory entries.
- **Phase 6 polish** (2026-06-11):
  - Code-split three.js: `DownloadStep` is now `React.lazy()` — initial bundle 374 kB (was ~911 kB),
    three.js loads only when user reaches step 4 (separate 539 kB chunk).
  - Landing page gallery: 3 example tactile-page cards (cat/dog/flower) below the hero with a 2nd CTA.
  - `TactilePageMock` now accepts `word` prop and renders a matching SVG illustration.
  - Fixed `GenerateStep` queue detection: was checking `stage === 'in_queue'` (not a real stage value),
    now correctly checks `msg.queue === true || position > 0` per actual `@gradio/client` v2 spec.
  - Added `aria-label="תוכן ראשי"` to `<main>` for screen-reader landmark.
  - `web/README.md` with Vercel deploy steps (replaces Vite boilerplate).
- **Phase 7 — a11y pass** (2026-06-11) via headless Playwright + extracted `libasound2`:
  - ✅ RTL direction, Hebrew headings, `<main>` landmark, no missing image alt text — all pass.
  - **Fixed**: Focus ring was white on colored buttons (Tailwind's `transition` includes `outline-color`;
    ring animated in from white → near-invisible on cream background). Fix: pre-set
    `outline-color: var(--color-accent)` on all focusable elements in `index.css` so the transition
    starts at the correct teal colour. Also hardened `:is()` over `:where()` for specificity.
  - **Fixed**: Mobile Stepper overflow — step 4 circle clipped at left edge (390px viewport).
    Fix: connector lines `hidden sm:inline-block`, circles `h-7 w-7 sm:h-8 sm:w-8` — all 4
    steps fully visible on mobile without overflow.
  - Visual screenshots in `web/playwright-shots/` (not committed).

## ⏳ Pending / blockers
1. **Push HF backend** to deploy `/generate_page` (needed for live generation). Commit `7f865c0`
   is ready in `hf_space/`. Auth/http gotchas: memory `hf-deploy-gotchas`. Run manually:
   ```bash
   cd ~/book_generator_tom/hf_space
   HF_TOKEN=$(cat ~/.cache/huggingface/token)
   git push "https://MLightning:${HF_TOKEN}@huggingface.co/spaces/MLightning/text2STL-engine-2.0-superMX-bottom" main
   ```
2. **End-to-end live test** after the HF push: add page → generate → image+STL URLs → 3D preview → download.
3. **Main-repo git commit** — web/, hf_space submodule pointer, .claude/, README.md, CLAUDE.md,
   PROGRESS.md are all ready to stage. Commit only when barak asks.
4. **Vercel deploy** — connect `web/` to a Vercel project, set `VITE_HF_SPACE`.

## Playwright notes (for future sessions)
- Chromium is at `~/.cache/ms-playwright/chromium-1223/` but needs `libasound2`.
- Workaround: `apt-get download libasound2 && dpkg-deb -x libasound2_*.deb /tmp/alsa_extract`
  then prefix: `LD_LIBRARY_PATH=/tmp/alsa_extract/usr/lib/x86_64-linux-gnu node script.mjs`
- Playwright MCP defaults to `chrome` channel; no sudo → can't install.
  Real fix: `sudo apt install libasound2` or run test scripts via Bash directly.

## ⚠ Caveats (assumptions made without live testing)
- `hfClient.js` assumes `@gradio/client` v2 message shapes — verified against the source:
  `msg.type === 'status'/'data'` ✓, `msg.stage` ✓, `msg.queue` ✓, `msg.position` ✓.
  Still need to validate against the real live endpoint (file URLs, etc.).
- `StlViewer` lays the plate flat via `mesh.rotation.x = -Math.PI/2` (a guess) — confirm the STL
  up-axis visually; fix orientation if needed.
- `web/src/lib/nikud.js` option keys MUST mirror `SPECIAL_REPLACEMENTS` in `src/language_funcs.py`.

## Run
```bash
npm run dev --prefix web     # http://localhost:5173  (not running in a fresh session)
npm run build --prefix web   # validate compile
cd web && npm run lint
```
