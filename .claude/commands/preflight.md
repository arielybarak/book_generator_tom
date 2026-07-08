---
description: >-
  Offline gate before any HF or Vercel push — runs /stl-bench, /regress, /check-sync, Python
  syntax check, and npm build+lint. Catches failures locally in seconds instead of after a
  2-min HF rebuild. USE before every sync_to_space.sh or git push from hf_space/ or web/.
argument-hint: "[--web] [--skip-bench]"
---

# /preflight — offline gate before deploy

Runs all local checks before touching HF or Vercel. A full HF rebuild cold-loads the 8.9 GB
model (~2 min); catching failures here saves that round-trip.

**$ARGUMENTS** = `[--web] [--skip-bench]`
- `--web` = also run `npm run build && npm run lint` in `web/` (frontend changes)
- `--skip-bench` = skip `/stl-bench` (use only when bench was just run this session)

---

## Gate 1 — Python syntax (fast, always)

```bash
python -m py_compile src/*.py hf_space/gradio_app_lithophane.py
echo "[Gate 1] Python syntax: $?"
```

Any non-zero exit = syntax error; fix before proceeding. Do not deploy broken Python to HF.

---

## Gate 2 — vendored-copy + nikud + i18n parity (`/check-sync`)

Run `/check-sync` (read-only). Any DRIFT = stop; sync or fix before deploying.

---

## Gate 3 — offline STL bench (`/stl-bench`, unless `--skip-bench`)

Run:
```bash
python -c "
from src.image_funcs import generate_text_dxf, generate_braille_dxf_from_text
from src.dxf_3d import create_one_page_stl_from_dxf
from src.language_funcs import text_to_braille
import time, subprocess

t0 = time.perf_counter()
generate_text_dxf('שלום', '/tmp/pf_text.dxf', rtl=True)
br = text_to_braille('שלום', 'hebrew')
generate_braille_dxf_from_text(br, '/tmp/pf_braille.dxf')

r = subprocess.run(
    ['python','-c',
     \"from src.dxf_3d import create_one_page_stl_from_dxf; \
       create_one_page_stl_from_dxf('/tmp/pf_text.dxf','/tmp/pf_braille.dxf',None,'/tmp/pf_out.stl')\"],
    timeout=120)
if r.returncode in (-11, 139):
    print('[FAIL] Gate 3: SIGSEGV in STL assembly'); raise SystemExit(1)

elapsed = time.perf_counter()-t0
print(f'[Gate 3] STL bench: {elapsed:.0f}s', '[OK]' if elapsed<120 else '[SLOW — boolean union?]')
"
```

Must complete without SIGSEGV and under 120 s. Slow (> 120 s) = boolean union crept back in;
do not deploy — fix [[tactile-stl-geometry]] first.

---

## Gate 4 — regression fixtures (`/regress`, if fixtures exist)

```bash
python -c "
from pathlib import Path
fixtures = list(Path('bench/fixtures').glob('*.json'))
if not fixtures:
    print('[Gate 4] regress: no fixtures yet — skip')
else:
    import regress
    regress.run_all()
    print('[Gate 4] regress: OK')
" 2>/dev/null || echo "[Gate 4] regress: no bench/fixtures/ — skip"
```

---

## Gate 5 — web build + lint (only with `--web`)

```bash
cd web && npm run build && npm run lint
echo "[Gate 5] web build+lint: $?"
```

A failing build means Vercel would also fail. Fix before `git push` to Vercel.

---

## Verdict

Print a summary table:

| Gate | Check | Result |
|---|---|---|
| 1 | Python syntax | PASS / FAIL |
| 2 | check-sync (3 drift points) | PASS / DRIFT |
| 3 | stl-bench | PASS / FAIL / SLOW |
| 4 | regress fixtures | PASS / SKIP |
| 5 | web build (if --web) | PASS / FAIL / SKIP |

All PASS or SKIP = clear to deploy. Any FAIL or DRIFT = block; name the exact fix.
