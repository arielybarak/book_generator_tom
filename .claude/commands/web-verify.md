---
description: >-
  Boot the React dev server and drive headless Chromium through TOM's 4-step create flow,
  screenshotting key states. Prerequisites: npx playwright install --with-deps chromium (once).
  USE WHEN verifying UI changes work end-to-end without a live HF Space.
argument-hint: "[--prod] [--screenshot-dir DIR]"
---

# /web-verify — browser harness

Boots the frontend and drives a real browser through TOM's 4-step flow. Everything in F2–F6
depends on this running. **Prerequisite (once per env):**
```bash
npx playwright install --with-deps chromium
```
Without `--with-deps`, bundled Chromium fails on `libasound2` absent in many WSL/CI envs.

**$ARGUMENTS** = `[--prod] [--screenshot-dir DIR]`
- `--prod` = serve `dist/` (after `npm run build`) instead of dev server — catches build-only bugs
- `--screenshot-dir DIR` = where to save screenshots (default: `web/test-screenshots/`)

## Steps

**Step 1 — start the dev server (unless --prod)**
```bash
cd web
npm run dev &
DEV_PID=$!
# wait until listening
until curl -sf http://localhost:5173/ -o /dev/null; do sleep 1; done
BASE_URL=http://localhost:5173
```

For `--prod`: `npm run build && npx serve dist -p 4173 &` → `BASE_URL=http://localhost:4173`.

**Step 2 — run the Playwright script**

```js
// web/tools/web-verify.mjs
import { chromium } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const SHOT_DIR = process.env.SHOT_DIR ?? 'test-screenshots';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// 4-step flow: Hebrew and English
for (const lang of ['he', 'en']) {
  await page.goto(`${BASE}?lang=${lang}`);
  await page.screenshot({ path: `${SHOT_DIR}/01-landing-${lang}.png` });

  // Step 1: enter text
  await page.fill('[data-testid="text-input"]', lang === 'he' ? 'פרח' : 'flower');
  await page.screenshot({ path: `${SHOT_DIR}/02-text-entered-${lang}.png` });

  // Step 2: image description
  await page.fill('[data-testid="image-desc"]', 'a simple flower');
  await page.screenshot({ path: `${SHOT_DIR}/03-desc-entered-${lang}.png` });

  // Step 3: check no visible Hebrew jargon / STL mentions
  const body = await page.textContent('body');
  if (/STL|nikud|חולם|שורוק|דגש/.test(body)) {
    console.error(`[FAIL] jargon visible in ${lang} UI`);
    process.exitCode = 1;
  }

  console.log(`[OK] ${lang} 3-step flow reached`);
}

// Check RTL direction applied for Hebrew
await page.goto(`${BASE}?lang=he`);
const dir = await page.getAttribute('html', 'dir');
console.assert(dir === 'rtl', `[FAIL] html dir=${dir} for Hebrew`);

await browser.close();
```

```bash
BASE_URL=$BASE_URL SHOT_DIR=${SCREENSHOT_DIR:-web/test-screenshots} node web/tools/web-verify.mjs
kill $DEV_PID 2>/dev/null
```

**Step 3 — report**
List screenshots saved. Any `[FAIL]` line = report it and the fix. The screenshots in
`test-screenshots/` are the quick human visual check — open them if anything seems off.

Note: the generate step (Step 4) is NOT driven here — it requires a live Space + GPU quota. Use
`/gen-probe` for that. The harness verifies UI flow and static content only.
