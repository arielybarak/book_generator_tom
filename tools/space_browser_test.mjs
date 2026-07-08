/**
 * Browser E2E test for TOM's HF Space — drives a real Chromium instance so the
 * request origin matches the live Vercel site, exercising the CORS path and the
 * credentials-strip fetch shim in hfClient.js.
 *
 * Defaults to `slow_ping` (CPU, 22 s) so the test costs zero GPU quota.
 * Pass `--gpu` to call `generate_page` instead (burns ZeroGPU; owner's rule: don't).
 *
 * ## Run (from web/)
 *
 *   LD_LIBRARY_PATH=/tmp/alsa_extract/usr/lib/x86_64-linux-gnu \
 *     node --input-type=module < ../tools/space_browser_test.mjs
 *
 * Or with a GPU run:
 *   GPU=true LD_LIBRARY_PATH=/tmp/alsa_extract/usr/lib/x86_64-linux-gnu \
 *     node --input-type=module < ../tools/space_browser_test.mjs
 *
 * ## Prerequisites (ephemeral — recreate in a fresh env)
 *
 *   # Playwright + Chromium (in web/ or /tmp):
 *   cd /tmp && npm install playwright && npx playwright install chromium
 *
 *   # System libs for Chromium on WSL/headless Linux:
 *   mkdir -p /tmp/alsa_extract && cd /tmp/alsa_extract
 *   apt-get download libasound2 2>/dev/null || true
 *   dpkg-deb -x libasound2*.deb . 2>/dev/null || true
 *
 * Both /tmp directories are ephemeral — redo after a session restart.
 */

import { chromium } from '/tmp/node_modules/playwright/index.mjs'

const ROOT = 'https://mlightning-text2stl-engine-2-0-supermx-bottom.hf.space'
const SITE = 'https://book-generator-tom.vercel.app'
const USE_GPU = process.env.GPU === 'true'
const ENDPOINT = USE_GPU ? 'generate_page' : 'slow_ping'

// Inputs for each endpoint.  generate_page needs Hebrew text + variations.
const INPUTS = USE_GPU
  ? ['שלום', {}, 'a simple flower', 'flower']  // minimal valid page
  : []                                           // slow_ping takes no inputs

console.log(`[space_browser_test] endpoint: ${ENDPOINT}  gpu: ${USE_GPU}`)
console.log(`[space_browser_test] launching Chromium (headless)…`)

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ baseURL: SITE })
const page = await ctx.newPage()

// Navigate to the real site so the request origin is the live Vercel domain.
// This activates the credentials-strip fetch shim from hfClient.js (window.__hfFetchPatched).
page.on('console', msg => console.log('[browser]', msg.text()))
page.on('pageerror', err => console.error('[browser-err]', err.message))

await page.goto(SITE, { waitUntil: 'networkidle', timeout: 30_000 })
console.log('[space_browser_test] page loaded — origin:', new URL(SITE).origin)

// Run the 2-step Gradio REST call inside the browser context (real origin + CORS shim).
const result = await page.evaluate(
  async ({ ROOT, ENDPOINT, INPUTS }) => {
    const timeout = (ENDPOINT === 'generate_page') ? 8 * 60_000 : 60_000
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeout)

    try {
      // Step 1 — enqueue
      const postRes = await fetch(`${ROOT}/gradio_api/call/${ENDPOINT}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: INPUTS }),
        signal: controller.signal,
      })
      if (!postRes.ok) return { ok: false, error: `POST ${postRes.status}` }
      const { event_id: eventId } = await postRes.json()

      // Step 2 — stream result
      const sseRes = await fetch(`${ROOT}/gradio_api/call/${ENDPOINT}/${eventId}`, {
        signal: controller.signal,
      })
      if (!sseRes.ok || !sseRes.body) return { ok: false, error: `GET ${sseRes.status}` }

      const reader = sseRes.body.getReader()
      const dec = new TextDecoder()
      let buf = '', lastEvent = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let nl
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).replace(/\r$/, '')
          buf = buf.slice(nl + 1)
          if (line.startsWith('event:')) lastEvent = line.slice(6).trim()
          else if (line.startsWith('data:')) {
            if (lastEvent === 'complete') return { ok: true, data: line.slice(5).trim() }
            if (lastEvent === 'error')    return { ok: false, error: line.slice(5).trim() }
          }
        }
      }
      return { ok: false, error: 'stream ended before complete' }
    } finally {
      clearTimeout(timer)
    }
  },
  { ROOT, ENDPOINT, INPUTS },
)

await browser.close()

if (result.ok) {
  console.log(`[space_browser_test] PASS — ${ENDPOINT} complete`)
  console.log('[space_browser_test] data (first 200 chars):', result.data?.slice(0, 200))
} else {
  console.error(`[space_browser_test] FAIL — ${ENDPOINT}:`, result.error)
  process.exitCode = 1
}
