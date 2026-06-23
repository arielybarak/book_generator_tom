import { createContext, useContext, useEffect, useState } from 'react'
import { COPY } from './copy'

/**
 * App language (UI + generated content). 'hebrew' | 'english'.
 * - Persisted in localStorage so the choice sticks across refreshes.
 * - Drives the page direction: Hebrew = RTL, English = LTR (set on <html>).
 * - `t` is the active language's copy object (lib/copy.js).
 */
const LangContext = createContext(null)
const KEY = 'tom.lang'
const DEFAULT = 'hebrew'

function initialLang() {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'hebrew' || saved === 'english') return saved
  } catch {
    /* private mode / no storage */
  }
  return DEFAULT
}

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(initialLang)
  const dir = lang === 'hebrew' ? 'rtl' : 'ltr'

  useEffect(() => {
    try {
      localStorage.setItem(KEY, lang)
    } catch {
      /* ignore */
    }
    const html = document.documentElement
    html.lang = lang === 'hebrew' ? 'he' : 'en'
    html.dir = dir
  }, [lang, dir])

  const t = COPY[lang] || COPY[DEFAULT]
  return <LangContext.Provider value={{ lang, setLang, t, dir }}>{children}</LangContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLang() {
  const ctx = useContext(LangContext)
  if (!ctx) throw new Error('useLang must be used inside <LanguageProvider>')
  return ctx
}
