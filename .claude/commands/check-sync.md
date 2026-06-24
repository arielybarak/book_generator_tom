---
description: >-
  Report TOM's three deploy drift points: hf_space/ vs src/+config.yaml sync, nikud keys
  parity, and web/src/lib/copy.js i18n key parity (hebrew vs english). Read-only. USE before
  any HF or Vercel push, or when UI shows undefined for a language string.
argument-hint: ""
---

Report whether TOM's three known drift points are clean. **Read-only — do not run
`sync_to_space.sh`, do not edit anything.** Summarize findings as PASS/DRIFT per check.

**Check 1 — hf_space/ vendored copy vs source of truth.** The deploy ships `hf_space/`, which
vendors a copy of `src/` + `config.yaml`; if they differ, a deploy would be stale (or the copy
was edited directly, which is forbidden — see [[hf-space-sync-deploy]]).
- !`cd "$CLAUDE_PROJECT_DIR" && diff -rq --exclude=__pycache__ src/ hf_space/src/ ; echo "config:"; diff -q config.yaml hf_space/config.yaml`
- Any output = DRIFT (run `/deploy-hf` to resync). No output = PASS.

**Check 2 — nikud key parity (backend ↔ frontend).** The option keys in `SPECIAL_REPLACEMENTS`
(`src/language_funcs.py`) must match `DISPLAY_MAPPING` and the `key:` values in
`web/src/lib/nikud.js`; a mismatch means a UI choice is silently dropped (see [[hebrew-braille-nikud]]).
- Backend keys: !`grep -oE "'(default|holam|shuruk|shin|sin|dagesh)'" "$CLAUDE_PROJECT_DIR/src/language_funcs.py" | sort -u`
- Frontend keys: !`grep -oE "key: '[a-z]+'" "$CLAUDE_PROJECT_DIR/web/src/lib/nikud.js" | sort -u`
- Compare the two sets. Equal = PASS; any key on one side only = DRIFT.

**Check 3 — i18n copy key parity (`web/src/lib/copy.js`).** `copy.js` exports `{ hebrew, english }`
(or equivalent locale keys); every key present in `hebrew` must exist in `english` and vice-versa.
A missing key renders as `undefined` in the UI (no error thrown — silently broken string).
- !`node -e "const c=require('./web/src/lib/copy.js'); const hk=new Set(Object.keys(c.hebrew||{})); const ek=new Set(Object.keys(c.english||{})); const onlyH=[...hk].filter(k=>!ek.has(k)); const onlyE=[...ek].filter(k=>!hk.has(k)); if(onlyH.length||onlyE.length){console.log('DRIFT — only in hebrew:',onlyH,'only in english:',onlyE);}else{console.log('PASS — key sets equal, count:',hk.size);}" 2>/dev/null || echo "copy.js not found or not CommonJS — read the file and diff key sets manually."`
- If the file uses ES module syntax (`export const`), read it directly and diff the key lists.
- DRIFT = add the missing key with a placeholder value, then have a translator fill it.

End with a one-line verdict per check and the exact fix for any DRIFT.
