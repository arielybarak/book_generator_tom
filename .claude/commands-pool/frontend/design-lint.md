---
description: >-
  Lint TOM's design-system constraints: raw hex/ad-hoc spacing not using src/index.css @theme
  tokens, and banned jargon (STL/generate/nikud/חולם) in copy.js. USE before adding new
  components or screens to keep visual consistency and warm parent-facing tone.
argument-hint: ""
---

# /design-lint — design-system + no-jargon guard

TOM has two hard constraints documented in `web/CLAUDE.md` that nothing currently enforces:

1. **Design tokens are the single source of look** — defined in `src/index.css @theme`; raw
   hex colors or ad-hoc spacing that bypass tokens make the visual system inconsistent.
2. **No-jargon tone** — users are parents of blind children, not developers. Banned terms must
   never appear in `copy.js` (what users read). Technical terms belong only in code comments.

## Scan 1 — raw hex / ad-hoc values in JSX + CSS

```bash
# Raw hex colors in JSX/CSS (should use var(--color-*) tokens)
grep -rn --include="*.jsx" --include="*.tsx" --include="*.css" \
  -E '#[0-9a-fA-F]{3,6}\b|rgb\(|rgba\(' web/src/ \
  | grep -v '// token-ok' | grep -v 'node_modules'
```

```bash
# Ad-hoc pixel values not from tokens (spacing > 4px not on the Tailwind scale)
grep -rn --include="*.css" \
  -E '[0-9]{2,}px' web/src/index.css \
  | grep -v '@theme' | grep -v '// spacing-ok'
```

Any hex/rgb match = likely missing token. Cross-check `src/index.css @theme` first — if the
color is already defined as `--color-brand: #xyz`, use `var(--color-brand)` / `bg-brand` not
the raw hex. Add a `// token-ok` comment only when a raw value is genuinely unavoidable (e.g.
a third-party embed that requires inline style).

## Scan 2 — banned jargon in copy.js

TOM's glossary (from `web/CLAUDE.md`):

| Banned | Allowed instead |
|---|---|
| STL / stl | הקובץ להדפסה (the print file) |
| generate / יצור | יוצרים (we create) |
| nikud / ניקוד | סימני ניקוד if unavoidable |
| חולם / שורוק / דגש | the actual vowel symbol, never the name |
| object_class | (internal only, never user-facing) |

```bash
grep -in 'stl\|generat\|nikud\|ניקוד\|חולם\|שורוק\|דגש\|object_class' \
  web/src/lib/copy.js
```

Any match = jargon leak. Replace with the glossary equivalent and note the mapping in
`web/CLAUDE.md` for future contributors.

## Scan 3 — component token usage (spot check)

```bash
# New components that introduce color classes not in the token list
TOKEN_CLASSES=$(grep -oP '(?<=@theme \{)[^}]+' web/src/index.css | grep -oP '--\w+' | sed 's/--color-/bg-/;s/--//')
grep -rn --include="*.jsx" 'className=' web/src/components/ \
  | grep -E 'text-#|bg-#|border-#' | grep -v '// token-ok'
```

## Report

```
Scan 1 — raw hex/spacing: N hits (list)
Scan 2 — jargon in copy.js: N hits (list terms + lines)
Scan 3 — component token check: N hits

Overall: PASS / FAIL
```

PASS = consistent design, warm tone. Add to `/preflight --web` once clean.
