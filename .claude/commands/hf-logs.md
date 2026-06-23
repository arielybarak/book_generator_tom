---
description: >-
  Fetch TOM HF Space logs (run/build) via ~/.hf_token — real Python traceback behind a
  failed /generate_page. USE WHEN generation errors or Space is RUNTIME_ERROR.
argument-hint: "[run|build] [grep-regex]"
---

Pull the Hugging Face Space logs and surface the failure. Gradio hides tracebacks from
clients (the web/API call just gets `event: error` / `data: null`) — the truth is in the
Space's container logs. See [[zerogpu-web-bridge]] for what the failures usually mean.

**$ARGUMENTS** = `[run|build] [grep-regex]` (defaults: `run`, no filter). `run` = the live
app/container log (runtime errors, tracebacks); `build` = the image build log (deploy/boot).

Run this (token is read into a var and never printed):

!`bash -c '
T=$(cat ~/.hf_token 2>/dev/null) || { echo "no ~/.hf_token — see the token-handoff in CLAUDE/memory"; exit 1; }
R="MLightning/text2STL-engine-2.0-superMX-bottom"
KIND="${1:-run}"; PAT="${2:-}"
curl -s --max-time 15 -H "Authorization: Bearer $T" "https://huggingface.co/api/spaces/$R/logs/$KIND" -o /tmp/hf_$KIND.sse -w "http=%{http_code}\n"
python3 - "$PAT" <<PY
import json,sys,re
pat=sys.argv[1] if len(sys.argv)>1 else ""
out=[]
for raw in open("/tmp/hf_$KIND.sse"):
    raw=raw.strip()
    if raw.startswith("data: "):
        try: out.append(json.loads(raw[6:]).get("data",""))
        except Exception: pass
txt="".join(out).splitlines()
if pat:
    rx=re.compile(pat); txt=[l for l in txt if rx.search(l)]
print("\n".join(txt[-80:]))
PY
' -- $ARGUMENTS`

Then read the tail: a `Traceback (most recent call last)` or an `Error:` line is the cause.
Common ones for this Space:
- `The requested GPU duration (Xs) is larger than the maximum allowed` → `@spaces.GPU(duration)`
  too high for the anonymous caller; lower it (see [[zerogpu-web-bridge]]).
- `FileNotFoundError: ... page_1.png` in `gr.File.postprocess` → SD didn't run, so no image was
  written; the web handler should `raise gr.Error` on a missing file instead of returning the path.
- Build log `address already in use` → a second server bound the Gradio port; let `demo.launch()`
  own it, don't start your own uvicorn.

Endpoint note: it's `…/logs/run` and `…/logs/build` (NOT `…/logs/container`, which 404s).
The token is the Space owner's; keep it out of any printed output.
