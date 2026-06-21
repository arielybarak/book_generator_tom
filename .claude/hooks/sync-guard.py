#!/usr/bin/env python3
"""Sync Guard — TOM deploy hygiene (PostToolUse, advisory / non-blocking).

After an Edit/Write/MultiEdit, remind about TOM's #1 deploy trap:
  * editing repo-root ``src/`` or ``config.yaml`` -> must run ``./sync_to_space.sh``
    before the change reaches the Hugging Face Space;
  * editing ``hf_space/src/`` or ``hf_space/config.yaml`` directly -> those are
    VENDORED COPIES that the next sync overwrites; edit repo-root + sync instead.

It NEVER blocks (always exit 0) — a missed reminder is fine, a wedged workflow is not.
Note: the frontend ``web/src/`` is intentionally ignored (sync_to_space.sh does not
mirror it).

Wire it in .claude/settings.json:

    "hooks": {
      "PostToolUse": [
        { "matcher": "Edit|Write|MultiEdit",
          "hooks": [ { "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/sync-guard.py\"" } ] }
      ]
    }
"""

import json
import sys


def message_for(path: str) -> str | None:
    p = path.replace("\\", "/")

    # Forbidden: a vendored copy inside the submodule.
    if "/hf_space/src/" in p or p.startswith("hf_space/src/") \
            or p.endswith("/hf_space/config.yaml") or p == "hf_space/config.yaml":
        return ("[sync-guard] You edited a VENDORED COPY inside hf_space/. The next "
                "./sync_to_space.sh overwrites it. Edit repo-root src/ or config.yaml "
                "instead, then run ./sync_to_space.sh (see /deploy-hf).")

    # Skip the frontend — sync_to_space.sh does not mirror web/.
    if "/web/" in p or p.startswith("web/"):
        return None

    # Repo-root Python src/ or config.yaml -> the source of truth that must be synced.
    is_root_src = p.startswith("src/") or "/src/" in p
    is_config = p == "config.yaml" or p.endswith("/config.yaml")
    if (is_root_src or is_config) and "hf_space" not in p:
        return ("[sync-guard] Edited repo-root src/ or config.yaml. Run ./sync_to_space.sh "
                "and push from inside hf_space/ before this reaches the Space (see /deploy-hf).")

    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break the workflow on a parse error
    tool_input = event.get("tool_input", {}) or {}
    path = tool_input.get("file_path") or ""
    if isinstance(path, str) and path:
        msg = message_for(path)
        if msg:
            print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
