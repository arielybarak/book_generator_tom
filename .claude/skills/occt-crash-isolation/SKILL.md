---
name: occt-crash-isolation
description: >-
  TOM pattern — risky CadQuery/OCCT ops (taper/fillet/boolean on user glyph outlines) segfault the
  whole Gradio worker with no traceback. Run them in a subprocess with a timeout; treat exit
  -11/139 as "skip this feature". USE WHEN adding a CadQuery op on user-supplied geometry or
  debugging a worker that dies silently mid-generation.
---

# OCCT crash-isolation

OCCT (CadQuery's kernel) **segfaults** on some real user geometry — `extrude(taper=)` on Hebrew
glyph outlines is the proven case (see [[tactile-stl-geometry]]). A segfault kills the **entire
Gradio worker**, so the user just sees "something went wrong" and [[/hf-logs]] shows the process
died, not a Python error.

## When to Activate This Skill
- Adding a risky CadQuery op on user-supplied outlines: `taper`, `fillet`, `chamfer`, or boolean
  `union`/`fuse`/`cut` across glyph / line-art solids.
- A build that dies with no Python traceback, or the worker restarts mid-generation.

## The pattern: isolate in a subprocess with a timeout
Never run a crash-prone op inline in the request handler. Spawn it:

```python
import subprocess
r = subprocess.run(["python", "-c", op_script, *args], timeout=TIMEOUT)
if r.returncode in (-11, 139):       # SIGSEGV (-11 POSIX, 139 = 128+11)
    # skip the feature; fall back to the safe path (e.g. flat-top extrude)
    ...
```

- `returncode == -11` or `139` = **SIGSEGV** → treat as "skip this feature," never let it
  propagate and kill the worker.
- Always pass `timeout=` — OCCT can also **hang** (the O(N²) boolean), not only crash.
- Keep the **default product path crash-safe** (flat tops, no boolean union — [[tactile-stl-geometry]]);
  the subprocess is only for optional rounded-top / fancy ops.

Worth a reusable helper in `src/`. Pairs with [[/stl-bench]], which runs the build in a subprocess
for exactly this reason (an STL bench that segfaults shouldn't take the tool down).
