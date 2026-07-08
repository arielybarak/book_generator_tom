# TOM — frontend (`web/`)

React + Vite + Tailwind v4 SPA. Hebrew-first, RTL, deployed to Vercel.
The Hugging Face Space is the compute backend; the frontend calls it via `@gradio/client`.

## Local dev

```bash
cd web
npm install
cp .env.example .env          # set VITE_HF_SPACE if needed
npm run dev                   # http://localhost:5173
npm run build && npm run preview
npm run lint
```

## Deploy to Vercel

1. Import the **root** of this repo into Vercel.
2. Set **Root Directory** → `web`.
3. Add env var: `VITE_HF_SPACE` = `MLightning/text2STL-engine-2.0-superMX-bottom`
4. Framework preset: **Vite**. Build command: `npm run build`. Output: `dist`.

Auto-deploys on every push to `master`.

## Backend API contract

One endpoint on the HF Space:

```
POST /generate_page
inputs: [raw_text, variations, image_desc, object_class]
output: [image_file_url, stl_file_url]
```

Defined in `hf_space/gradio_app_lithophane.py` (deployed) and `hf_space/gradio_app.py`.
Client code: `src/api/hfClient.js`.

The Space must be **public** (no token needed from the browser).
See repo memory `hf-deploy-gotchas` for push/auth pitfalls.
