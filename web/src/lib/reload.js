/**
 * Self-heal after a deploy.
 *
 * Every build renames its hashed chunks (index-<hash>.js, DownloadStep-<hash>.js).
 * After we deploy, the OLD hashes 404 on the production domain. A browser that
 * still holds an old tab or a cached index.html then fails to load a chunk and
 * the page breaks (blank screen, or a lazy step that won't open).
 *
 * The cure is always the same: reload once to pull the fresh index.html + hashes.
 * These helpers detect that specific failure and reload a single time, guarded by
 * sessionStorage so a genuinely-broken build can never loop-reload forever.
 */

// One shared guard key across every reload path (ErrorBoundary, vite:preloadError,
// and the inline <script> in index.html — keep that copy in sync with this string).
const RELOAD_GUARD_KEY = 'tom_stale_reload'

/** True if `error` looks like a failed dynamic-import / chunk load, across browsers. */
export function isChunkLoadError(error) {
  if (!error) return false
  if (error.name === 'ChunkLoadError') return true
  const msg = typeof error === 'string' ? error : error.message || ''
  return (
    /failed to fetch dynamically imported module/i.test(msg) ||
    /error loading dynamically imported module/i.test(msg) ||
    /importing a module script failed/i.test(msg) ||
    /'text\/html'.*is not a valid JavaScript MIME type/i.test(msg)
  )
}

/**
 * Reload the page once to recover from a stale build. Returns true if it triggered
 * a reload. Fail-closed: if sessionStorage is unavailable (private mode, etc.) we do
 * NOT reload, since without the guard we could loop.
 */
export function reloadOnceForStaleBuild() {
  try {
    if (sessionStorage.getItem(RELOAD_GUARD_KEY)) return false
    sessionStorage.setItem(RELOAD_GUARD_KEY, '1')
  } catch {
    return false
  }
  window.location.reload()
  return true
}

/** Clear the guard once the app has mounted OK, so a later deploy can self-heal too. */
export function clearStaleReloadFlag() {
  try {
    sessionStorage.removeItem(RELOAD_GUARD_KEY)
  } catch {
    /* ignore */
  }
}
