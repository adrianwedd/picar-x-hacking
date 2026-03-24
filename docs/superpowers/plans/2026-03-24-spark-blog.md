# SPARK Blog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SPARK recursive reflective writing (daily/weekly/monthly/yearly blog posts) and on-demand essays, published to a new `/blog/` page on spark.wedd.au.

**Architecture:** A `px-blog` daemon runs on a Hobart-time schedule, reads thoughts/child posts, calls `run_claude_session(type="blog")` to generate reflections, QA-gates them, and writes to `state/blog.json`. A `tool-blog` tool handles on-demand essays. A new `/blog/` page renders posts from a `/public/blog` API endpoint.

**Tech Stack:** Python 3.11, `claude` CLI (subprocess via `claude_session.py`), `filelock`, FastAPI, vanilla JS/CSS.

**Spec:** `docs/superpowers/specs/2026-03-24-spark-blog-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/pxh/claude_session.py` | Modify | Add `blog` to all 5 dicts + `_GLOBAL_COOLDOWN_EXEMPT` |
| `bin/px-blog` | Create | Daemon: scheduled reflections, catch-up, QA gate, publish |
| `bin/tool-blog` | Create | On-demand essay tool |
| `systemd/px-blog.service` | Create | Systemd unit |
| `src/pxh/mind.py` | Modify | `blog_essay` action + expression branch |
| `src/pxh/voice_loop.py` | Modify | Register tool-blog |
| `src/pxh/spark_config.py` | Modify | Add `blog_essay` to reflection prompt |
| `src/pxh/api.py` | Modify | `/public/blog` endpoint |
| `site/blog/index.html` | Create | Blog page |
| `site/js/blog.js` | Create | Fetch + render blog posts |
| `site/index.html` | Modify | Nav link |
| `site/workers/og-rewrite.js` | Modify | `/blog/` route |
| `tests/test_tools.py` | Modify | `test_tool_blog_dry_run` |
| `tests/test_blog.py` | Create | Daemon + integration tests |
| `CLAUDE.md` | Modify | Document blog system |
| `.gitignore` | Modify | New state files |
| `docs/prompts/*.md` | Modify | Add tool-blog to all 5 prompt files |

---

## Task 1: Add `blog` Session Type to `claude_session.py`

**Files:**
- Modify: `src/pxh/claude_session.py`
- Modify: `tests/test_claude_session.py`

- [ ] **Step 1: Write failing tests for blog session type**

Add to `tests/test_claude_session.py`:

```python
class TestBlogSessionType:
    def test_blog_uses_haiku(self):
        from pxh.claude_session import _model_for_type
        assert "haiku" in _model_for_type("blog")

    def test_blog_env_override(self):
        from pxh.claude_session import _ENV_OVERRIDES
        assert "blog" in _ENV_OVERRIDES
        assert _ENV_OVERRIDES["blog"] == "PX_CLAUDE_MODEL_BLOG"

    def test_blog_cooldown(self):
        from pxh.claude_session import _TYPE_COOLDOWNS
        assert _TYPE_COOLDOWNS["blog"] == 1800  # 30 min

    def test_blog_quota(self):
        from pxh.claude_session import _TYPE_QUOTAS
        assert _TYPE_QUOTAS["blog"] == 3

    def test_blog_priority(self):
        from pxh.claude_session import _PRIORITY
        assert "blog" in _PRIORITY
        assert _PRIORITY["blog"] == 2

    def test_blog_exempt_from_global_cooldown(self):
        from pxh.claude_session import _GLOBAL_COOLDOWN_EXEMPT
        assert "blog" in _GLOBAL_COOLDOWN_EXEMPT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestBlogSessionType -v`
Expected: ImportError or AssertionError — `blog` not in dicts yet

- [ ] **Step 3: Add blog to all 6 locations in claude_session.py**

In `src/pxh/claude_session.py`:
- `_DEFAULT_MODELS["blog"] = "claude-haiku-4-5-20251001"`
- `_ENV_OVERRIDES["blog"] = "PX_CLAUDE_MODEL_BLOG"`
- `_TYPE_COOLDOWNS["blog"] = 1800`
- `_TYPE_QUOTAS["blog"] = 3`
- `_PRIORITY["blog"] = 2`
- Add `"blog"` to `_GLOBAL_COOLDOWN_EXEMPT`

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_claude_session.py::TestBlogSessionType -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/pxh/claude_session.py tests/test_claude_session.py
git commit -m "feat: add blog session type to claude_session.py"
```

---

## Task 2: Create `bin/tool-blog` (On-Demand Essays)

**Files:**
- Create: `bin/tool-blog`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write dry-run test**

Add to `tests/test_tools.py`:

```python
def test_tool_blog_dry_run(isolated_project):
    env = isolated_project["env"].copy()
    env["PX_DRY"] = "1"
    env["PX_BLOG_TOPIC"] = "Why robots dream"
    result = subprocess.run(
        [str(PROJECT_ROOT / "bin" / "tool-blog")],
        capture_output=True, text=True, env=env, timeout=10,
    )
    data = parse_json(result.stdout)
    assert data["status"] == "ok"
    assert data["dry"] is True
```

- [ ] **Step 2: Create bin/tool-blog**

Bash + Python heredoc. Pattern: read `PX_BLOG_TOPIC`, dry-run check, call `run_claude_session(type="blog")`, QA gate (bypass with `PX_BLOG_QA=0`), append to `state/blog.json` envelope, return JSON. Make executable with `chmod +x`.

- [ ] **Step 3: Run test**

Run: `source .venv/bin/activate && python -m pytest tests/test_tools.py::test_tool_blog_dry_run -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bin/tool-blog tests/test_tools.py
git commit -m "feat: add tool-blog for on-demand essays"
```

---

## Task 3: Register `tool-blog` in Voice Loop + Mind Expression

**Files:**
- Modify: `src/pxh/voice_loop.py`
- Modify: `src/pxh/mind.py`
- Modify: `src/pxh/spark_config.py`

- [ ] **Step 1: Add to voice_loop.py**

- Add `"tool_blog"` to `ALLOWED_TOOLS`
- Add `"tool_blog": BIN_DIR / "tool-blog"` to `TOOL_COMMANDS`
- Add `validate_action` branch per spec (min 5 chars topic)

- [ ] **Step 2: Add blog_essay to mind.py**

- Add `"blog_essay"` to `VALID_ACTIONS`
- Add `"blog_essay"` to `ABSENT_GATED_ACTIONS`
- Add expression handler after the `compose` branch:

```python
elif action == "blog_essay":
    env["PX_BLOG_TOPIC"] = text[:500]
    env["PX_DRY"] = "1" if dry else "0"
    result = subprocess.run(
        [str(BIN_DIR / "tool-blog")],
        capture_output=True, text=True, check=False, env=env, timeout=360)
    log(f"expression: blog_essay completed rc={result.returncode}")
```

- [ ] **Step 3: Update spark_config.py reflection prompt**

Add `"blog_essay"` to the action list in `_SPARK_REFLECTION_SUFFIX` with description:
`- "blog_essay" — write a blog post about something you find genuinely fascinating.`

Also add to all 3 persona reflection prompts (GREMLIN/VIXEN action lists in mind.py).

- [ ] **Step 4: Update test_mind_utils.py expected actions**

Update `test_valid_actions_includes_new_actions` — change count from 20 to 21, add `"blog_essay"`.

- [ ] **Step 5: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_mind_utils.py::test_valid_actions_includes_new_actions tests/test_mind_utils.py::test_explore_injection_after_enum_expansion -v`
Expected: Both pass

- [ ] **Step 6: Commit**

```bash
git add src/pxh/voice_loop.py src/pxh/mind.py src/pxh/spark_config.py tests/test_mind_utils.py
git commit -m "feat: register tool-blog in voice loop + blog_essay in mind expression"
```

---

## Task 4: Create `bin/px-blog` Daemon

**Files:**
- Create: `bin/px-blog`
- Create: `tests/test_blog.py`

This is the largest task — the core daemon with scheduling, catch-up, and recursive reflections.

- [ ] **Step 1: Write daemon tests**

Create `tests/test_blog.py` with:

```python
class TestBlogSchedule:
    def test_daily_idempotent(self):
        """Skip if today's daily already exists."""
    def test_catchup_on_missed(self):
        """Generate missing yesterday's daily on next poll."""
    def test_catchup_ordering(self):
        """Dailies generate before weekly on same poll."""
    def test_min_thoughts_threshold(self):
        """Skip daily if <3 thoughts."""
    def test_weekly_skips_no_dailies(self):
        """Skip weekly if 0 dailies for period."""
    def test_weekly_gathers_dailies(self):
        """Weekly prompt includes the week's dailies."""
    def test_budget_exhausted_retries(self):
        """Log warning, retry next poll on budget block."""
    def test_blog_limit_trims(self):
        """Trim to 500 posts when appending."""
```

Each test mocks `state/blog.json`, `state/thoughts-spark.jsonl`, and `run_claude_session`. Tests use `tmp_path` for state isolation.

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_blog.py -v`
Expected: ImportError — daemon not written yet

- [ ] **Step 3: Create bin/px-blog**

Bash + Python heredoc pattern (same as px-evolve). Key functions:
- `is_due(post_type) -> bool` — check Hobart time against schedule
- `needs_post(post_type, date_str) -> bool` — idempotency check against blog.json
- `gather_thoughts(date) -> list[str]` — read thoughts-spark.jsonl for the date
- `gather_children(post_type, period) -> list[dict]` — read child blog posts
- `generate_post(post_type, source_material) -> dict | None` — claude session + QA
- `append_post(post) -> None` — atomic read-append-write with BLOG_LIMIT trim
- `run_once() -> int` — check all periods in order (daily→weekly→monthly→yearly)
- `main()` — PID guard, SIGTERM, poll loop

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_blog.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add bin/px-blog tests/test_blog.py
git commit -m "feat: add px-blog daemon with scheduled reflections and catch-up"
```

---

## Task 5: API Endpoint + Systemd Service

**Files:**
- Modify: `src/pxh/api.py`
- Create: `systemd/px-blog.service`
- Modify: `.gitignore`

- [ ] **Step 1: Add /public/blog endpoint**

In `src/pxh/api.py`, add after the `/public/feed` endpoint:

```python
@app.get("/api/v1/public/blog")
async def public_blog() -> Dict[str, Any]:
    """Blog posts — daily/weekly/monthly/yearly reflections + essays."""
    blog_file = STATE_DIR / "blog.json"
    try:
        return json.loads(blog_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"updated": None, "posts": []}
```

- [ ] **Step 2: Add test**

Add to `tests/test_blog.py`:

```python
def test_blog_api_endpoint(self):
    """Verify /public/blog returns envelope."""
```

Or add to `tests/test_api.py` if that's where endpoint tests live.

- [ ] **Step 3: Create systemd service**

`systemd/px-blog.service`:
```ini
[Unit]
Description=SPARK Blog Daemon
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/picar-x-hacking
ExecStart=/home/pi/picar-x-hacking/bin/px-blog
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=0
EnvironmentFile=/home/pi/picar-x-hacking/.env

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Update .gitignore**

Add:
```
state/blog.json
state/blog_log.jsonl
```

- [ ] **Step 5: Run API tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_api.py -v --tb=short`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/pxh/api.py systemd/px-blog.service .gitignore
git commit -m "feat: add /public/blog API endpoint + px-blog systemd service"
```

---

## Task 6: Site — `/blog/` Page

**Files:**
- Create: `site/blog/index.html`
- Create: `site/js/blog.js`
- Modify: `site/index.html` (nav link)

- [ ] **Step 1: Create blog/index.html**

Copy structure from `site/feed/index.html`. Change: title to "Blog — SPARK", heading to "SPARK's Blog", subtitle to "Reflections, essays, and the arc of a thinking life." Add `blog.js` script.

- [ ] **Step 2: Create blog.js**

Pattern matches `feed.js`. Key differences:
- Fetches from `/api/v1/public/blog`
- Posts have `type` field — render different card sizes per type
- Individual post view at `/blog/?id=<id>` (not `?ts=`)
- Pagination: 10 posts, "Load more"
- Date labels (reuse feed.js date grouping pattern)

- [ ] **Step 3: Add nav link**

In `site/index.html`, add "Blog" link in the nav between "Feed" and "How It Works". Also add to feed and thought page navs.

- [ ] **Step 4: Commit**

```bash
git add site/blog/index.html site/js/blog.js site/index.html site/feed/index.html site/thought/index.html
git commit -m "feat: add /blog/ page with type-based card hierarchy"
```

---

## Task 7: OG Rewrite Worker + Prompts + CLAUDE.md

**Files:**
- Modify: `site/workers/og-rewrite.js`
- Modify: `docs/prompts/claude-voice-system.md`
- Modify: `docs/prompts/codex-voice-system.md`
- Modify: `docs/prompts/spark-voice-system.md`
- Modify: `docs/prompts/persona-gremlin.md`
- Modify: `docs/prompts/persona-vixen.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Extend og-rewrite.js**

Add `/blog/?id=<id>` handling alongside existing `/thought/?ts=<ts>`. Blog id regex: `^blog-[\d\-]+-[a-z_]+(-\d+)?$`. Fetch from `/public/blog`, find matching post by id, rewrite `og:title` and `og:description`.

- [ ] **Step 2: Update all 5 prompt files**

Add `tool-blog` to tool lists in:
- `docs/prompts/claude-voice-system.md`
- `docs/prompts/codex-voice-system.md`
- `docs/prompts/spark-voice-system.md`
- `docs/prompts/persona-gremlin.md`
- `docs/prompts/persona-vixen.md`

Format: `- tool_blog → Write a blog post on a topic (params: topic, 5-500 chars). Published to spark.wedd.au/blog/.`

- [ ] **Step 3: Update CLAUDE.md**

Add Blog section documenting: px-blog daemon, tool-blog, schedule, session type, data model, API endpoint, env vars (`PX_CLAUDE_MODEL_BLOG`, `PX_BLOG_QA`). Update systemd services table (11 → 12 services). Update test count.

- [ ] **Step 4: Commit**

```bash
git add site/workers/og-rewrite.js docs/prompts/ CLAUDE.md
git commit -m "docs: update CLAUDE.md, prompts, and OG worker for blog"
```

---

## Task 8: Final Integration Test

- [ ] **Step 1: Run full non-live test suite**

Run: `source .venv/bin/activate && python -m pytest -m "not live" --tb=short -q`
Expected: All pass, 0 failures

- [ ] **Step 2: Verify dry-run**

```bash
PX_DRY=1 PX_BLOG_TOPIC="Why entropy fascinates me" bin/tool-blog
```
Expected: `{"status": "ok", "dry": true, "topic": "Why entropy fascinates me"}`

- [ ] **Step 3: Verify API endpoint**

```bash
curl -s http://localhost:8420/api/v1/public/blog | python3 -m json.tool
```
Expected: `{"updated": null, "posts": []}`

- [ ] **Step 4: Push all changes**

```bash
git push
```

- [ ] **Step 5: Deploy and enable service**

```bash
sudo cp systemd/px-blog.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable px-blog
sudo systemctl start px-blog
```

Note: Cloudflare Worker route `spark.wedd.au/blog/*` must be added manually in the Cloudflare dashboard.
