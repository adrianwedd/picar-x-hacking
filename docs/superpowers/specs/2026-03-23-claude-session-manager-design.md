# SPARK Claude Session Manager & Extended Autonomy

**Date:** 2026-03-23
**Status:** Approved
**Supersedes:** 2026-03-20-spark-self-evolution-design.md (evolve pipeline section)

## Problem

SPARK's self-evolution pipeline (`px-evolve`) has a 0% success rate — 9/9 non-dry
attempts failed. Root cause: `claude -p` is invoked with `--allowedTools ""`,
meaning Claude cannot read or edit files, and must output blind unified diffs
that fail `git apply`. Beyond fixing evolve, SPARK currently has no way to
leverage Claude Code for research, self-debugging, creative writing, or deep
conversation — all cognitive activity is limited to single-shot Haiku reflections.

## Design

### 1. Claude Session Manager (`src/pxh/claude_session.py`)

Central dispatcher for all SPARK-initiated Claude Code interactions.

#### Responsibilities

- **Model routing**: maps session type to the right model
- **Rate limiting**: enforces global cooldown, daily cap, and per-type cooldowns
- **Execution**: wraps `claude -p` subprocess with timeout, env stripping, output capture
- **Logging**: every session logged to `state/claude_sessions.jsonl`
- **Budget tracking**: reads session log to enforce daily caps

#### Model Routing

| Session Type    | Model  | Rationale                                    |
|-----------------|--------|----------------------------------------------|
| `evolve`        | Opus   | Must read, understand, and edit Python code  |
| `self_debug`    | Sonnet | Analytical — reads logs, proposes diagnosis  |
| `research`      | Haiku  | Text generation, no code                     |
| `compose`       | Haiku  | Prose generation, shaped by prompt           |
| `conversation`  | Sonnet | Reasoning over complex questions, no code    |

Models configurable via env vars:
- `PX_CLAUDE_MODEL_EVOLVE` (default: `claude-opus-4-6`)
- `PX_CLAUDE_MODEL_DEBUG` (default: `claude-sonnet-4-6`)
- `PX_CLAUDE_MODEL_RESEARCH` (default: `claude-haiku-4-5-20251001`)
- `PX_CLAUDE_MODEL_COMPOSE` (default: `claude-haiku-4-5-20251001`)
- `PX_CLAUDE_MODEL_CONVERSATION` (default: `claude-sonnet-4-6`)

#### Interface

```python
from pxh.claude_session import run_claude_session, SessionBudgetExhausted

try:
    result = run_claude_session(
        session_type="evolve",
        prompt="...",
        timeout=1800,
        allowed_tools="Read,Write,Edit,Bash,Glob,Grep",
        skip_permissions=True,   # required for non-interactive tool use
        cwd="/tmp/spark-evolve-xxx",
    )
    # result: RunResult(stdout, stderr, returncode, duration_s, model_used)
except SessionBudgetExhausted:
    # Fall back to non-Claude action
    pass
```

The `skip_permissions` parameter maps to `--dangerously-skip-permissions` on the
`claude -p` subprocess. Only used for sessions that need tool access (`evolve`).
Defaults to `False`. The `cwd` parameter defaults to `PROJECT_ROOT` when not
specified (used by non-worktree sessions like research, compose).

Priority is determined internally by `session_type`, not passed by the caller.
The session manager maps each type to its priority rank.

#### Rate Limiting

| Constraint          | Value     | Scope                |
|---------------------|-----------|----------------------|
| Global cooldown     | 30 min    | Between any sessions |
| Daily session cap   | 8/day     | All types combined   |
| Evolve              | 1/day     | Per-type             |
| Self-debug          | 6 hours   | Per-type             |
| Research            | 2 hours   | Per-type             |
| Compose             | 4 hours   | Per-type             |
| Conversation depth  | 15 min    | Per-type cooldown    |

Day boundary: midnight Hobart time (`Australia/Hobart`), consistent with all
other time-of-day logic in the codebase.

Priority when budget is tight (≤2 sessions remaining):
`self_debug > evolve > conversation > research > compose`

Lower-priority sessions raise `SessionBudgetExhausted` — callers fall back to
non-Claude actions.

#### Override Env Vars

- `PX_CLAUDE_DAILY_CAP=8`
- `PX_CLAUDE_COOLDOWN_S=1800`
- `PX_CLAUDE_BUDGET_DISABLED=1` — bypass all limits (testing)

#### Session Log Format

`state/claude_sessions.jsonl` — one JSON object per line:

```json
{
  "ts": "2026-03-23T10:00:00Z",
  "type": "evolve",
  "model": "claude-opus-4-6",
  "duration_s": 342.5,
  "returncode": 0,
  "outcome": "success",
  "session_id": "sess-20260323-100000-042"
}
```

### 2. Fixed Evolution Pipeline (`bin/px-evolve`)

#### Changes from Current Implementation

1. **Remove patch approach** — delete `patch_prompt` construction (lines 200-217),
   patch extraction regex, `git apply`/`patch -p1` fallback logic (lines 249-298)
2. **Give Claude real tools** — `--allowedTools "Read,Write,Edit,Bash,Glob,Grep"`
   with `--dangerously-skip-permissions`
3. **Simplified prompt** — tell Claude to edit files directly, then commit
4. **Detect changes via git log** — check `git log HEAD --not master --oneline`
   for commits rather than checking unstaged diffs
5. **Route through session manager** — `run_claude_session(type="evolve", ...)`
   for unified rate limiting and logging
6. **Timeout**: 1800s (30 min), configurable via `PX_EVOLVE_TIMEOUT`

#### Broadened File Whitelist

- `src/pxh/spark_config.py` — angles, seeds, constants (safe, existing)
- `src/pxh/mind.py` — expression logic, reactive templates, gating rules (new, PR-gated)
- `src/pxh/voice_loop.py` — ALLOWED_TOOLS and TOOL_COMMANDS dicts only (existing)
- `bin/tool-*` — new tools only (existing)
- `tests/` — new and modified test files (existing)
- `docs/prompts/` — new prompt files only (new)

#### Blacklist (updated — `mind.py` moved to whitelist)

- `docs/prompts/persona-*.md` — jailbreak prompts
- `src/pxh/api.py` — security-critical
- `bin/tool-chat`, `bin/tool-chat-vixen` — persona tools
- `bin/px-evolve` — no self-modification of the evolution daemon
- `.env`, credentials, systemd units

Note: `src/pxh/mind.py` was on the previous blacklist. It is now explicitly
moved to the whitelist for expression logic and reactive template changes.
All `mind.py` changes still require PR approval (option C safety model).

#### Post-Claude Whitelist Enforcement

After Claude finishes, `px-evolve` validates `git diff --name-only` against the
whitelist. Any changes to files outside the whitelist cause the entry to fail
with `failed:whitelist_violation`. This is a hard gate — the prompt whitelist is
advisory (Claude may ignore it), but the post-validation is enforced.

#### Feedback Loop

`tool-introspect` gains a new `evolve_outcomes` section that queries merged/rejected
PRs via `gh pr list --state all --head spark/evolve-*` (branch prefix filter) and
includes the outcome + any review comments in the introspection payload. This
feeds into the next evolution prompt so SPARK learns from rejection.

Note: `gh pr create` is updated to add `--label spark-evolve` for easy filtering.
The branch prefix query is the primary mechanism; the label is supplementary.

### 3. New Claude-Powered Capabilities

Five new session types, triggered from `px-mind` expression layer or voice loop.

#### A) Research (`tool-research`)

- **Trigger**: reflection produces thought with salience ≥ 0.8 and mood `curious`
- **Model**: Haiku, `--allowedTools ""`, 5-min timeout
- **Prompt**: SPARK's curiosity question + awareness context
- **Output**: multi-paragraph note saved to `state/notes-spark.jsonl`
- **Cooldown**: 2 hours
- **New action**: `research` added to VALID_ACTIONS

#### B) Self-Debugging (internal to mind.py)

- **Trigger**: `_consecutive_reflection_failures >= 3` (already tracked in mind.py)
- **Model**: Sonnet, `--allowedTools "Read,Glob,Grep"` (read-only, no Bash), 10-min timeout
- **Prompt**: "Reflection has failed N times. Recent errors: {stderr}. Diagnose."
  Includes recent log tail and state file contents in the prompt itself (no need
  for Bash to read them — mind.py gathers the context before spawning the session).
- **Output**: diagnostic report to `state/debug_reports.jsonl`; if confident,
  queues an evolution entry via `tool-evolve`
- **Cooldown**: 6 hours
- **New action**: `self_debug` added to VALID_ACTIONS
- **No new tool** — triggered directly from mind.py reflection error path
- **Security**: No Bash access. Runs in the main repo (not a worktree) but with
  read-only tools only. Cannot modify files, execute commands, or exfiltrate data.

#### C) Creative Writing (`tool-compose`)

- **Trigger**: explicit voice command ("write something for Obi") OR mind
  expression picks it during low-activity periods (weekend mornings, Obi at mum's)
- **Model**: Haiku, `--allowedTools ""`, 5-min timeout
- **Prompt**: awareness context + mood + recent thoughts → journal/letter/observation
- **Output**: saved to `state/compositions-spark.jsonl`; optionally posted to
  feed if salience high enough
- **Cooldown**: 4 hours
- **New action**: `compose` added to VALID_ACTIONS

#### D) Conversational Depth (voice_loop.py enhancement)

- **Trigger**: explicit voice command only — user says "think about that more",
  "go deeper", or "explain that properly". No automatic heuristic in v1;
  automatic detection can be added later with real usage data.
- **Model**: Sonnet, `--allowedTools ""`, 3-min timeout
- **Prompt**: conversation history + the complex question + awareness context
- **Response**: spoken via tool-voice, replacing the quick LLM backend response.
  The voice loop's existing `CODEX_CHAT_CMD` pipeline is bypassed for this
  single response — the Sonnet answer is injected directly as the tool output.
- **Cooldown**: 15 min post-session cooldown (between conversation-depth sessions)
- **No new tool** — enhancement to voice_loop.py response handling

#### E) Expression Layer Integration (mind.py)

- New valid actions: `research`, `self_debug`, `compose`
- `research` and `compose` added to `ABSENT_GATED_ACTIONS` (no activity when
  nobody's home) — these are social/creative actions.
- `self_debug` is NOT in `ABSENT_GATED_ACTIONS` — it is a system health action
  that should run regardless of Obi's presence. It is also NOT in
  `CHARGING_GATED_ACTIONS` (no motors/GPIO involved).
- `research` and `compose` are NOT in `CHARGING_GATED_ACTIONS` (no motors/GPIO).
- All route through `claude_session.py` for unified rate limiting
- `_daytime_action_hint()` updated:
  - Compose/research nudged during quiet daytime
  - Self_debug only triggered on reflection failure, never by daytime hints
- Research output uses `notes_file_for_persona("spark")` (existing helper) to
  maintain consistency with the persona-scoped notes pattern.

### 4. Integration Points

#### px-statusline

New field showing Claude session usage: `🧠3/8` (sessions used today / cap).

#### Dashboard API

`GET /api/v1/public/status` gains `claude_sessions_today` (int) and
`claude_budget_remaining` (int) fields.

#### tool-introspect

New sections in introspection payload:
- `claude_sessions`: today's count, model breakdown, total duration
- `evolve_outcomes`: merged/rejected PR history with reviewer comments

#### CLAUDE.md

Update the self-evolution section to reflect the new architecture, add
documentation for the session manager and new capabilities.

### 5. New Files

| File | Purpose |
|------|---------|
| `src/pxh/claude_session.py` | Session manager — routing, rate limiting, execution, logging |
| `bin/tool-research` | Research session tool (Haiku, text-only) |
| `bin/tool-compose` | Creative writing tool (Haiku, text-only) |
| `state/claude_sessions.jsonl` | Unified session log (gitignored) |
| `state/debug_reports.jsonl` | Self-debug diagnostic reports (gitignored) |
| `state/compositions-spark.jsonl` | Creative writing output (gitignored) |

### 6. Modified Files

| File | Changes |
|------|---------|
| `bin/px-evolve` | Remove patch hack, use session manager, broader whitelist |
| `src/pxh/mind.py` | New actions (research, self_debug, compose), expression routing, debug trigger |
| `src/pxh/voice_loop.py` | Add new tools to ALLOWED_TOOLS/TOOL_COMMANDS, conversation depth |
| `bin/tool-introspect` | Claude session stats, evolve outcome feedback |
| `bin/px-statusline` | Claude budget display |
| `src/pxh/api.py` | Claude budget fields in /public/status |
| `docs/prompts/claude-voice-system.md` | Document "think deeper" trigger |

### 7. Testing Strategy

- Unit tests for `claude_session.py`: rate limiting, model routing, budget enforcement,
  cooldown math, day boundary rollover, priority gating
- Unit tests for evolve pipeline: prompt construction, change detection,
  whitelist enforcement (post-Claude validation), blacklist rejection
- Integration test: mock `claude -p` subprocess, verify end-to-end flow for each session type
- Existing test suite must continue to pass
- New tools (`tool-research`, `tool-compose`): dry-run tests via `isolated_project` fixture
- Whitelist enforcement test: verify `failed:whitelist_violation` when Claude
  touches a blacklisted file

### 8. Operational Notes

- **Session log rotation**: `state/claude_sessions.jsonl` will grow at ~200 bytes
  per entry × 8/day = ~1.6 KB/day (~600 KB/year). No rotation needed; file will
  be trivially small. If it ever exceeds 5 MB, use `rotate_log()` from `state.py`.
- **Pi 4 resource cost**: Claude sessions are remote API calls — the Pi just
  launches a subprocess and waits. The 30-min timeout for evolve is a wall-clock
  wait, not a CPU-intensive operation. Multiple sessions cannot run concurrently
  (global cooldown enforces serialization).
- **Timeout hierarchy**: session type timeout (e.g., 1800s for evolve) is the
  subprocess timeout. The global cooldown (30 min) is measured from session END,
  not session start. A 30-min evolve session followed by a 30-min cooldown means
  the next session can start ~60 min after the evolve began.
