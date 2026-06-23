---
name: hf-space-sync-deploy
description: >-
  TOM hf_space/ deploy: edit src/+config.yaml, sync_to_space.sh, commit+push from
  hf_space/. USE WHEN deploying to HF Space, editing the Gradio app, or after any
  src/ or config.yaml change.
---

# HF Space sync + deploy

The deployed backend lives in the **`hf_space/` git submodule** (its own repo:
`MLightning/text2STL-engine-2.0-superMX-bottom`). It is **self-contained** — it vendors a
*copy* of `src/` and `config.yaml`. See repo-root `CLAUDE.md` → "HF Spaces deployment note"
for the rule; this skill is the procedure and the traps.

## When to Activate This Skill
- "deploy", "push to the space", "redeploy", "update the HF backend", "switch the app"
- Right after editing any repo-root `src/` module or `config.yaml` that the app uses
- Editing the Gradio app files (`gradio_app_lithophane.py`, `gradio_app.py`, `requirements.txt`)

## The deploy procedure (in order)
1. Make code/config changes in **repo-root** `src/` and `config.yaml` (the source of truth for notebooks/CLI).
2. From the repo root, run **`./sync_to_space.sh`** — it `rsync -a --delete`s `src/` → `hf_space/src/` and copies `config.yaml` → `hf_space/config.yaml` (skips `__pycache__`).
3. `cd hf_space && git add -A && git commit -m "…" && git push` — **push from inside the submodule**, not the parent repo. HF auto-rebuilds on push.

## Gotchas (the exact things people get wrong here)
- **Never edit `hf_space/src/` or `hf_space/config.yaml` directly.** They are vendored copies; the next `./sync_to_space.sh` overwrites them (`--delete` even removes files you added there). Edit repo-root `src/`/`config.yaml`, then sync.
- **`sync_to_space.sh` mirrors only `src/` and `config.yaml`.** The app files live *only* in `hf_space/` — `gradio_app_lithophane.py`, `gradio_app.py`, `requirements.txt`, `README.md`. Edit those **directly inside `hf_space/`** (then commit+push from there); they are not synced from anywhere.
- **Deployed entry point = `hf_space/gradio_app_lithophane.py`**, selected by `app_file:` in `hf_space/README.md` frontmatter. To switch apps, edit `app_file:`, then commit+push from `hf_space/`.
- **SD inference is the only GPU code** — `run_sd_inference()` is `@spaces.GPU(duration=120)` (ZeroGPU; GPU only attached inside that call). Translation, DXF, and STL stay on CPU. Don't decorate CPU work with `@spaces.GPU`.
- **Push from the wrong place does nothing.** Committing in the parent repo updates the submodule pointer, not the Space; only `git push` *inside* `hf_space/` triggers an HF rebuild.
- Forgetting the sync = a **stale deploy** (old `src/`/`config.yaml` shipped). Run `/check-sync` if unsure, or `/deploy-hf` to do the whole checklist.
