# web/ — TOM frontend (Claude Code instructions)

React + Vite + Tailwind v4 SPA. The beautiful, **non-technical Hebrew** face over the
Hugging Face compute backend. Users = parents / kindergarten teachers, no tech background.
**Hebrew-first, RTL, accessible.** Deployed to Vercel; the HF Space stays the backend.

## Run

```bash
npm install
npm run dev        # http://localhost:5173
npm run build
```

Env: `VITE_HF_SPACE` = public HF Space id (compute backend). See `.env.example`.

## Backend API contract (the only backend touchpoint)

`src/api/hfClient.js` → `@gradio/client` → endpoint **`/generate_page`** on the Space:

- **inputs** (positional): `[raw_text, variations, image_desc, object_class]`
  - `raw_text` — Hebrew sentence
  - `variations` — `{ "<charIndex>": "<key>" }` nikud choices (keys from `lib/nikud.js`)
  - `image_desc` / `object_class` — short picture description (Hebrew or English)
- **outputs**: `[image, stl]` → served file URLs (`{ url }`)

Defined in `hf_space/gradio_app_lithophane.py` (deployed) and `hf_space/gradio_app.py`.

## Hebrew copy — NO JARGON (glossary)

All UI strings live in `src/lib/copy.js`. Never expose engineering terms:

| Concept | Say (Hebrew) |
|---|---|
| STL / file | הקובץ להדפסה |
| generate | יוצרים / ליצור |
| the image | הציור |
| nikud / vowels | איך הוגים את האות?  (never חולם/שורוק/דגש) |
| 3D model / STL preview | הדגם / תצוגה תלת־ממדית |

Tone: short, warm, human. Speak to a parent, not a developer.

## Conventions

- **RTL everywhere** (`html dir="rtl"`). Prefer logical spacing; verify both directions.
- **Design tokens** live in `src/index.css` `@theme` (colors, font, radius, shadow) — the
  single source of the look. Change there, not ad-hoc. Utilities: `bg-brand`, `text-ink`,
  `bg-brand-soft`, `text-accent`, `rounded-card`, `shadow-card`, …
- **Font**: Rubik (Google Fonts, Hebrew). Base 18px for readability.
- **Accessibility is the point of this product** — keep it exemplary: visible focus rings,
  ARIA labels, full keyboard nav, high contrast, `prefers-reduced-motion` respected.
- Components in `src/components/` (PascalCase `.jsx`); primitives in `components/ui/`.
- Format with Prettier (`.prettierrc.json`) before commit.

## ⚠ nikud sync

`src/lib/nikud.js` mirrors the option **keys** of `SPECIAL_REPLACEMENTS` in
`../src/language_funcs.py`. If the backend keys change, update `nikud.js` to match.
Also note the current `hf_space/gradio_app_lithophane.py` had a Hebrew RTL/direction quirk —
don't treat its Hebrew handling as a reference; verify text + Braille direction independently.

## Deploy

Frontend → **Vercel** (project root = `web/`, env `VITE_HF_SPACE`). Auto-deploys on `git push`.
Backend stays on HF — see repo-root `CLAUDE.md` → "HF Spaces deployment note".
