/**
 * Backend client → the HF Space, via Gradio's built-in REST API (no @gradio/client).
 *
 * Why not @gradio/client? Its browser build can't drive a ZeroGPU job from a
 * standalone site: the GPU is scheduled only after a postMessage token handshake
 * with huggingface.co that only happens inside the HF iframe. Off-iframe, the GPU
 * job is submitted but never runs and the client hangs forever.
 *
 * Gradio also exposes a plain 2-step REST API for every endpoint, which is what the
 * (working) Python client uses under the hood and which needs no iframe handshake:
 *   POST /gradio_api/call/generate_page  {"data":[...]}   -> { event_id }
 *   GET  /gradio_api/call/generate_page/<event_id>        -> SSE: 'complete' + data
 * The GET is held open while the job runs; Gradio sends `event: heartbeat` to keep
 * the stream alive, then `event: complete` with the output files (URLs already
 * served thanks to the gr.File outputs).
 */
const SPACE = import.meta.env.VITE_HF_SPACE || 'MLightning/text2STL-engine-2.0-superMX-bottom'

// HF Space subdomain: owner/name lowercased, every non-alphanumeric run → "-".
const SLUG = SPACE.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
const ROOT = `https://${SLUG}.hf.space`
const ENDPOINT = 'generate_page'

// ── HF Spaces CORS workaround ────────────────────────────────────────────────
// HF's edge layer answers the CORS preflight for *.hf.space without
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

/** A Gradio file output is { url } | { path } | string. Normalize to a URL. */
function fileUrl(item) {
  if (!item) return null
  if (typeof item === 'string') return item
  return item.url || item.path || null
}

/** Poll until the Space answers (it may be asleep). Emits a 'waking' status. */
async function wakeUp(onStatus, attempts = 10, delayMs = 5000) {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(`${ROOT}/config`, { method: 'GET' })
      if (res.ok && (res.headers.get('content-type') || '').includes('json')) return
    } catch {
      // network error / DNS not ready while the Space spins up — keep waiting
    }
    if (i === attempts - 1) break
    onStatus?.({ type: 'status', stage: 'waking', queue: true, position: 0 })
    await new Promise((r) => setTimeout(r, delayMs))
  }
}

/** Read a Gradio /call SSE stream; resolve with the `complete` data, throw on `error`. */
async function readResultStream(url, signal) {
  const res = await fetch(url, { method: 'GET', signal })
  if (!res.ok || !res.body) throw new Error(`Result stream failed (status ${res.status})`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let event = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let nl
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl).replace(/\r$/, '')
      buffer = buffer.slice(nl + 1)
      if (line.startsWith('event:')) {
        event = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        const dataStr = line.slice(5).trim()
        if (event === 'complete') return JSON.parse(dataStr)
        if (event === 'error') {
          let detail = dataStr
          try {
            const p = JSON.parse(dataStr)
            detail = (Array.isArray(p) ? p[0] : p?.message) || dataStr
          } catch {
            /* keep raw */
          }
          throw new Error(typeof detail === 'string' ? detail : 'Generation failed')
        }
        // 'generating' / 'heartbeat' → ignore, keep reading
      }
    }
  }
  throw new Error('Result stream ended before completion')
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
  try {
    // 1) Enqueue via our serverless proxy, which adds a server-side HF token so the
    //    job runs on the owner's PRO ZeroGPU quota (the site can't carry a token).
    //    Same-origin call; the token never reaches the browser.
    const postRes = await fetch(`/api/generate`, {
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
    const enq = await postRes.json().catch(() => ({}))
    if (!postRes.ok || !enq.event_id) {
      throw new Error(enq.detail || enq.error || `Enqueue failed (status ${postRes.status})`)
    }
    const root = enq.root || ROOT

    // 2) Stream the result directly from the Space (no token needed for retrieval).
    const data = await readResultStream(`${root}/gradio_api/call/${ENDPOINT}/${enq.event_id}`, controller.signal)
    if (!Array.isArray(data)) throw new Error('Unexpected result shape from /generate_page')
    const [image, stl] = data
    return { imageUrl: fileUrl(image), stlUrl: fileUrl(stl) }
  } finally {
    clearTimeout(timer)
  }
}
