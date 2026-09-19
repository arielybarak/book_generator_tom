import { useEffect, useRef } from 'react'

/**
 * Cloudflare Turnstile — a free, privacy-friendly CAPTCHA that proves a real user
 * (not a bot) is signing in. Supabase Auth verifies the token server-side when
 * CAPTCHA protection is enabled in the dashboard, so there's no custom verify step.
 *
 * Off until configured: with no VITE_TURNSTILE_SITE_KEY the widget renders nothing
 * and auth behaves exactly as before — so enabling it is a two-step, non-breaking
 * rollout (ship the key first, turn on Supabase CAPTCHA second).
 *
 * Remount with a changing `key` to reset the challenge (tokens are single-use — get
 * a fresh one after each failed sign-in attempt).
 */
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

// eslint-disable-next-line react-refresh/only-export-components
export const captchaEnabled = Boolean(SITE_KEY)

let scriptPromise = null
function loadScript() {
  if (typeof window !== 'undefined' && window.turnstile) return Promise.resolve()
  if (scriptPromise) return scriptPromise
  scriptPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = SCRIPT_SRC
    s.async = true
    s.defer = true
    s.onload = () => resolve()
    s.onerror = () => reject(new Error('turnstile script failed to load'))
    document.head.appendChild(s)
  })
  return scriptPromise
}

export function Turnstile({ onToken }) {
  const boxRef = useRef(null)
  const widgetIdRef = useRef(null)

  useEffect(() => {
    if (!SITE_KEY) return
    let cancelled = false
    loadScript()
      .then(() => {
        if (cancelled || !boxRef.current || !window.turnstile) return
        widgetIdRef.current = window.turnstile.render(boxRef.current, {
          sitekey: SITE_KEY,
          callback: (token) => onToken(token),
          'expired-callback': () => onToken(''),
          'error-callback': () => onToken(''),
        })
      })
      .catch(() => onToken(''))
    return () => {
      cancelled = true
      if (widgetIdRef.current && window.turnstile) {
        try {
          window.turnstile.remove(widgetIdRef.current)
        } catch {
          /* widget already gone */
        }
      }
    }
  }, [onToken])

  if (!SITE_KEY) return null
  return <div ref={boxRef} className="flex justify-center" />
}
