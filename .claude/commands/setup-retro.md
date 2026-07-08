---
description: Capture this repo's AI-setup pain into a machine-consumable setup-backlog.md — what you kept doing by hand, which blocks are now WRONG (stale), what's missing — so /upgrade-claude-setup can work it down. USE WHEN a session was painful, after a big migration/refactor, or when a skill's advice feels out of date.
argument-hint: "[note about what surfaced this]"
---

Author or update **`.claude/setup-backlog.md`** for this repo — the durable record that
lets the setup keep up with the code instead of rotting. Write for a builder agent with
**no chat context**: every item implementable cold (name the block, the observed cost,
the exact behavior/args/entry points, the done-check). Ground every claim in a real
file/command — an ungrounded item gets cut.

Context to fold in: **$ARGUMENTS**

## Do this

1. **Where time was burned (this round).** From the current session + recent history,
   name 2–5 themes of pain. Pull evidence:
   - !`git log --oneline -30`
   - !`git log --since="30 days ago" --stat --oneline | head -60`
   - If the meta-env-setup kit is reachable, enrich with session evidence:
     `python /home/barak/agents_sendbox/meta-env-setup/tools/mine_transcripts.py --repo .`
     (repeated commands, throwaway harnesses, deploy→wait loops). If not, skip — the git
     + session review still works.

2. **Stale check (do NOT skip — a wrong block misleads worse than a missing one).**
   For **each** block in `.claude/skills|commands|agents`, pull the concrete identifiers
   it cites (function names, constants, flags, filenames) and grep the codebase:
   - !`ls .claude/skills .claude/commands .claude/agents 2>/dev/null`
   - For a suspect noun: !`grep -rn "<identifier>" --include=*.py --include=*.js . | head`
   - Zero hits = the block describes code that no longer exists → **REWRITE** candidate.
   Cross-check `git log` for a migration/refactor that postdates the block.

3. **Write the backlog** with these sections (priority order within §2):
   - **§1 Where time was burned** — the themes above, short (this is the credibility).
   - **§2 The backlog** — one entry per change, highest **(cost × frequency)** first.
     Tag each **ADD** (new block) · **FIX** (existing falls short) · **REWRITE** (now
     wrong, see §3) · **KEEP** · **CUT**. Per entry: target block+path · why (the
     observed cost) · what to build/change (behavior, args, entry points, file:line) ·
     **Done when** (the concrete check).
   - **§3 Stale — now WRONG** — table: block path | why it's wrong now | what it must
     say instead. (From step 2.)
   - **§4 Keep** · **§5 Cut** — name them so the refine loop doesn't churn what works.
   - **§6 Durable knowledge** — facts worth a *new* skill or a memory.
   - **§7 Appendix** — constants, endpoints, entry-point signatures, file:line anchors:
     everything a cold builder needs. The most valuable section.

4. **Hand off.** Tell the user: run **`/upgrade-claude-setup <this-repo>`** from the
   meta-env-setup kit — it imports the live setup, reconciles it against this backlog
   (ADD/FIX/REWRITE/KEEP/CUT), and works it down without touching the real repo until
   `install.sh --apply`.

Keep it sharp and grounded. This backlog is the single most valuable artifact for the
next round — treat it as the spec, not a diary.
