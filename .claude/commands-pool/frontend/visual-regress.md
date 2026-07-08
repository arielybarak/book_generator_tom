---
description: >-
  Screenshot every TOM route in dir=rtl AND dir=ltr at mobile+desktop widths and diff against
  committed baselines. Catches RTL/LTR mirror bugs (text-right vs text-start, arrow direction,
  corner placement). USE after any layout/CSS change or before adding new screens.
argument-hint: "[--update-baselines] [--contact-sheet]"
---

# /visual-regress — dual-direction visual regression

RTL/LTR mirror bugs recur in TOM (`text-right`→`text-start`, `←/→` arrows, header corner
placement). This command screenshots every route in both directions at two widths, diffs against
committed baselines, and optionally produces a side-by-side contact sheet.

**Prerequisite:** headless Chromium (see `/web-verify`).

**$ARGUMENTS**
- `--update-baselines` = accept current screenshots as new golden (use after intentional design change)
- `--contact-sheet` = produce `visual-regress/contact-<date>.png` side-by-side he/en comparison

## Baseline directory

```
web/test-baselines/
  <route-slug>-he-mobile.png
  <route-slug>-he-desktop.png
  <route-slug>-en-mobile.png
  <route-slug>-en-desktop.png
```

Commit the baseline PNGs. Routes with generate output: use the **checked-in fixture** image
(`web/test-baselines/fixtures/generate-output.png`) — do NOT screenshot live SD output (it
varies per run and churns the diff). Point the baseline at the fixture for generate/download routes.

## Playwright script

```js
// web/tools/visual-regress.mjs
import { chromium } from 'playwright';
import { execSync } from 'child_process';
import { mkdirSync, existsSync, copyFileSync } from 'fs';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const ROUTES = ['/', '/create', '/preview'];
const VIEWPORTS = [
  { name: 'mobile',   width: 390,  height: 844 },
  { name: 'desktop',  width: 1280, height: 900 },
];
const UPDATE = process.argv.includes('--update-baselines');

mkdirSync('web/test-screenshots/regress', { recursive: true });
const browser = await chromium.launch({ headless: true });
let diffs = 0;

for (const lang of ['he', 'en']) {
  for (const vp of VIEWPORTS) {
    for (const route of ROUTES) {
      const page = await browser.newPage({ viewport: vp });
      await page.goto(`${BASE}${route}?lang=${lang}`);
      await page.waitForLoadState('networkidle');

      // Freeze animations so screenshots are deterministic
      await page.addStyleTag({ content: '*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }' });

      const slug = route.replace(/\//g, '_') || '_home';
      const name = `${slug}-${lang}-${vp.name}`;
      const current = `web/test-screenshots/regress/${name}.png`;
      const baseline = `web/test-baselines/${name}.png`;

      await page.screenshot({ path: current, fullPage: true });

      if (UPDATE) {
        mkdirSync('web/test-baselines', { recursive: true });
        copyFileSync(current, baseline);
        console.log(`[UPDATED] ${name}`);
      } else if (existsSync(baseline)) {
        // pixelmatch diff via ImageMagick compare (stdlib-friendly)
        const result = execSync(
          `convert ${baseline} ${current} -metric AE -compare -format "%[distortion]" info: 2>&1 || true`
        ).toString().trim();
        const diffPx = parseFloat(result) || 0;
        if (diffPx > 50) {
          console.error(`[FAIL] ${name}: ${diffPx} pixel diff`);
          diffs++;
        } else {
          console.log(`[OK] ${name}: ${diffPx}px diff`);
        }
      } else {
        console.warn(`[SKIP] ${name}: no baseline — run with --update-baselines first`);
      }
      await page.close();
    }
  }
}

await browser.close();
if (diffs) process.exit(1);
```

## Contact sheet (--contact-sheet)

After screenshots are taken, produce a side-by-side grid with ImageMagick:

```bash
convert +append \
  web/test-screenshots/regress/_home-he-mobile.png \
  web/test-screenshots/regress/_home-en-mobile.png \
  web/test-screenshots/regress/_home-he-desktop.png \
  web/test-screenshots/regress/_home-en-desktop.png \
  web/visual-regress/contact-$(date +%Y%m%d).png
```

The contact sheet lets a human eyeball "does the English mirror look right?" in one image.
Particularly useful when reviewing new screen builds (auth, library) before merging.

## When to update baselines

Only after an **intentional** design change: new brand color, component redesign, layout shift.
Not after fixing a mirror bug — the fix should bring screenshots back to the existing baseline.
