import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)

// Map a UI username to the synthetic email Supabase stores.
// Must stay in sync with the server-side check in api/generate.js.
export const usernameToEmail = (u) => `${String(u).trim().toLowerCase()}@tom.local`
