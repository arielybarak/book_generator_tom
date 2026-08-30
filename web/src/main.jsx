import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { ErrorBoundary } from './components/ErrorBoundary.jsx'
import { LanguageProvider } from './lib/i18n.jsx'
import { AuthProvider } from './lib/auth.jsx'
import { reloadOnceForStaleBuild, clearStaleReloadFlag } from './lib/reload.js'

// Vite fires this when a dynamic import's preload 404s — i.e. this tab is on a
// build that's been replaced by a deploy. Reload once to get the fresh chunks.
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault()
  reloadOnceForStaleBuild()
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <LanguageProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </LanguageProvider>
    </ErrorBoundary>
  </StrictMode>,
)

// We rendered successfully, so any stale-build reload has resolved. Clear the
// guard so a future deploy (this same tab session) can self-heal again.
clearStaleReloadFlag()
