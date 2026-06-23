---
description: >-
  Report TOM's two deploy drift points: hf_space/ vs src/+config.yaml sync, and
  SPECIAL_REPLACEMENTS keys vs web/src/lib/nikud.js. Read-only.
argument-hint: ""
---

Report whether TOM's two known drift points are clean. **Read-only — do not run
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
- Compare the two sets and the per-letter coverage. Read @src/language_funcs.py and @web/src/lib/nikud.js if a key looks off. Equal sets = PASS; any key on one side only = DRIFT.

End with a one-line verdict and the exact fix for any DRIFT.
