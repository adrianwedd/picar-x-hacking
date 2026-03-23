# Claude Session Manager & Extended Autonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SPARK autonomous Claude Code sessions for self-evolution, research, creative writing, self-debugging, and deep conversation — all managed by a central rate-limited session dispatcher.

**Architecture:** A new `claude_session.py` module centralises all Claude subprocess invocations with model routing, rate limiting, and logging. `px-evolve` is rewritten to use real tool access (no Bash) instead of the broken patch approach. Three new expression actions (`research`, `self_debug`, `compose`) and one voice loop enhancement (`conversation` depth) extend SPARK's cognitive capabilities.

**Tech Stack:** Python 3.11, `claude` CLI (subprocess), `filelock`, existing `pxh` library patterns.

**Spec:** `docs/superpowers/specs/2026-03-23-claude-session-manager-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/pxh/claude_session.py` | Create | Session manager: model routing, rate limiting, execution, logging, whitelist enforcement |
| `bin/tool-research` | Create | Research session tool (Haiku, text-only) |
| `bin/tool-compose` | Create | Creative writing tool (Haiku, text-only) |
| `bin/px-evolve` | Modify | Replace patch approach with real tool access via session manager |
| `src/pxh/mind.py` | Modify | New actions, expression routing, self-debug trigger |
| `src/pxh/voice_loop.py` | Modify | Register new tools, validate_action branches, conversation depth |
| `bin/tool-introspect` | Modify | Claude session stats, evolve outcome feedback |
| `bin/px-statusline` | Modify | Claude budget display |
| `src/pxh/api.py` | Modify | Budget fields in /public/status |
| `tests/test_claude_session.py` | Create | Unit tests for session manager |
| `tests/test_evolve_v2.py` | Create | Tests for rewritten evolve pipeline |

---

## Task 1: Claude Session Manager — Core Module

**Files:**
- Create: `src/pxh/claude_session.py`
- Create: `tests/test_claude_session.py`

This is the foundation — everything else depends on it.

- [ ] **Step 1: Write failing tests for model routing**

Create `tests/test_claude_session.py`:

```python
"""Tests for Claude session manager."""
import json
import os
import time
import datetime as dt
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _make_session_dir(tmp_path):
    sd = tmp_path / "state"
    sd.mkdir()
    return sd


class TestModelRouting:
    def test_evolve_uses_opus(self):
        from pxh.claude_session import _model_for_type
        assert "opus" in _model_for_type("evolve")

    def test_self_debug_uses_sonnet(self):
        from pxh.claude_session import _model_for_type
        assert "sonnet" in _model_for_type("self_debug")

    def test_research_uses_haiku(self):
        from pxh.claude_session import _model_for_type
        assert "haiku" in _model_for_type("research")

    def test_compose_uses_haiku(self):
        from pxh.claude_session import _model_for_type
        assert "haiku" in _model_for_type("compose")

    def test_conversation_uses_sonnet(self):
        from pxh.claude_session import _model_for_type
        assert "sonnet" in _model_for_type("conversation")

    def test_env_override(self):
        from pxh.claude_session import _model_for_type
        with patch.dict(os.environ, {"PX_CLAUDE_MODEL_EVOLVE": "claude-test-model"}):
            assert _model_for_type("evolve") == "claude-test-model"

    def test_unknown_type_raises(self):
        from pxh.claude_session import _model_for_type
        with pytest.raises(ValueError):
            _model_for_type("nonexistent")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestModelRouting -v`
Expected: ImportError — module doesn't exist yet

- [ ] **Step 3: Write model routing implementation**

Create `src/pxh/claude_session.py` with:
- Imports: `datetime`, `json`, `os`, `subprocess`, `time`, `dataclasses`, `pathlib`, `zoneinfo`, `filelock`
- Constants: `HOBART_TZ`, `PROJECT_ROOT`, `STATE_DIR`, `SESSION_LOG`, `SESSION_LOCK`
- `_DEFAULT_MODELS` dict mapping session type to model string
- `_ENV_OVERRIDES` dict mapping session type to env var name
- `_model_for_type(session_type: str) -> str` function

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestModelRouting -v`
Expected: 7 passed

- [ ] **Step 5: Write failing tests for rate limiting**

Add `TestRateLimiting` class to `tests/test_claude_session.py` with tests for:
- Empty log allows all sessions
- Global cooldown blocks non-exempt types
- `self_debug` exempt from global cooldown
- Daily cap blocks at limit
- Per-type cooldown blocks recent same-type sessions
- Per-type quota blocks when exceeded
- Corrupt log lines are skipped gracefully
- Priority gating: low-priority blocked when <=2 sessions remain
- Cold start: missing session log file returns None (allowed)
- `PX_CLAUDE_BUDGET_DISABLED=1` bypasses all checks
- DST day-boundary rollover: session logged at 23:30 AEDT is "today" in AEDT
  but must not become "tomorrow" after DST switch
- Concurrent FileLock serialization (mock-based: verify lock acquire/release calls)

Each test creates a tmp_path session dir, writes test entries to a mock session log, and patches `SESSION_LOG` to point at it.

- [ ] **Step 6: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestRateLimiting -v`
Expected: ImportError for `check_budget`

- [ ] **Step 7: Write rate limiting implementation**

Add to `src/pxh/claude_session.py`:
- Constants: `COOLDOWN_S`, `DAILY_CAP`, `BUDGET_DISABLED`, `_TYPE_COOLDOWNS`, `_TYPE_QUOTAS`, `_PRIORITY`, `_GLOBAL_COOLDOWN_EXEMPT`
- `_load_session_log() -> list[dict]` — reads JSONL, skips malformed lines
- `_today_entries(entries) -> list[dict]` — filters to Hobart-timezone today
- `check_budget(session_type: str) -> str | None` — returns None if allowed, reason string if blocked. Checks in order: budget disabled bypass, daily cap, priority gating, per-type quota, global cooldown (exempt for self_debug), per-type cooldown

- [ ] **Step 8: Run rate limiting tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestRateLimiting -v`
Expected: 9 passed

- [ ] **Step 9: Write failing tests for session execution**

Add `TestRunSession` class with tests for:
- `SessionBudgetExhausted` raised when budget blocked
- Successful session logged to session log file
- Claude Code env vars (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT) stripped from subprocess env

- [ ] **Step 10: Write session execution implementation**

Add to `src/pxh/claude_session.py`:
- `SessionBudgetExhausted(Exception)` class
- `RunResult` dataclass: stdout, stderr, returncode, duration_s, model_used
- `_log_session(session_type, model, duration_s, returncode, outcome)` — generates a `session_id` (format: `sess-YYYYMMDD-HHMMSS-NNN`), appends to session log using `atomic_write` from `state.py` with `FileLock` protection (read-append-write pattern, not bare file append)
- `run_claude_session(session_type, prompt, timeout, allowed_tools, skip_permissions, cwd) -> RunResult` — budget check, model routing, subprocess execution, logging

The `run_claude_session` function:
1. Calls `check_budget()` — raises `SessionBudgetExhausted` if blocked
2. Gets model via `_model_for_type()`
3. Builds `claude -p` command with `--model`, `--no-session-persistence`, `--output-format text`, `--allowedTools`
4. Optionally adds `--dangerously-skip-permissions`
5. Strips CLAUDECODE/CLAUDE_CODE_* env vars
6. Runs subprocess with timeout
7. Logs session result
8. Returns `RunResult`

- [ ] **Step 11: Run all session manager tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py -v`
Expected: All passed

- [ ] **Step 12: Add whitelist enforcement functions**

Add to `src/pxh/claude_session.py` (used by px-evolve, must be importable):

```python
WHITELIST_PATTERNS = [
    "src/pxh/spark_config.py",
    "src/pxh/mind.py",
    "src/pxh/voice_loop.py",
    "bin/tool-",
    "tests/",
    "docs/prompts/",
]

BLACKLIST_FILES = {
    "src/pxh/api.py",
    "bin/tool-chat",
    "bin/tool-chat-vixen",
    "bin/px-evolve",
    ".env",
}

# Blacklist patterns (prefix match)
BLACKLIST_PATTERNS = [
    "docs/prompts/persona-",   # jailbreak prompts — never allow editing
    "systemd/",
]


def file_in_whitelist(path: str) -> bool:
    if path in BLACKLIST_FILES:
        return False
    if any(path.startswith(p) for p in BLACKLIST_PATTERNS):
        return False
    return any(path.startswith(p) or path == p for p in WHITELIST_PATTERNS)
```

Add whitelist tests to `tests/test_claude_session.py`:

```python
class TestWhitelist:
    def test_spark_config_allowed(self):
        from pxh.claude_session import file_in_whitelist
        assert file_in_whitelist("src/pxh/spark_config.py")

    def test_mind_allowed(self):
        from pxh.claude_session import file_in_whitelist
        assert file_in_whitelist("src/pxh/mind.py")

    def test_api_blacklisted(self):
        from pxh.claude_session import file_in_whitelist
        assert not file_in_whitelist("src/pxh/api.py")

    def test_px_evolve_blacklisted(self):
        from pxh.claude_session import file_in_whitelist
        assert not file_in_whitelist("bin/px-evolve")

    def test_new_tool_allowed(self):
        from pxh.claude_session import file_in_whitelist
        assert file_in_whitelist("bin/tool-newfeature")

    def test_test_file_allowed(self):
        from pxh.claude_session import file_in_whitelist
        assert file_in_whitelist("tests/test_new.py")

    def test_env_blacklisted(self):
        from pxh.claude_session import file_in_whitelist
        assert not file_in_whitelist(".env")

    def test_persona_prompt_blacklisted(self):
        from pxh.claude_session import file_in_whitelist
        assert not file_in_whitelist("docs/prompts/persona-gremlin.md")
        assert not file_in_whitelist("docs/prompts/persona-vixen.md")
```

- [ ] **Step 13: Run all tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py -v`
Expected: All passed (model routing + rate limiting + execution + whitelist)

- [ ] **Step 14: Commit**

```
git add src/pxh/claude_session.py tests/test_claude_session.py
git commit -m "feat: add Claude session manager with model routing, rate limiting, execution, and whitelist"
```

---

## Task 2: Rewrite px-evolve Pipeline

**Files:**
- Modify: `bin/px-evolve` (replace build_prompt lines ~125-158, replace _run_in_worktree lines ~190-370)
- Create: `tests/test_evolve_v2.py`

- [ ] **Step 1: Write tests for evolve prompt and flow**

Create `tests/test_evolve_v2.py`. Note: whitelist tests are already in Task 1
(`tests/test_claude_session.py::TestWhitelist`). This file tests the evolve-specific
flow via subprocess (since px-evolve is a bash heredoc, not importable).

- [ ] **Step 2: Rewrite build_prompt in px-evolve**

Replace `build_prompt` function. New version:
- Imports `file_in_whitelist` from `pxh.claude_session` (not local — the function lives in the importable module)
- `build_prompt(intent, introspection) -> str` — clean prompt telling Claude to use Edit/Write tools directly. **Do NOT tell Claude to run `git commit`** — px-evolve commits after Claude exits. Lists whitelist and blacklist. Max files constraint.

- [ ] **Step 4: Rewrite _run_in_worktree**

Replace `_run_in_worktree` function. New flow:
1. Call `run_claude_session(type="evolve", allowed_tools="Read,Write,Edit,Glob,Grep", skip_permissions=True, cwd=workdir, timeout=EVOLVE_TIMEOUT)` where `EVOLVE_TIMEOUT` is updated from 600 to **1800** (30 min, per spec). Wire via `PX_EVOLVE_TIMEOUT` env var.
2. After Claude exits: `git add -A`, check `git diff --cached --name-only` for staged changes
3. If changes: `git commit -m "[SPARK] {intent[:60]}"`
4. Whitelist enforcement: `git diff --name-only master...HEAD`, validate each file via `file_in_whitelist()`
5. Max files check
6. Run pytest (with `--ignore=tests/test_tools_live.py`)
7. Push branch, create PR with `--label spark-evolve`

Handle errors at each stage: `failed:budget`, `failed:timeout`, `failed:no_changes`, `failed:whitelist_violation`, `failed:too_many_files`, `failed:tests`, `failed:pr_create`

- [ ] **Step 5: Run all evolve tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_evolve_coverage.py tests/test_evolve_v2.py -v --tb=short`
Expected: All pass

- [ ] **Step 6: Commit**

```
git add bin/px-evolve tests/test_evolve_v2.py
git commit -m "feat: rewrite px-evolve to use session manager with real tool access"
```

---

## Task 3: tool-research

**Files:**
- Create: `bin/tool-research`
- Modify: `src/pxh/voice_loop.py` (ALLOWED_TOOLS ~line 26, TOOL_COMMANDS ~line 67, validate_action ~line 649)
- Add test in: `tests/test_tools.py`

- [ ] **Step 1: Write dry-run test**

Add `test_tool_research_dry_run` to `tests/test_tools.py`:
- Sets `PX_DRY=1`, `PX_RESEARCH_QUERY="Why do magnets work?"`
- Runs `bin/tool-research`
- Asserts `status=ok`, `dry=True`

- [ ] **Step 2: Create bin/tool-research**

Bash + Python heredoc pattern. Main function:
- Reads `PX_RESEARCH_QUERY` from env
- Dry mode: logs and returns `{"status": "ok", "dry": true}`
- Live mode: calls `run_claude_session(type="research", prompt=..., timeout=300, allowed_tools="")` — explicitly no tool access (Haiku text-only, per spec)
- Saves result to `notes_file_for_persona("spark")` as JSONL entry with type=research
- Returns `{"status": "ok", "query": ...}`

Make executable with `chmod +x`.

- [ ] **Step 3: Register in voice_loop.py**

- Add `"tool_research"` to `ALLOWED_TOOLS` set
- Add `"tool_research": BIN_DIR / "tool-research"` to `TOOL_COMMANDS`
- Add `elif tool == "tool_research":` branch in `validate_action()` — sanitize `query` param (min 5 chars, max 500 chars)

- [ ] **Step 4: Run test and commit**

```
source .venv/bin/activate && python -m pytest tests/test_tools.py::test_tool_research_dry_run -v
git add bin/tool-research src/pxh/voice_loop.py tests/test_tools.py
git commit -m "feat: add tool-research for SPARK curiosity-driven deep dives"
```

---

## Task 4: tool-compose

**Files:**
- Create: `bin/tool-compose`
- Modify: `src/pxh/voice_loop.py`
- Add test in: `tests/test_tools.py`

Follows identical pattern to Task 3.

- [ ] **Step 1: Write dry-run test**

Add `test_tool_compose_dry_run` to `tests/test_tools.py`:
- Sets `PX_DRY=1`, `PX_COMPOSE_TOPIC="morning observation"`
- Asserts `status=ok`, `dry=True`

- [ ] **Step 2: Create bin/tool-compose**

Same pattern as tool-research but:
- Reads `PX_COMPOSE_TOPIC` env var
- Session type: `"compose"`, `allowed_tools=""` (text-only, no tool access per spec)
- Prompt: creative writing in SPARK's voice (journal entry / letter / observation)
- Output saved to `state/compositions-spark.jsonl`

Make executable with `chmod +x`.

- [ ] **Step 3: Register in voice_loop.py**

- Add `"tool_compose"` to `ALLOWED_TOOLS` and `TOOL_COMMANDS`
- Add `validate_action` branch — sanitize `topic` param

- [ ] **Step 4: Run test and commit**

```
source .venv/bin/activate && python -m pytest tests/test_tools.py::test_tool_compose_dry_run -v
git add bin/tool-compose src/pxh/voice_loop.py tests/test_tools.py
git commit -m "feat: add tool-compose for SPARK creative writing sessions"
```

---

## Task 5: Self-Debug Integration in mind.py

**Files:**
- Modify: `src/pxh/mind.py` (VALID_ACTIONS ~line 357, expression() ~line 2847, reflection failure ~line 3046)
- Add test in: `tests/test_claude_session.py`

- [ ] **Step 1: Write test for self_debug in action sets**

Add `TestSelfDebugTrigger` class:
- Verify `"self_debug"` is in `VALID_ACTIONS`
- Verify `"self_debug"` is NOT in `ABSENT_GATED_ACTIONS`
- Verify `"self_debug"` is NOT in `CHARGING_GATED_ACTIONS`

Note: `REFLECTION_FAIL_WARN_THRESHOLD` is a local variable inside `main_loop()` at
line 2949, not a module-level constant. Do not try to import it. The threshold
value (3) is tested implicitly by the integration test.

- [ ] **Step 2: Add self_debug to VALID_ACTIONS and update reflection prompts**

At `src/pxh/mind.py:357`, add `"self_debug"` to the set.

**CRITICAL**: Also update the reflection prompt strings that list valid actions.
Search for the action list in `REFLECTION_SYSTEM_SPARK` (and GREMLIN/VIXEN variants)
in `src/pxh/spark_config.py` — these are the prompts the LLM sees. If `research`,
`self_debug`, and `compose` are not listed there, the LLM will **never output them**.
Add all three new actions with brief descriptions to the prompt's action list.

- [ ] **Step 3: Add self_debug branch in expression()**

After the `"evolve"` branch (~line 2847), add `elif action == "self_debug":` branch that:
1. Gathers diagnostic context: recent log tail, awareness state, failure count
2. Calls `run_claude_session(type="self_debug", allowed_tools="Read,Glob,Grep", timeout=600)`
3. Saves diagnostic report to `state/debug_reports.jsonl`
4. Catches `SessionBudgetExhausted` gracefully

- [ ] **Step 4: Add self_debug trigger on reflection failures**

At ~line 3046, when `_consecutive_reflection_failures` hits multiples of `REFLECTION_FAIL_WARN_THRESHOLD`, set a flag `_pending_self_debug = True`. In the main loop, check this flag and dispatch a synthetic thought with `action="self_debug"`.

- [ ] **Step 5: Run tests and commit**

```
source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestSelfDebugTrigger -v
git add src/pxh/mind.py tests/test_claude_session.py
git commit -m "feat: add self_debug action triggered by consecutive reflection failures"
```

---

## Task 6: Conversation Depth in Voice Loop

**Files:**
- Modify: `src/pxh/voice_loop.py`
- Add test in: `tests/test_claude_session.py`

- [ ] **Step 1: Write test for trigger detection**

Add `TestConversationDepthTrigger` class:
- `is_depth_trigger("think about that more")` returns True
- `is_depth_trigger("go deeper on that")` returns True
- `is_depth_trigger("explain that properly")` returns True
- `is_depth_trigger("hello there")` returns False

- [ ] **Step 2: Add trigger detection function**

Add to `src/pxh/voice_loop.py`:
- `_DEPTH_TRIGGERS` set of trigger phrases
- `is_depth_trigger(text: str) -> bool` — checks if any trigger phrase is in lowercase text

- [ ] **Step 3: Add depth handling in response processing**

In the voice loop's response handling, before normal LLM call:
- Check `is_depth_trigger(user_text)`
- If triggered: call `run_claude_session(type="conversation", ...)` with Sonnet
- Route response through `execute_tool("tool_voice", ...)` to preserve persona voice env, token logging, voice locks
- On any error: fall through to normal processing

- [ ] **Step 4: Run tests and commit**

```
source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestConversationDepthTrigger -v
git add src/pxh/voice_loop.py tests/test_claude_session.py
git commit -m "feat: add conversation depth trigger for Sonnet deep-dive responses"
```

---

## Task 7: Expression Layer Integration in mind.py

**Files:**
- Modify: `src/pxh/mind.py` (VALID_ACTIONS, ABSENT_GATED_ACTIONS, _daytime_action_hint, expression)

- [ ] **Step 1: Add new actions to gate constants**

- Add `"research"`, `"compose"` to `VALID_ACTIONS` (~line 357)
- Add `"research"`, `"compose"` to `ABSENT_GATED_ACTIONS` (~line 364) — NOT `self_debug`
- Do NOT add any of these to `CHARGING_GATED_ACTIONS` (no GPIO)

- [ ] **Step 2: Update _daytime_action_hint() and reflection prompts**

At ~line 144, add nudges for quiet daytime:
- Compose/research suggested during calm periods
- Never suggest self_debug via hints (it's failure-triggered only)

**CRITICAL**: Update the SPARK reflection prompt in `src/pxh/spark_config.py` to list
the new actions (`research`, `compose`, `self_debug`) with descriptions. Without this,
the LLM will never output these actions. Look for the action list in the prompt string
(search for `"action":` or the list of valid actions like `wait`, `greet`, `comment`).
Add:
- `research` — "pursue a curiosity deep-dive on a topic you find fascinating"
- `compose` — "write a creative journal entry, letter, or observation"
- `self_debug` — "diagnose why your reflection layer is failing (only when errors persist)"

- [ ] **Step 3: Add research and compose branches in expression()**

After the `self_debug` branch:
- `elif action == "research":` — reads thought text as query, runs `bin/tool-research` via subprocess
- `elif action == "compose":` — reads thought text as topic, runs `bin/tool-compose` via subprocess

Both pass `PX_DRY` env var and use 360s timeout.

- [ ] **Step 4: Run full non-live test suite**

Run: `source .venv/bin/activate && python -m pytest -m "not live" --tb=short -q`
Expected: All pass

- [ ] **Step 5: Commit**

```
git add src/pxh/mind.py
git commit -m "feat: integrate research, compose, self_debug into expression layer"
```

---

## Task 8: Integration Points (Statusline, API, Introspect)

**Files:**
- Modify: `bin/px-statusline`
- Modify: `src/pxh/api.py` (~line 510)
- Modify: `bin/tool-introspect`

- [ ] **Step 1: Add Claude budget to px-statusline**

In the `parts` assembly section, add a new field using `_load_session_log()` and `_today_entries()` from `claude_session.py`. Format: `🧠{used}/{cap}`. Wrapped in try/except (statusline must never crash).

- [ ] **Step 2: Add budget fields to /public/status API**

In `public_status()` function, add `claude_sessions_today` (int) and `claude_budget_remaining` (int) to the response dict. Wrapped in try/except.

- [ ] **Step 3: Add Claude stats and evolve outcomes to tool-introspect**

In `main()`, before writing introspection payload:
- `claude_sessions`: today's count, by_type breakdown, total_duration_s
- `evolve_outcomes`: query recent PRs via `gh pr list --state all --head spark/evolve- --json number,state,title,mergedAt,reviews --limit 5`. For each PR, also fetch comments via `gh pr view {number} --json comments` to surface reviewer feedback — this is the learning loop that lets SPARK iterate on rejected proposals.

- [ ] **Step 4: Run tests and commit**

```
source .venv/bin/activate && python -m pytest -m "not live" --tb=short -q
git add bin/px-statusline src/pxh/api.py bin/tool-introspect
git commit -m "feat: add Claude session budget to statusline, API, and introspect"
```

---

## Task 9: Update Documentation, Prompts, and .gitignore

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/prompts/claude-voice-system.md`
- Modify: `docs/prompts/codex-voice-system.md`
- Modify: `docs/prompts/persona-gremlin.md`
- Modify: `docs/prompts/persona-vixen.md`
- Modify: `.gitignore`

- [ ] **Step 1: Add new state files to .gitignore**

Add these entries to `.gitignore` (in the state files section):

```
state/claude_sessions.jsonl
state/debug_reports.jsonl
state/compositions-spark.jsonl
```

- [ ] **Step 2: Update CLAUDE.md**

Update the Self-Evolution section to document:
- Session manager (`src/pxh/claude_session.py`) and its responsibilities
- Five session types with model routing table
- Rate limiting (global cooldown, daily cap, per-type quotas)
- Updated evolve pipeline (real tool access, no Bash, whitelist enforcement)
- New capabilities: research, compose, self_debug, conversation depth
- New env vars: `PX_CLAUDE_MODEL_*`, `PX_CLAUDE_DAILY_CAP`, `PX_CLAUDE_COOLDOWN_S`, `PX_CLAUDE_BUDGET_DISABLED`
- New state files: `claude_sessions.jsonl`, `debug_reports.jsonl`, `compositions-spark.jsonl`
- Update `PX_EVOLVE_TIMEOUT` default from 300s to 1800s

- [ ] **Step 3: Update voice system prompts**

Add "think deeper", "go deeper", "explain that properly" as recognised trigger
phrases that invoke a Sonnet deep-dive session.

Per CLAUDE.md "Adding a New Tool" checklist (steps 4-5), also add `tool-research`
and `tool-compose` to:
- `docs/prompts/claude-voice-system.md`
- `docs/prompts/codex-voice-system.md`
- `docs/prompts/persona-gremlin.md`
- `docs/prompts/persona-vixen.md`

- [ ] **Step 4: Commit**

```
git add CLAUDE.md .gitignore docs/prompts/claude-voice-system.md docs/prompts/codex-voice-system.md docs/prompts/persona-gremlin.md docs/prompts/persona-vixen.md
git commit -m "docs: update CLAUDE.md, prompts, and gitignore for session manager"
```

---

## Task 10: Final Integration Test

- [ ] **Step 1: Run full non-live test suite**

Run: `source .venv/bin/activate && python -m pytest -m "not live" --tb=short -q`
Expected: All existing + new tests pass, 0 failures

- [ ] **Step 2: Verify dry-run of new tools**

```bash
PX_DRY=1 PX_RESEARCH_QUERY="Why does the sky change colour?" bin/tool-research
PX_DRY=1 PX_COMPOSE_TOPIC="morning light" bin/tool-compose
```
Expected: `{"status": "ok", "dry": true}` for each

- [ ] **Step 3: Verify statusline includes budget**

```bash
bin/px-statusline
```
Expected: Output includes `🧠0/8` (or similar budget display)

- [ ] **Step 4: Push all changes**

```bash
git push
```
