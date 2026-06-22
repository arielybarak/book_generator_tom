/**
 * Thin wrapper around @gradio/client → the HF Space's /generate_page endpoint.
 *
 * The Space (gradio_app_lithophane.py) exposes a hidden, stable endpoint named
 * "generate_page" that takes (raw_text, variations, image_desc, object_class) and
 * returns [image, stl] as served file URLs. We connect once and reuse the client.
 */
import { Client } from '@gradio/client'

const SPACE = import.meta.env.VITE_HF_SPACE || 'MLightning/text2STL-engine-2.0-superMX-bottom'

// ── HF Spaces CORS workaround ────────────────────────────────────────────────
// @gradio/client hardcodes `credentials: 'include'` on its requests. HF's edge
// layer answers the CORS *preflight* for *.hf.space without
// `Access-Control-Allow-Credentials: true`, so the browser rejects every
// credentialed cross-origin request and the client can't even connect. A public
// Space needs no credentials, so strip them for cross-origin Space requests.
// (EventSource/SSE already defaults to no credentials, so only fetch needs this.)
if (typeof window !== 'undefined' && !window.__hfFetchPatched) {
  const _fetch = window.fetch.bind(window)
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url
    if (url && url.includes('.hf.space')) init = { ...init, credentials: 'omit' }
    return _fetch(input, init)
  }
  window.__hfFetchPatched = true
}

let _clientPromise = null

async function connectWithRetry(onStatus, attempts = 8, delayMs = 5000) {
  for (let i = 0; i < attempts; i++) {
    try {
      return await Client.connect(SPACE)
    } catch (err) {
      const sleeping = err?.message?.includes('config') || err?.message?.includes('503')
      if (!sleeping || i === attempts - 1) throw err
      onStatus?.({ type: 'status', stage: 'waking', queue: false, position: 0 })
      await new Promise((r) => setTimeout(r, delayMs))
    }
  }
}

function getClient(onStatus) {
  if (!_clientPromise) {
    _clientPromise = connectWithRetry(onStatus).catch((err) => {
      _clientPromise = null
      throw err
    })
  }
  return _clientPromise
}

/** A Gradio file output can be a {url}, a {path}, or a bare string. Normalize to a URL. */
function fileUrl(item) {
  if (!item) return null
  if (typeof item === 'string') return item
  return item.url || item.path || null
}

/**
 * Generate one page on the backend.
 *
 * @param {{text:string, variations?:object, imageDesc?:string, objectClass?:string}} page
 * @param {(status:object)=>void} [onStatus]  receives queue/progress status messages
 * @returns {Promise<{imageUrl:string|null, stlUrl:string|null}>}
 */
async function _run({ text, variations, imageDesc, objectClass }, onStatus) {
  const client = await getClient(onStatus)

  // Positional payload in the endpoint's wired input order.
  const job = client.submit('/generate_page', [text, variations, imageDesc, objectClass])

  let data = null
  for await (const msg of job) {
    if (msg.type === 'status') onStatus?.(msg)
    else if (msg.type === 'data') data = msg.data
  }

  if (!Array.isArray(data)) throw new Error('No data returned from /generate_page')
  const [image, stl] = data
  return { imageUrl: fileUrl(image), stlUrl: fileUrl(stl) }
}

export async function generatePage(
  { text, variations = {}, imageDesc = '', objectClass = '' },
  onStatus,
) {
  const args = { text, variations, imageDesc, objectClass }
  try {
    return await _run(args, onStatus)
  } catch {
    // The cached client may be stale (Space restarted/died). Drop it and reconnect once.
    _clientPromise = null
    return await _run(args, onStatus)
  }
}
