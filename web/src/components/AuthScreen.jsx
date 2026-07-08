import { useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { useLang } from '../lib/i18n'
import { Button } from './ui/Button'
import { Card } from './ui/Card'

const USERNAME_RE = /^[a-z0-9_.-]{3,}$/i

export function AuthScreen() {
  const { t } = useLang()
  const { signIn, signUp } = useAuth()
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const usernameRef = useRef(null)

  const isLogin = mode === 'login'

  function validateLocal() {
    if (!USERNAME_RE.test(username)) return t.auth.errorUsername
    if (password.length < 6) return t.auth.errorPassword
    return null
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    const local = validateLocal()
    if (local) { setError(local); return }
    setBusy(true)
    try {
      const { error: err } = isLogin
        ? await signIn(username, password)
        : await signUp(username, password)
      if (err) setError(isLogin ? t.auth.errorInvalid : t.auth.errorSignup)
      // on success: onAuthStateChange in AuthProvider updates session → App re-renders
    } finally {
      setBusy(false)
    }
  }

  function switchMode() {
    setMode(isLogin ? 'signup' : 'login')
    setError('')
    usernameRef.current?.focus()
  }

  return (
    <section className="mx-auto max-w-md px-6 py-10">
      <Card className="p-6">
        <h2 className="text-ink mb-6 text-2xl font-bold">
          {isLogin ? t.auth.loginTitle : t.auth.signupTitle}
        </h2>

        <form onSubmit={submit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="auth-username" className="text-ink mb-1 block font-semibold">
              {t.auth.username}
            </label>
            <input
              ref={usernameRef}
              id="auth-username"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-invalid={!!error}
              className="border-line bg-surface focus:border-brand w-full rounded-2xl border px-4 py-3 text-lg outline-none"
            />
          </div>

          <div>
            <label htmlFor="auth-password" className="text-ink mb-1 block font-semibold">
              {t.auth.password}
            </label>
            <input
              id="auth-password"
              type="password"
              autoComplete={isLogin ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={!!error}
              className="border-line bg-surface focus:border-brand w-full rounded-2xl border px-4 py-3 text-lg outline-none"
            />
          </div>

          {error && (
            <p role="alert" aria-live="polite" className="text-sm text-red-600">
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={busy} className="w-full">
            {busy ? '…' : isLogin ? t.auth.loginCta : t.auth.signupCta}
          </Button>
        </form>

        <p className="text-muted mt-4 text-center text-sm">
          <button type="button" onClick={switchMode} className="text-accent hover:underline">
            {isLogin ? t.auth.toggleToSignup : t.auth.toggleToLogin}
          </button>
        </p>
      </Card>
    </section>
  )
}
