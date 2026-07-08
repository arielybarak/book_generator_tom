# Getting Started — forking & running your own copy of TOM

This doc is for students/contributors who want to **fork this repo and stand up their own
working copy** — not just read the code. `README.md` covers the mission and pipeline; this
is the "how do I actually get this running end-to-end on my own accounts" doc.

TOM's production deployment spans **three separate free-tier cloud platforms**. None of them
are required to work on the core pipeline locally — read the [Level 0](#level-0--just-the-pipeline-no-accounts-needed)
section first if you just want to generate STLs on your own machine.

| Platform | What it does here | Why this one |
|---|---|---|
| **[Hugging Face Spaces](https://huggingface.co/spaces)** | Hosts the Python/Gradio backend (`hf_space/`) and gives it a free serverless GPU (**ZeroGPU**) for the Stable Diffusion step. | Free GPU hosting for a Gradio app is rare; ZeroGPU allocates a GPU only for the seconds an `@spaces.GPU` function runs, so a hobby project doesn't pay for idle GPU time. |
| **[Vercel](https://vercel.com)** | Hosts the React frontend (`web/`) and one serverless function (`web/api/generate.js`) that proxies generation requests. | Zero-config static+serverless hosting for a Vite app, generous free tier, deploys on every `git push`. |
| **[Supabase](https://supabase.com)** | Auth (username/password, stored as Postgres users under the hood). | The *real* reason auth exists isn't login UX — it's to gate who can spend the project owner's ZeroGPU quota. See below. |

---

## Why auth exists (this trips people up)

A Hugging Face Space is **public** — anyone can call its API. ZeroGPU gives every anonymous
caller a tiny shared GPU-time quota, which a real app blows through instantly. The fix used
here: **only signed-in users can trigger generation**, and the request is enqueued through a
Vercel serverless function carrying the **project owner's personal HF token**, so approved
traffic runs on the owner's larger (PRO) quota instead of the anonymous one.

Request flow:

```
Browser (signed in via Supabase)
  │  POST /api/generate  (Authorization: Bearer <supabase JWT>)
  ▼
Vercel serverless fn  (web/api/generate.js)
  │  validates JWT with Supabase
  │  POST {hf-space}/gradio_api/call/generate_page  (Authorization: Bearer <HF_TOKEN>)
  ▼
Hugging Face Space   (hf_space/gradio_app_lithophane.py, api_name="generate_page")
  │  returns { event_id }
  ▼
Browser streams the result itself:
  GET {hf-space}/gradio_api/call/generate_page/{event_id}   (SSE, no auth needed)
```

So: Supabase decides *who* can ask, the Vercel function decides *how the request reaches HF*
(with a token the browser never sees), and the browser talks to HF directly only for the
public, unauthenticated result stream.

---

## Level 0 — just the pipeline, no accounts needed

Run the Gradio app locally. No HF Space, no Vercel, no Supabase required:

```bash
pip install -r hf_space/requirements.txt
cd hf_space
python gradio_app_lithophane.py
```

Open the local Gradio URL, add a page, hit Generate. This exercises the whole
SD → DXF → STL pipeline on your machine (CPU-only if you have no local GPU — slower, but it
works). Good enough to read/modify `src/dxf_3d.py`, `src/image_funcs.py`,
`src/language_funcs.py`, etc. and see the result.

---

## Level 1 — your own Hugging Face Space (backend + free GPU)

1. **Duplicate, don't fork, the Space.** `hf_space/` in this repo is a **git submodule**
   pointing at `https://huggingface.co/spaces/MLightning/text2STL-engine-2.0-superMX-bottom` —
   you don't have push access to that repo. Instead:
   - Go to the live Space, click **⋯ → Duplicate this Space** (needs a free HF account). This
     copies the app file, `src/`, `config.yaml`, and `requirements.txt` into a new Space
     *you* own.
   - Under **Settings → Hardware**, ZeroGPU is selected via the `spaces.GPU` decorator in code
     (not a hardware tier you pick manually) — the free ZeroGPU tier works for a personal
     Space; just make sure the Space's `README.md` frontmatter still has `sdk: gradio`.
2. **Point your local clone at your Space** (optional, only needed if you want `git push` to
   redeploy the way this repo does):
   ```bash
   git submodule deinit hf_space
   git rm hf_space
   git submodule add https://huggingface.co/spaces/<you>/<your-space-name> hf_space
   ```
3. **Pushing to a Space** uses HTTPS git, not the HF web UI, for edits:
   ```bash
   cd hf_space
   git add -A && git commit -m "..."
   git push
   ```
   - Git asks for username + password. Username = your HF username. Password = an **access
     token value** (`hf_...`), generated at huggingface.co/settings/tokens — not the token's
     label. Get a *write* token if you'll push.
   - If the push hangs forever, it's usually an HTTP/2 issue with HF's git server:
     `git config --global http.version HTTP/1.1`.
4. Keep `src/` and `hf_space/src/` in sync going forward: edit the repo-root `src/`, then run
   `./sync_to_space.sh` before committing inside `hf_space/` (Spaces must be fully
   self-contained — they don't see the rest of this repo).

You now have a working backend at `https://<you>-<your-space-name>.hf.space` with its own
Gradio UI, usable stand-alone with no frontend at all.

---

## Level 2 — your own Supabase project (auth)

1. Create a free project at [supabase.com](https://supabase.com).
2. **Authentication → Providers**: Email should be enabled by default.
3. **Authentication → Settings**: turn **off "Confirm email"**. The app maps a plain username
   to a synthetic address (`{username}@tom.local`, see `web/src/lib/supabase.js`) that can't
   receive a confirmation email — leaving confirmation on will lock every signup half-finished.
4. Grab **Project URL** and **anon public key** (Settings → API) — these become
   `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` (client) and `SUPABASE_URL` /
   `SUPABASE_ANON_KEY` (server, same values, no `VITE_` prefix) in the next step.

---

## Level 3 — your own Vercel deployment (frontend + proxy)

1. Import your fork into Vercel. **Root Directory = `web`**, framework preset **Vite**.
2. Environment variables (Project Settings → Environment Variables):

   | Variable | Value | Visible to browser? |
   |---|---|---|
   | `VITE_HF_SPACE` | `<you>/<your-space-name>` | yes |
   | `VITE_SUPABASE_URL` | your Supabase project URL | yes |
   | `VITE_SUPABASE_ANON_KEY` | your Supabase anon key | yes |
   | `HF_TOKEN` | an HF access token (ideally on a **PRO** account for a larger ZeroGPU quota) | **no** — server-only |
   | `HF_SPACE` | `<you>/<your-space-name>` | **no** — **set this explicitly**; `web/api/generate.js` hardcodes the original project's Space as its fallback, so skipping this sends your traffic to the wrong Space |
   | `SUPABASE_URL` | same as above | **no** |
   | `SUPABASE_ANON_KEY` | same as above | **no** |

3. **Settings → Git → Production Branch** must match the branch you actually push (e.g.
   `main` vs `master`) — a mismatch silently deploys every push as a *preview*, and the live
   domain keeps serving an old build until you manually promote one.
4. Push to your fork's default branch; Vercel builds and deploys automatically.

---

## Local dev with your own full stack

```bash
cd web
cp .env.example .env.local     # fill in the vars from Level 2 + 3 (VITE_ ones for local dev)
npm install
npm run dev                    # http://localhost:5173
```

`npm run dev` still calls the deployed Vercel function for `/api/generate` unless you also
run `vercel dev` — for most UI work, pointing `VITE_HF_SPACE` at your Space and testing the
Gradio app directly (Level 0/1) is faster than round-tripping through auth.

---

## Where to go next

- **`README.md`** — mission, pipeline, module map, CLI usage, geometry tuning.
- **`CLAUDE.md`** / **`web/CLAUDE.md`** — the conventions and contracts an AI coding agent (or
  a careful human) needs before touching this code: the DXF/STL engine invariants, the
  Hebrew/Braille/nikud contract, the HF↔Vercel API contract, RTL/i18n rules.
- **`PROGRESS.md`** — the real war-story log of what broke and why (OCCT segfaults, ZeroGPU
  cold starts, Hebrew glyph rendering) — worth reading before you touch `src/dxf_3d.py`.
- **`.claude/skills/`** — if you use Claude Code, these encode most of the gotchas above (and
  more) as auto-activating, task-specific procedures.
