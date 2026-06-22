/**
 * Backend client → the HF Space's plain REST endpoint `/api/generate`.
 *
 * Why not @gradio/client? The browser gradio client cannot drive a ZeroGPU job:
 * the GPU is scheduled only when the page asks huggingface.co for ZeroGPU auth
 * headers via the parent-iframe postMessage handshake. A standalone site (this
 * app) isn't in that iframe, so /generate_page submits but never gets a GPU and
 * the client hangs forever. The Space therefore also exposes a plain REST route
 * that runs the same pipeline server-side (it natively owns its ZeroGPU context)
 * and returns JSON. We hit it with a normal fetch — no queue, no SSE, no iframe.
 */
const SPACE = import.meta.env.VITE_HF_SPACE || 'MLightning/text2STL-engine-2.0-superMX-bottom'

// HF Space subdomain: owner/name lowercased, every non-alphanumeric run → "-".
const SLUG = SPACE.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
const ROOT = `https://${SLUG}.hf.space`

// ── HF Spaces CORS workaround ────────────────────────────────────────────────
// HF's edge layer answers the CORS *preflight* for *.hf.space without
// `Access-Control-Allow-Credentials: true`, so any credentialed cross-origin
// request is rejected. A public Space needs no credentials — strip them.
if (typeof window !== 'undefined' && !window.__hfFetchPatched) {
  const _fetch = window.fetch.bind(window)
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url
    if (url && url.includes('.hf.space')) init = { ...init, credentials: 'omit' }
    return _fetch(input, init)
  }
  window.__hfFetchPatched = true
}

const GENERATE_TIMEOUT_MS = 8 * 60 * 1000 // ZeroGPU cold start can take minutes

/** Poll the Space until it answers (it may be asleep). Emits a 'waking' status. */
async function wakeUp(onStatus, attempts = 10, delayMs = 5000) {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(`${ROOT}/api/health`, { method: 'GET' })
      if (res.ok) {
        const body = await res.json().catch(() => null)
        if (body?.ok) return
      }
    } catch {
      // network error / DNS not ready while the Space spins up — keep waiting
    }
    if (i === attempts - 1) break
    onStatus?.({ type: 'status', stage: 'waking', queue: true, position: 0 })
    await new Promise((r) => setTimeout(r, delayMs))
  }
}

/**
 * Generate one page on the backend.
 *
 * @param {{text:string, variations?:object, imageDesc?:string, objectClass?:string}} page
 * @param {(status:object)=>void} [onStatus]  receives status messages (e.g. 'waking')
 * @returns {Promise<{imageUrl:string|null, stlUrl:string|null}>}
 */
export async function generatePage(
  { text, variations = {}, imageDesc = '', objectClass = '' },
  onStatus,
) {
  await wakeUp(onStatus)
  onStatus?.({ type: 'status', stage: 'working' })

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), GENERATE_TIMEOUT_MS)
  let res
  try {
    res = await fetch(`${ROOT}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_text: text,
        variations,
        image_desc: imageDesc,
        object_class: objectClass,
      }),
      signal: controller.signal,
    })
  } finally {
    clearTimeout(timer)
  }

  let data
  try {
    data = await res.json()
  } catch {
    throw new Error(`Backend returned non-JSON (status ${res.status})`)
  }
  if (!res.ok || data?.error) {
    throw new Error(data?.detail || data?.error || `Generation failed (${res.status})`)
  }
  return { imageUrl: data.image_url || null, stlUrl: data.stl_url || null }
}
