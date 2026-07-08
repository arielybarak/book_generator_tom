# TOM website — improvement suggestions

Ideas to grow the public site (`web/`) beyond "it generates a page." Grounded in what TOM
actually is: **3D-printable tactile storybooks for blind children**, Hebrew-first, made by
**non-technical parents/teachers**, over a **free ZeroGPU** backend, with **Eliya** as the partner.

Grouped by theme; each item has a rough **effort** (S/M/L) and **why it matters**. The two you
named — bilingual + auth — are the first two themes.

---

## 1. Bilingual (Hebrew + English)  — *the site is Hebrew-only today*
- **UI i18n** (M) — extract all `lib/copy.js` strings into `he`/`en` dictionaries, add a language
  toggle, set `dir`/`lang` per language. The pipeline already translates Hebrew→English for the
  image prompt, so the backend is half-ready. *Why:* opens TOM to non-Hebrew families and to
  Eliya's English-speaking partners/donors.
- **English content generation** (M) — accept English `raw_text`, render English raised text +
  English/UEB Braille. Needs a Latin path in `language_funcs` / `lithophane` and a Braille table
  swap. *Why:* the tactile value isn't Hebrew-specific.
- **RTL/LTR correctness per language** (S) — now that Hebrew text renders upright in the STL,
  make sure Latin text stays LTR end-to-end. *Why:* avoid re-introducing the mirror/flip class of bug.

## 2. Accounts & persistence  — *everything is localStorage today; a refresh can lose work*
- **Auth (username + password / magic-link)** (M) — Clerk or Supabase Auth. *Why beyond login:*
  the real lever is **ZeroGPU quota** — anonymous callers hit a low GPU cap; signing requests with a
  per-user identity lets you fair-share GPU, rate-limit abuse, and queue jobs.
- **Saved library** (M) — persist books server-side (Supabase/Postgres or Vercel Blob for STLs):
  a "My books" page, re-download, rename, duplicate. *Why:* generation is slow + costs GPU; never
  make a parent redo a finished book.
- **Email when ready** (S, needs auth) — long/cold GPU jobs can take minutes; email the STL link on
  completion instead of holding the tab. *Why:* matches the real latency of a cold ZeroGPU start.

## 3. Generation quality & control
- **Regenerate with choices** (S) — keep a seed, show 2–3 image variants, let the user pick; "make it
  simpler" slider (fewer strokes = better tactile legibility). *Why:* line-art quality is hit-or-miss.
- **Live STL/printability checks** (M) — warn when text is too long for the band, show plate
  dimensions + estimated print time/filament, validate the mesh is watertight before download.
  *Why:* a failed print wastes hours; catch it in the browser.
- **Prompt presets / categories** (S) — animals, shapes, vehicles, letters — curated prompts tuned
  for clean single-stroke output. *Why:* non-technical users shouldn't have to prompt-engineer.

## 4. Accessibility — *this is the point of the product*
- **The site for blind parents** (M) — a blind parent may be making a book for their child. Full
  screen-reader pass, audio confirmation of each step, describe the generated image in text/ARIA.
- **Audio narration of the page** (M) — TTS of the Hebrew sentence attached to each page, so the
  child hears the story while feeling the relief.
- **Braille options** (M) — Grade 1 vs Grade 2 Hebrew Braille, and a nikud-in-Braille toggle. *Why:*
  reading level varies by child/age.

## 5. From file to object (fulfillment)
- **"Order a printed copy"** (L) — most users don't own a 3D printer. Integrate a print-on-demand
  service or Eliya's printers; one button → printed + shipped. *Why:* this is what turns a download
  into a book in a child's hands — the actual mission.
- **Book assembly** (M) — cover page, Braille page numbers, binding-hole option, export the whole
  book as one print job / ZIP. *Why:* a "book" is more than loose pages.

## 6. Sustainability & trust
- **Cost/quota management** (M) — visible queue position, per-account rate limits, a donations / "support
  TOM" link (GPU isn't free at scale). *Why:* keeps the free tier alive.
- **Safety on generation** (S) — basic prompt moderation (kids' content), since images are public-ish.
- **Observability** (S) — Sentry for frontend errors + Vercel Analytics; a feedback button. *Why:*
  today a failed generation is invisible to you unless a user reports it.

## 7. Polish (quick wins)
- **SEO / social** (S) — Open Graph / Twitter cards + canonical tags for a shareable public site.
- **PWA** (S) — installable, offline access to the saved library.
- **Onboarding** (S) — a 30-second first-run guide for a parent who has never 3D-printed anything.
- **Shareable book links** (S) — send a book to a partner/teacher by URL (pairs with accounts).

---

## Suggested sequence
1. **Auth + saved library + email-when-ready** — unblocks GPU fair-use *and* stops losing work. Highest leverage.
2. **Bilingual UI** (then English content) — widen the audience; partner/donor friendly.
3. **Generation control + printability checks** — raise the success rate per generation.
4. **Order-a-printed-copy** — the mission-completing feature; largest effort, do it once the above is solid.

> Notes from the build: anonymous ZeroGPU has a low GPU-duration cap (auth helps manage it); the STL
> now renders upright in any viewer (row-flip fix in `src/lithophane.py`). Backend contract + ZeroGPU
> traps live in `.claude/skills/zerogpu-web-bridge` and `web-backend-contract`.
