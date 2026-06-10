---
title: Text2STL Engine 2.0 SuperMX Bottom
emoji: 😻
colorFrom: green
colorTo: indigo
sdk: gradio
sdk_version: 6.3.0
# Deployed app — change `app_file` to switch (see note below), then commit + push:
#   gradio_app.py             -> CadQuery STL (crisp tactile layers)
#   gradio_app_lithophane.py  -> heightmap / lithophane STL (experimental)
app_file: gradio_app_lithophane.py
pinned: false
short_description: text2STL-engine
---

## Which app is deployed?

The `app_file:` field in the frontmatter above selects the running app:

- `gradio_app.py` — final STL via **CadQuery** (crisp, discrete tactile layers)
- `gradio_app_lithophane.py` — **experimental**: STL from a combined **heightmap** (no CadQuery)

**To switch:** edit `app_file`, then `git commit` + `git push`. The Space rebuilds automatically.
Currently set to: **`gradio_app_lithophane.py`**.

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
