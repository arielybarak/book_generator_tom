---
name: tom-design-system
description: >-
  TOM web design DNA for new components in web/src/components/ — Rubik 18px base, brand/accent
  tokens in src/index.css @theme, rounded-card/shadow-card, framer-motion reducedMotion, RTL-logical
  spacing (ms-/me-/ps-/pe-), warm Hebrew tone. USE WHEN adding new UI screens or components.
---

# TOM design system

Activate this skill when adding new components or screens to `web/src/`. It encodes TOM's design
DNA so new work matches without re-reading `web/CLAUDE.md`.

## Typography

- **Font:** Rubik (Hebrew + Latin), loaded via `index.css @font-face` or Google Fonts.
- **Base:** 18px (`text-lg` in Tailwind or `var(--text-base)`). Never go below 16px for
  body copy — parents of blind children may also have low vision.
- **Headings:** semibold (`font-semibold`), not bold.
- **RTL:** Hebrew text auto-aligns via `dir="rtl"` on `<html>`. Never set explicit
  `text-left` / `text-right` — use `text-start` / `text-end`.

## Color tokens — `src/index.css @theme`

All colors live as CSS custom properties. **Never raw hex in JSX** — use the token class
(e.g. `bg-brand`, `text-accent`). Key tokens (verify in `index.css`; names may evolve):

```css
@theme {
  --color-brand:   /* warm orange/coral — primary CTAs */
  --color-accent:  /* indigo/blue — secondary, focus rings */
  --color-surface: /* off-white — card backgrounds */
  --color-text:    /* near-black — body copy */
}
```

If you add a new color, add it to `@theme` first, then use it via Tailwind (`bg-[var(--color-new)]`
or add a Tailwind alias). Never repeat a raw hex twice.

## Spacing and layout

- **Cards:** `rounded-card` + `shadow-card` (defined in `tailwind.config.*` or `@layer`). All
  content panels use this; do not use raw `rounded-xl` / `shadow-lg` — they'll drift from the system.
- **RTL-logical spacing:** always `ms-*` / `me-*` / `ps-*` / `pe-*` (margin/padding start/end),
  never `ml-*` / `mr-*` / `pl-*` / `pr-*`. Same for positioning: `start-*` / `end-*`, not `left-*`
  / `right-*`. ([[/i18n-lint]] catches regressions.)
- **Gutters:** 4-column mobile, 12-column desktop. Sections use `px-4 md:px-8`.

## Motion

TOM uses **Framer Motion** for transitions. All motion must respect `prefers-reduced-motion`:

```jsx
import { MotionConfig } from 'framer-motion';
// in layout root:
<MotionConfig reducedMotion="user"> ... </MotionConfig>
```

Do not add bare CSS `transition`/`animation` properties — route through Framer or check
`prefers-reduced-motion` via the `useReducedMotion()` hook.

## Accessibility baseline (every component)

- **Focus rings:** `focus-visible:ring-2 focus-visible:ring-accent` on every interactive element.
  Never `outline-none` without a replacement visible indicator.
- **ARIA:** text inputs need `aria-label` or `<label htmlFor>`. Icon-only buttons need
  `aria-label`. Use `aria-live="polite"` for dynamic status updates (loading, errors).
- **Contrast:** all text ≥ 4.5:1 vs its background. Check with `/a11y` before shipping.
- **Landmark roles:** `<main>`, `<nav>`, `<header>`, `<footer>` — always present at page level.

## Tone (copy.js)

TOM's users are parents, not developers. Glossary (see also [[/design-lint]]):

| Banned | Use instead |
|---|---|
| STL / stl | הקובץ להדפסה |
| generate | יוצרים (we create) |
| nikud / ניקוד | describe the choice functionally |
| object_class | never user-facing |

Warmth > efficiency. One sentence that feels like a caring teacher, not a developer portal.

## New screen checklist

Before wiring a new screen to routing:
1. Tokens used (no raw hex). ✓
2. RTL-logical spacing only. ✓
3. `rounded-card shadow-card` for content panels. ✓
4. Focus rings on all interactives. ✓
5. Landmark roles present. ✓
6. Copy through `t.` accessor (no hardcoded strings). ✓
7. Motion behind `MotionConfig reducedMotion`. ✓
8. Run `/a11y`, `/i18n-lint`, `/design-lint` before merging. ✓
