/* global process */
/**
 * Vercel serverless function — enqueue a page generation on the HF Space using a
 * SERVER-SIDE HF token, so the public site runs on the owner's PRO ZeroGPU quota
 * instead of the (tiny, anonymous) pool. The browser calls this same-origin; the
 * token never reaches the client.
 *
 * Only the enqueue (POST) needs the token — ZeroGPU attributes the job to the
 * authenticated POST. The browser then streams the result GET itself (that GET
 * works without auth), so this function stays fast (<1s) and can't hit a timeout.
 *
 * Env: HF_TOKEN (required, a PRO account token), HF_SPACE (optional, defaults below).
 */
const SPACE = process.env.HF_SPACE || 'MLightning/text2STL-engine-2.0-superMX-bottom'
const SLUG = SPACE.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
const ROOT = `https://${SLUG}.hf.space`

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method_not_allowed' })
    return
  }
  const token = process.env.HF_TOKEN
  if (!token) {
    res.status(500).json({ error: 'server_misconfigured', detail: 'HF_TOKEN is not set' })
    return
  }
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {}
    const { raw_text = '', variations = {}, image_desc = '', object_class = '', language = 'hebrew' } = body

    const r = await fetch(`${ROOT}/gradio_api/call/generate_page`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ data: [raw_text, variations, image_desc, object_class, language] }),
    })
    if (!r.ok) {
      res.status(502).json({ error: 'enqueue_failed', status: r.status })
      return
    }
    const { event_id: eventId } = await r.json()
    if (!eventId) {
      res.status(502).json({ error: 'no_event_id' })
      return
    }
    // Browser streams the result from {root}/gradio_api/call/generate_page/{event_id}.
    res.status(200).json({ event_id: eventId, root: ROOT })
  } catch (e) {
    res.status(502).json({ error: 'proxy_error', detail: String(e?.message || e) })
  }
}
