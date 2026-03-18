# Local Ollama Fallback for px-mind Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-tier LLM fallback chain to `px-mind` so reflection continues during internet outages or when M1.local is unreachable.

**Architecture:** `call_llm` currently tries Claude (tier 1) then M1 Ollama (tier 2) and gives up. We add tier 3: a local Ollama instance already running on the Pi itself. `call_ollama` is refactored to accept `host` and `model` parameters so both remote and local calls share one implementation. The local model defaults to `deepseek-r1:1.5b` (already installed).

**Tech Stack:** Python (bash heredoc in `bin/px-mind`), Ollama REST API (`/api/generate`), pytest with `_load_mind_helpers()` exec-based loader pattern (see `tests/test_mind_utils.py`).

---

## Context for the implementer

`bin/px-mind` is a bash script containing an embedded Python heredoc between `<<'PY'` and `PY`. All logic is in that Python block. Tests load it via `_load_mind_helpers()` in `tests/test_mind_utils.py` — this pattern execs the heredoc Python in a stubbed namespace. New tests for the fallback chain should use the same pattern.

The full LLM call chain lives in three functions (line numbers approximate — confirm with `grep -n` before editing):

| Function | Location | Purpose |
|---|---|---|
| `call_ollama(prompt, system)` | ~L880 | Calls `OLLAMA_HOST` (M1.local) |
| `call_claude_haiku(prompt, system)` | ~L909 | Calls Claude CLI |
| `call_llm(prompt, system, persona)` | ~L947 | Dispatches + Claude→Ollama fallback |

Relevant config constants (all near the top of the heredoc, ~L173):

```
OLLAMA_HOST  = os.environ.get("PX_OLLAMA_HOST", "http://M1.local:11434")
MODEL        = os.environ.get("PX_MIND_MODEL", "qwen3.5:0.8b")
MIND_BACKEND = os.environ.get("PX_MIND_BACKEND", "auto")
CLAUDE_MODEL = os.environ.get("PX_MIND_CLAUDE_MODEL", "claude-haiku-4-5-20251001")
```

Two new constants will be added alongside these:

```
LOCAL_OLLAMA_HOST = os.environ.get("PX_MIND_LOCAL_OLLAMA_HOST", "http://localhost:11434")
LOCAL_MODEL       = os.environ.get("PX_MIND_LOCAL_MODEL", "deepseek-r1:1.5b")
```

---

## File Map

| File | Action | What changes |
|---|---|---|
| `bin/px-mind` | Modify | New constants, refactor `call_ollama`, update `call_llm` |
| `tests/test_mind_fallback.py` | Create | Unit tests for the three-tier fallback chain |
| `CLAUDE.md` | Modify | Document new env vars and fallback behaviour |

---

## Chunk 1: Tests + Implementation

### Task 1: Write failing tests for the fallback chain

**Files:**
- Create: `tests/test_mind_fallback.py`

The test module loads `bin/px-mind` via the same exec-based loader used in `tests/test_mind_utils.py`. It patches `urllib.request.urlopen` and `subprocess.run` to simulate each tier failing.

- [ ] **Step 1: Create `tests/test_mind_fallback.py`**

```python
"""Tests for px-mind three-tier LLM fallback: Claude -> M1 Ollama -> local Ollama."""
from __future__ import annotations

import os, sys, types, json
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent


def _load_mind():
    src = (PROJECT_ROOT / "bin" / "px-mind").read_text()
    start = src.index("<<'PY'\n") + len("<<'PY'\n")
    end   = src.rindex("\nPY\n")
    py_src = src[start:end]

    import datetime as _dt
    stub_keys = ("pxh", "pxh.state", "pxh.logging", "pxh.time")
    saved = {k: sys.modules.get(k) for k in stub_keys}

    stub_pxh   = types.ModuleType("pxh")
    stub_state = types.ModuleType("pxh.state")
    stub_state.load_session   = lambda: {}
    stub_state.update_session = lambda **kw: None
    stub_state.save_session   = lambda s: None
    stub_log  = types.ModuleType("pxh.logging")
    stub_log.log_event = lambda *a, **kw: None
    stub_time = types.ModuleType("pxh.time")
    stub_time.utc_timestamp = lambda: _dt.datetime.now(_dt.timezone.utc).isoformat()

    for k, m in [("pxh", stub_pxh), ("pxh.state", stub_state),
                 ("pxh.logging", stub_log), ("pxh.time", stub_time)]:
        sys.modules[k] = m

    env_patch = {
        "PROJECT_ROOT": str(PROJECT_ROOT),
        "LOG_DIR":      str(PROJECT_ROOT / "logs"),
        "PX_STATE_DIR": str(PROJECT_ROOT / "state"),
        "PX_OLLAMA_HOST":             "http://M1.local:11434",
        "PX_MIND_LOCAL_OLLAMA_HOST":  "http://localhost:11434",
        "PX_MIND_LOCAL_MODEL":        "deepseek-r1:1.5b",
    }
    old_env = {k: os.environ.get(k) for k in env_patch}
    os.environ.update(env_patch)

    globs: dict = {"__file__": str(PROJECT_ROOT / "bin" / "px-mind")}
    try:
        exec(compile(py_src, "bin/px-mind", "exec"), globs)  # noqa: S102
    finally:
        for k, old_mod in saved.items():
            if old_mod is None: sys.modules.pop(k, None)
            else:               sys.modules[k] = old_mod
        for k, old_v in old_env.items():
            if old_v is None: os.environ.pop(k, None)
            else:             os.environ[k] = old_v

    return globs


_MIND = _load_mind()


def _fake_ollama_cm(text: str):
    """Mock urlopen context manager returning a valid Ollama response."""
    body = json.dumps({"response": text}).encode()
    inner = MagicMock()
    inner.read = lambda: body
    cm = MagicMock()
    cm.__enter__ = lambda s: inner
    cm.__exit__  = MagicMock(return_value=False)
    return cm


def _fake_claude(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode, m.stdout, m.stderr = returncode, stdout, stderr
    return m


# ── Tier-2 fallback: Claude fails → M1 Ollama succeeds ─────────────

def test_falls_back_to_m1_ollama_when_claude_fails():
    call_llm = _MIND["call_llm"]
    with patch("subprocess.run", return_value=_fake_claude(1, stderr="auth error")), \
         patch("urllib.request.urlopen", return_value=_fake_ollama_cm("quantum foam")):
        result = call_llm("prompt", "system", persona="spark")
    assert "error" not in result
    assert "quantum foam" in result["response"]


# ── Tier-3 fallback: Claude + M1 fail → local Ollama succeeds ──────

def test_falls_back_to_local_ollama_when_m1_fails():
    import urllib.error
    call_llm  = _MIND["call_llm"]
    call_count = [0]

    def urlopen_side(req, timeout=30):
        call_count[0] += 1
        if call_count[0] == 1:
            raise urllib.error.URLError("M1 unreachable")
        return _fake_ollama_cm("running on fumes").__enter__(None)

    with patch("subprocess.run", return_value=_fake_claude(1, stderr="offline")), \
         patch("urllib.request.urlopen", side_effect=urlopen_side):
        result = call_llm("prompt", "system", persona="spark")

    assert call_count[0] == 2, f"expected 2 urlopen calls, got {call_count[0]}"
    assert "error" not in result
    assert "fumes" in result["response"]


# ── Full failure: all three tiers fail → error dict, no exception ───

def test_returns_error_when_all_tiers_fail():
    import urllib.error
    call_llm = _MIND["call_llm"]
    with patch("subprocess.run", return_value=_fake_claude(1, stderr="offline")), \
         patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("all down")):
        result = call_llm("prompt", "system", persona="spark")
    assert "error" in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd /home/pi/picar-x-hacking
python -m pytest tests/test_mind_fallback.py -v 2>&1 | tail -15
```

Expected: 3 FAILED (the tier-3 path doesn't exist yet, `test_falls_back_to_local_ollama_when_m1_fails` will fail because there's no second urlopen call, `test_returns_error_when_all_tiers_fail` may pass accidentally — that's fine).

---

### Task 2: Add constants and update `bin/px-mind`

**Files:**
- Modify: `bin/px-mind`

- [ ] **Step 3: Add two new constants after the existing config block (~L173–174)**

Find:
```
OLLAMA_HOST  = os.environ.get("PX_OLLAMA_HOST", "http://M1.local:11434")
MODEL        = os.environ.get("PX_MIND_MODEL", "qwen3.5:0.8b")
```

Add immediately after:
```
LOCAL_OLLAMA_HOST = os.environ.get("PX_MIND_LOCAL_OLLAMA_HOST", "http://localhost:11434")
LOCAL_MODEL       = os.environ.get("PX_MIND_LOCAL_MODEL", "deepseek-r1:1.5b")
```

- [ ] **Step 4: Refactor `call_ollama` to accept optional `host` and `model` params**

Replace the entire `call_ollama` function with:

```python
def call_ollama(prompt: str, system: str,
                host: str | None = None,
                model: str | None = None) -> dict:
    """Call Ollama for reflection. host defaults to OLLAMA_HOST (M1.local)."""
    _host  = host  or OLLAMA_HOST
    _model = model or MODEL

    payload = json.dumps({
        "model": _model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "think": False,
        "options": {
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "num_predict": MAX_TOKENS,
        },
    }).encode()

    req = urllib.request.Request(
        f"{_host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        return {"error": f"ollama unreachable ({_host}): {exc}"}
    except Exception as exc:
        return {"error": str(exc)}
```

Only behavioural change: error message now includes `_host` for clarity. All existing call sites (`call_llm`) pass no host/model so they still use the M1 defaults.

- [ ] **Step 5: Update `call_llm` to add tier-3 local fallback**

Replace the entire `call_llm` function with:

```python
def call_llm(prompt: str, system: str, persona: str = "") -> dict:
    """Three-tier LLM fallback.

    Tier 1 — Claude Haiku (internet):  SPARK in auto mode, or MIND_BACKEND=claude
    Tier 2 — Ollama M1.local (LAN):    all personas, or when Claude fails
    Tier 3 — Ollama localhost (Pi):     final fallback when LAN/internet both down
    """
    use_claude = (
        MIND_BACKEND == "claude"
        or (MIND_BACKEND == "auto" and persona == "spark")
    )
    if use_claude:
        result = call_claude_haiku(prompt, system)
        if "error" not in result:
            return result
        log(f"claude failed ({result['error']}), falling back to ollama")

    # Tier 2: M1 Ollama
    result = call_ollama(prompt, system)
    if "error" not in result:
        return result

    # Tier 3: local Pi Ollama
    log(f"M1 ollama failed ({result['error']}), falling back to local ollama")
    return call_ollama(prompt, system, host=LOCAL_OLLAMA_HOST, model=LOCAL_MODEL)
```

- [ ] **Step 6: Run the tests — all three should now pass**

```
python -m pytest tests/test_mind_fallback.py -v
```

Expected:
```
PASSED tests/test_mind_fallback.py::test_falls_back_to_m1_ollama_when_claude_fails
PASSED tests/test_mind_fallback.py::test_falls_back_to_local_ollama_when_m1_fails
PASSED tests/test_mind_fallback.py::test_returns_error_when_all_tiers_fail
```

- [ ] **Step 7: Run the full test suite**

```
python -m pytest -m "not live" -q 2>&1 | tail -5
```

Expected: 0 new failures.

- [ ] **Step 8: Commit**

```
git add bin/px-mind tests/test_mind_fallback.py
git commit -m "feat(mind): three-tier LLM fallback — Claude -> M1 Ollama -> local Pi Ollama"
```

---

## Chunk 2: Model + Docs

### Task 3: Verify the local model is available

The Pi already has `deepseek-r1:1.5b` (1.1 GB) and local Ollama running as a systemd service. No pull needed unless you want a lighter alternative.

- [ ] **Step 9: Confirm local model present**

```
ollama list | grep deepseek-r1
```

Expected: `deepseek-r1:1.5b` listed. If absent: `ollama pull deepseek-r1:1.5b`

**Optional lighter model** (~270 MB, better for natural prose than the coder model):

```
ollama pull smollm2:135m
# then override: PX_MIND_LOCAL_MODEL=smollm2:135m in systemd or px-env
```

- [ ] **Step 10: Smoke-test local Ollama directly**

```
curl -s http://localhost:11434/api/generate \
  -d '{"model":"deepseek-r1:1.5b","prompt":"Complete: I am alive and","stream":false,"think":false}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response','ERROR')[:80])"
```

Expected: a short response string, not `ERROR`.

---

### Task 4: Document new env vars in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 11: Add two rows to the Key Environment Variables table**

After the `PX_OLLAMA_HOST` row, add:

```
| `PX_MIND_LOCAL_OLLAMA_HOST` | Tier-3 fallback Ollama host on Pi (default: `http://localhost:11434`) |
| `PX_MIND_LOCAL_MODEL`       | Tier-3 fallback model (default: `deepseek-r1:1.5b`) |
```

- [ ] **Step 12: Update the px-mind section's Layer 2 description**

Find: `Layer 2 backend: **Claude CLI for SPARK**; Ollama qwen3.5:0.8b for others`

Replace with: `Layer 2 backend: three-tier fallback — Claude CLI (SPARK, internet) → Ollama on M1.local (LAN) → Ollama on Pi localhost (offline). Falls back automatically on any error; each fallback step is logged.`

- [ ] **Step 13: Commit docs**

```
git add CLAUDE.md
git commit -m "docs: document three-tier px-mind LLM fallback and new env vars"
```

---

### Task 5: Restart and verify live

- [ ] **Step 14: Restart px-mind, confirm reflections succeed**

```
sudo systemctl restart px-mind && sleep 5 && tail -25 /home/pi/picar-x-hacking/logs/px-mind.log
```

If Claude auth is still broken, expect to see:
```
[mind] claude failed (...), falling back to ollama
[mind] reflection: mood=... action=... salience=...
```
instead of `reflection failed`.

- [ ] **Step 15 (optional): Simulate M1 outage**

```
sudo bash -c 'echo "192.0.2.1 M1.local" >> /etc/hosts'
sleep 70
tail -5 /home/pi/picar-x-hacking/logs/px-mind.log
# Expect: "M1 ollama failed ... falling back to local ollama" + successful reflection
sudo sed -i '/192.0.2.1 M1.local/d' /etc/hosts
```

---

## Summary

| Tier | Backend | When triggered |
|---|---|---|
| 1 | Claude Haiku (internet) | SPARK + `auto` mode, or `MIND_BACKEND=claude` |
| 2 | Ollama M1.local (LAN) | Claude fails, or non-SPARK persona |
| 3 | Ollama Pi localhost | M1.local unreachable |

Three new tests cover each transition. Two new env vars allow overriding both local settings. No new dependencies — Ollama is already installed and running on the Pi with `deepseek-r1:1.5b`.
