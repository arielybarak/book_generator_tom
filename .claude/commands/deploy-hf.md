---
description: >-
  Redeploy TOM's backend to Hugging Face Spaces — run the full ./sync_to_space.sh →
  commit → push-from-hf_space/ checklist, with safety checks so a stale or wrong-place
  push can't happen. Reach for this whenever you've changed src/ or config.yaml.
argument-hint: "[commit message]"
---

Redeploy the TOM backend to the Hugging Face Space. Use **$ARGUMENTS** as the commit message
(default to a short summary of the diff if empty). Follow [[hf-space-sync-deploy]]; do NOT edit
`hf_space/src/` or `hf_space/config.yaml` directly.

Run this checklist, pausing if anything looks wrong:

1. **Show what changed** in the source of truth:
   !`cd "$CLAUDE_PROJECT_DIR" && git status --short src/ config.yaml`
2. **Confirm the deployed entry point** (so you push the app you think you're pushing):
   !`grep '^app_file:' "$CLAUDE_PROJECT_DIR/hf_space/README.md"`
3. **Sync** the library + config into the submodule:
   !`cd "$CLAUDE_PROJECT_DIR" && ./sync_to_space.sh`
4. **Review the submodule diff** before committing (this is what actually deploys):
   !`cd "$CLAUDE_PROJECT_DIR/hf_space" && git status --short && git --no-pager diff --stat`
5. **Commit + push from inside `hf_space/`** (the only push that triggers an HF rebuild):
   ```bash
   cd "$CLAUDE_PROJECT_DIR/hf_space" && git add -A && git commit -m "<message>" && git push
   ```
   Run this step explicitly — confirm the message and that you're in `hf_space/` first.

If app files themselves changed (`gradio_app_lithophane.py`, `gradio_app.py`, `requirements.txt`),
remember those live only in `hf_space/` and are committed in step 5, not produced by the sync.
After the push, HF rebuilds automatically; the frontend (Vercel) is a separate deploy and is
unaffected.
