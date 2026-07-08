---
description: >-
  Static scan for hardcoded Hebrew/English literals in JSX that bypass t., physical-direction
  Tailwind utilities (text-left/right, ml-/mr-, left-/right-) that should be logical, and
  copy.js key parity. USE after any JSX edit or before adding a new language.
argument-hint: ""
---

# /i18n-lint — string coverage and direction-utility scan

Two bugs TOM keeps shipping: hardcoded strings that bypass the i18n system, and physical
Tailwind direction utilities that break the RTL/LTR mirror. Both are cheap static scans.

## Scan 1 — hardcoded strings in JSX

Flags Hebrew (`֐–׿`) or English literals that appear as JSX text nodes or `aria-label` values
without going through the `t.` (or `copy.js`) accessor:

```bash
# Hebrew literals in JSX (not inside t.` or copy.)
grep -rn --include="*.jsx" --include="*.tsx" \
  '[֐-׿]' web/src/ | grep -v '\.test\.' | grep -v '//'
```

Any match = hardcoded Hebrew string in JSX. Cross-check: is it in `copy.js`? If not, add it.

```bash
# aria-label with a Hebrew string (should reference t.someKey)
grep -rn --include="*.jsx" --include="*.tsx" \
  'aria-label="[֐-׿]' web/src/
```

```bash
# Common hardcoded English UI text (adjust list as needed)
grep -rn --include="*.jsx" --include="*.tsx" \
  -E '"(Create|Generate|Download|Upload|Next|Back|Submit)[^"]' web/src/ \
  | grep -v 'copy\.' | grep -v '// i18n-ok'
```

Mark intentional raw strings with `{/* i18n-ok: reason */}` to suppress future flags.

## Scan 2 — physical direction utilities (mirror bugs)

Physical Tailwind classes break when `dir` flips. Must use logical equivalents:

| Physical (banned) | Logical (required) |
|---|---|
| `text-left`, `text-right` | `text-start`, `text-end` |
| `ml-*`, `mr-*` | `ms-*`, `me-*` |
| `pl-*`, `pr-*` | `ps-*`, `pe-*` |
| `left-*`, `right-*` (positioning) | `start-*`, `end-*` |
| `←`, `→` (arrow literals) | RTL-conditional: `dir === 'rtl' ? '←' : '→'` |
| `border-l-*`, `border-r-*` | `border-s-*`, `border-e-*` |

```bash
grep -rn --include="*.jsx" --include="*.tsx" --include="*.css" \
  -E 'text-(left|right)|[mp][lr]-[0-9]|border-[lr]-|(^|\s)(left|right)-[0-9]|←|→' \
  web/src/ | grep -v '// rtl-ok'
```

Mark intentional physical usage (e.g. a decorative element that shouldn't mirror) with `// rtl-ok`.

## Scan 3 — copy.js key parity

```bash
# same as /check-sync Check 3 — run it here too for a complete i18n report
node -e "
const c=require('./web/src/lib/copy.js');
const hk=new Set(Object.keys(c.hebrew||{}));
const ek=new Set(Object.keys(c.english||{}));
const onlyH=[...hk].filter(k=>!ek.has(k));
const onlyE=[...ek].filter(k=>!hk.has(k));
if(onlyH.length||onlyE.length){
  console.error('DRIFT — only in hebrew:',onlyH,'only in english:',onlyE);process.exit(1);
} else { console.log('PASS — key sets equal, count:',hk.size); }
" 2>/dev/null || echo "copy.js not found or not CommonJS — inspect manually"
```

## Report format

```
Scan 1 — hardcoded strings: N hits (list files)
Scan 2 — physical direction utilities: N hits (list classes + files)
Scan 3 — copy.js parity: PASS / DRIFT

Overall: PASS (0 hits) / FAIL (fix before shipping)
```

Zero hits on all three = clean. Add to `/preflight --web`.
