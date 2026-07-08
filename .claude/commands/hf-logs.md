---
description: >-
  Fetch TOM HF Space logs tail via ~/.hf_token — real Python traceback behind a failed
  /generate_page. Noise-filters asyncio teardown + tqdm lines; splits on \r (HF SSE quirk).
  USE WHEN generation errors, Space is RUNTIME_ERROR, or debugging a silent worker death.
argument-hint: "[run|build] [--tail N] [--grep REGEX] [--follow]"
---

Pull the HF Space log **tail** and surface the failure. Gradio hides tracebacks from clients
— the truth is in the container log. Default: last 80 meaningful lines of `run` log.

**$ARGUMENTS** = `[run|build] [--tail N] [--grep REGEX] [--follow]`
- `run` (default) = live app/container log — runtime errors, tracebacks
- `build` = image build log — deploy/boot failures
- `--tail N` = show last N lines (default 80)
- `--grep REGEX` = filter to matching lines after noise filtering
- `--follow` = poll every 5 s and print new lines (Ctrl-C to stop)

Run this (token is read into a var and never printed):

```bash
T=$(cat ~/.hf_token 2>/dev/null) || { echo "no ~/.hf_token"; exit 1; }
R="MLightning/text2STL-engine-2.0-superMX-bottom"
KIND="${ARG1:-run}"; TAIL_N="${ARG_TAIL:-80}"; PAT="${ARG_GREP:-}"

curl -s --max-time 20 -H "Authorization: Bearer $T" \
  "https://huggingface.co/api/spaces/$R/logs/$KIND" \
  -o /tmp/hf_space_log.sse -w "HTTP %{http_code}\n"
```

Then parse with:

```python
import sys, re, json
from pathlib import Path

NOISE = re.compile(
    r'Invalid file descriptor: -1'
    r'|BaseEventLoop\.__del__'
    r'|Exception ignored in'
    r'|\d+it/s\]'               # tqdm iterations
    r'|\d+B/s\]'                # tqdm bytes
    r'|Fetching \d+ files'      # model download chatter
    r'|Loading weights'
    r'|Downloading shards'
    r'|tokenizer_config'
)

raw = Path("/tmp/hf_space_log.sse").read_text(errors="replace")

lines = []
for chunk in raw.split("\r"):              # HF SSE quirk: CR-joined, not newline-joined
    chunk = chunk.strip()
    if chunk.startswith("data: "):
        try:
            obj = json.loads(chunk[6:])
            text = obj.get("data", "")
            lines.extend(text.splitlines())
        except Exception:
            pass

# noise filter
lines = [l for l in lines if not NOISE.search(l)]

# grep
pat = sys.argv[1] if len(sys.argv) > 1 else ""
if pat:
    rx = re.compile(pat)
    lines = [l for l in lines if rx.search(l)]

# tail
print("\n".join(lines[-int(sys.argv[2] if len(sys.argv) > 2 else 80):]))
```

Read the tail for `Traceback (most recent call last)` or `Error:`. Common ones:
- `The requested GPU duration (Xs) is larger than the maximum allowed` → `@spaces.GPU(duration)` too high; lower it ([[zerogpu-web-bridge]]).
- `FileNotFoundError: ... page_1.png` → SD didn't run; `gr.File` postprocess got no file; add a `raise gr.Error` guard.
- `Segmentation fault` with no traceback → OCCT crash; see [[occt-crash-isolation]].
- Build log: `address already in use` → second process bound the Gradio port.

Endpoint: `…/logs/run` and `…/logs/build` (NOT `…/logs/container`, which 404s).
Token is owner's. Never print it.
