---
description: >-
  Deploy TOM to HF Space. App-file change: commit+push from hf_space/ directly.
  src/+config.yaml change: sync_to_space.sh first. USE WHEN pushing any change to
  hf_space/ or src/+config.yaml.
argument-hint: "[commit message]"
---

Redeploy the TOM backend to the Hugging Face Space. Use **$ARGUMENTS** as the commit
message (default to a short summary of the diff if empty).

## Step 0 — determine the change type

```bash
cd "$CLAUDE_PROJECT_DIR"
git status --short src/ config.yaml
git -C hf_space status --short
```

- **Path A** (app-file only): only `hf_space/` files changed (e.g. `gradio_app_lithophane.py`,
  `requirements.txt`) and **no** repo-root `src/` or `config.yaml` changes. Skip to Step 3.
- **Path B** (library/config change): any `src/` or `config.yaml` was modified. Run Steps 1–3.

---

## Path B only — Steps 1–2

**Step 1 — confirm the deployed entry point:**
!`grep '^app_file:' "$CLAUDE_PROJECT_DIR/hf_space/README.md"`

Flag if it doesn't match the app you just changed.

**Step 2 — sync library + config into the submodule:**
!`cd "$CLAUDE_PROJECT_DIR" && ./sync_to_space.sh`

This mirrors `src/` and `config.yaml` into `hf_space/` via rsync (do NOT edit `hf_space/src/`
or `hf_space/config.yaml` by hand — the sync will overwrite them). See [[hf-space-sync-deploy]].

---

## Step 3 — review the submodule diff (both paths)

!`cd "$CLAUDE_PROJECT_DIR/hf_space" && git status --short && git --no-pager diff --stat`

This is what actually deploys. Confirm only expected files appear. If something looks wrong, stop.

---

## Step 4 — commit + push from inside `hf_space/`

The only push that triggers an HF rebuild is a push from the `hf_space/` repo:

```bash
cd "$CLAUDE_PROJECT_DIR/hf_space" && git add -A && git commit -m "<message>" && git push
```

Confirm: (a) the commit message is accurate, (b) you are inside `hf_space/` not the repo root.

---

After the push, HF rebuilds automatically (watch with `/hf-logs build`). The frontend (Vercel)
is a separate deploy and is unaffected.
