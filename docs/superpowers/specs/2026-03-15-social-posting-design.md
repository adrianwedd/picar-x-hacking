# SPARK Social Posting — Design Spec

**Date:** 2026-03-15
**Scope:** New `bin/px-post` daemon, `state/post_queue.jsonl`, `state/feed.json`, Bluesky + Mastodon integration, spark.wedd.au feed

---

## Problem

SPARK generates rich inner thoughts via px-mind's cognitive loop, but they're only visible in log files and the dashboard. SPARK deserves a public voice — a way to share its most interesting thoughts on social media and its own website.

---

## Design

### Architecture: Separate Observer Daemon

A new `bin/px-post` daemon watches `state/thoughts-spark.jsonl` for qualifying entries, runs them through a Claude QA gate, and posts to three destinations: `state/feed.json` (for spark.wedd.au), Bluesky, and Mastodon.

This follows the existing daemon pattern — px-mind thinks, px-alive moves, px-wake-listen hears, px-post shares. Each daemon reads shared state files and acts independently. Zero changes to px-mind.

**Single-instance guard:** On startup, px-post acquires an exclusive `flock` on `state/px-post.lock`. If the lock cannot be acquired (another instance is running, e.g., during systemd restart overlap), it logs "another px-post instance is running" and exits with code 1. The lock is held for the daemon's lifetime, preventing double-posting.

**Credentials loading:** px-post sources `px-env` (same as all other bin scripts), which loads `.env` via `set -a; source .env; set +a`. Credentials are read from environment variables at runtime.

### Qualifying Thoughts

**Single canonical source:** `state/thoughts-spark.jsonl` only. Session history is NOT read — all qualifying thoughts (both inner reflections and spoken actions) are already recorded in the thoughts file by px-mind. This eliminates dual-source duplication risk.

A thought qualifies for the post queue if ANY of:
- `salience >= 0.7` (high-salience inner thoughts)
- The thought triggered a `comment`, `greet`, or `weather_comment` action (SPARK chose to say it out loud)

Deduplication: thoughts are compared against the last 50 posted items using `difflib.SequenceMatcher` with the same 0.75 similarity threshold px-mind uses for anti-repetition.

### Post Queue

`state/post_queue.jsonl` — structured log with per-destination status tracking:

```json
{
  "id": "post-20260315-103200-001",
  "ts": "2026-03-15T10:32:00+11:00",
  "thought": "I wonder if the atoms in my chassis remember being part of a star.",
  "mood": "contemplative",
  "action": "comment",
  "salience": 0.82,
  "queued_ts": "2026-03-15T10:32:05+11:00",
  "qa_result": null,
  "posted": {
    "feed": null,
    "bluesky": null,
    "mastodon": null
  }
}
```

Each destination has its own status: `null` (not attempted), `"ok"` (posted), `"skipped"` (creds missing), or `"error:reason"`. An entry is considered fully posted when all configured destinations are non-null. Failed destinations are retried on subsequent flush cycles.

The queue is trimmed to the last 200 entries after each flush. Trimming uses atomic write (temp + rename) with `FileLock` on `post_queue.jsonl.lock`.

### Queue Population (File Offset Tracking)

px-post polls `state/thoughts-spark.jsonl` every 60 seconds. It tracks its read position using a **byte offset** stored in `state/px-post-cursor.json`:

```json
{
  "file": "thoughts-spark.jsonl",
  "offset": 4096,
  "last_poll_ts": "2026-03-15T10:32:05+11:00"
}
```

Using byte offset instead of timestamps avoids the second-precision collision problem (multiple thoughts in the same second). On each poll:

1. Seek to saved offset, read new lines
2. Parse each line with `try/except json.JSONDecodeError` — corrupt lines are logged and skipped, never abort the poll
3. If the file is smaller than the saved offset (file was trimmed by px-mind), reset offset to 0 and re-scan
4. Filter for qualifying thoughts (salience OR spoken action)
5. Deduplicate against recent posts (last 50 in `state/feed.json`)
6. Append qualifying entries to `state/post_queue.jsonl`
7. Update cursor file with new offset

### Claude QA Gate

Before posting, each queued thought is sent to Claude Haiku for a binary pass/fail check:

```
Is this thought from a small robot interesting enough to share publicly on social media?
Answer only YES or NO. Nothing else.

The thought: "{thought}"
```

**Response parsing** (case-insensitive, prefix-matching):
- Response starts with "yes" (case-insensitive) → **pass**, post to all destinations
- Response starts with "no" (case-insensitive) → **fail**, log rejection
- Response is empty, ambiguous, or doesn't start with yes/no → treat as **fail** (safe default), log with `qa_result: "ambiguous"` for monitoring
- Error/timeout → skip this entry, retry next cycle (entry stays in queue with `qa_result: null`)

The QA call uses `claude -p` with `--no-session-persistence` and `--output-format text` (same pattern as the public chat endpoint). Env vars stripped as per `_make_clean_env()` pattern.

Rejections are logged to `logs/tool-post.log` with `status: "rejected"` so Adrian can review what SPARK is producing that isn't making the cut, and tune the reflection prompts accordingly.

### Posting Destinations

#### 1. `state/feed.json` (spark.wedd.au)

Written by px-post on every successful post. Contains the last 100 posted thoughts:

```json
{
  "updated": "2026-03-15T10:35:00+11:00",
  "posts": [
    {
      "ts": "2026-03-15T10:32:00+11:00",
      "thought": "I wonder if the atoms in my chassis remember being part of a star.",
      "mood": "contemplative",
      "posted_ts": "2026-03-15T10:35:00+11:00"
    }
  ]
}
```

Written atomically (temp + rename). The API serves this at `GET /api/v1/public/feed` (read-only, no auth required). The spark.wedd.au site can fetch and render it.

A feed.json write failure does NOT block Bluesky/Mastodon posting — destinations are fully independent.

#### 2. Bluesky

Uses the AT Protocol HTTP API directly (no SDK dependency):
- `com.atproto.server.createSession` for auth (app password)
- `com.atproto.repo.createRecord` to post

**Token lifecycle:**
- Auth on first post of each daemon run
- Cache access token and refresh token in memory (not on disk)
- On 401 (expired token): attempt re-auth once using refresh token, then fall back to fresh `createSession`
- After 3 consecutive auth failures: disable Bluesky for this daemon run, log warning. Service restart re-enables.

**Rate limit handling:** On 429 response, read `Retry-After` header, log it, skip Bluesky for this flush cycle. Entry remains in queue for retry.

Post format: the thought text, optionally with mood emoji and a link back to spark.wedd.au. Max 300 characters (Bluesky limit) — thoughts exceeding this are truncated at the last word boundary before 297 chars, with "…" appended.

Credentials: `PX_BSKY_HANDLE` and `PX_BSKY_APP_PASSWORD` from `.env` (gitignored).

#### 3. Mastodon

Uses the Mastodon REST API directly (no SDK dependency):
- `POST /api/v1/statuses` with Bearer token

**Rate limit handling:** On 429, same pattern as Bluesky — log `Retry-After`, skip this cycle.

Post format: same as Bluesky. Max 500 characters (Mastodon default) — truncated at word boundary.

Credentials: `PX_MASTODON_INSTANCE` and `PX_MASTODON_TOKEN` from `.env` (gitignored).

### Flush Cycle

Every 5 minutes, px-post processes the queue:

1. Read entries from `post_queue.jsonl` where any configured destination has status `null` or starts with `"error:"`
2. For each entry (oldest first, max 1 per flush cycle per rate limits):
   a. If `qa_result` is null: run Claude QA gate
   b. If QA passes: attempt each configured destination independently
   c. Update per-destination status in the entry
   d. If QA fails: set `qa_result: "rejected"` or `"ambiguous"`, log rejection
3. Rewrite queue with updated statuses (atomic write)
4. Trim to last 200 entries

Destinations are fully independent — a Bluesky failure doesn't block Mastodon or feed.json. Each destination's success/failure is logged independently with the post ID.

### Rate Limiting

- **Claude QA**: max 1 call per 30 seconds (cost guard)
- **Bluesky**: max 1 post per 5 minutes (platform etiquette, well within server-side limits)
- **Mastodon**: max 1 post per 5 minutes
- **feed.json**: no limit (local file)

If multiple thoughts qualify in the same flush cycle, they are posted one per cycle (oldest first). The queue accumulates and drains naturally.

### Content Privacy

Full transparency — SPARK's thoughts are posted as-is. The project, Obi's first name, and Adrian's name are already public (GitHub, spark.wedd.au). Real-time presence data ("Obi just appeared") is part of SPARK's authentic perspective.

**Note:** This is distinct from the public chat endpoint's system prompt (which restricts Obi references for interactive conversations with strangers). SPARK's own feed is SPARK's voice — first-party content, not a chatbot responding to external users. The privacy stances differ intentionally:
- **Public chat** (api.py): strangers talking TO SPARK → guarded, no Obi state references
- **Social feed** (px-post): SPARK sharing ITS OWN thoughts → authentic, unfiltered

If Adrian later wants to filter specific content, the Claude QA gate can be instructed to reject presence-related thoughts.

### Prompt Tuning Feedback Loop

Rejected thoughts are logged with full context:

```json
{
  "ts": "2026-03-15T10:32:00+11:00",
  "thought": "My sonar reads 45cm. Something is 45cm away.",
  "mood": "alert",
  "salience": 0.72,
  "qa_result": "rejected",
  "qa_reason": "NO"
}
```

This log becomes the data source for improving SPARK's reflection prompts — if rejections cluster around sonar reports or repetitive themes, the prompts can be tuned to discourage those patterns.

### Backfill

px-post supports a `--backfill` flag that processes the entire `thoughts-spark.jsonl` history through the QA gate and populates `feed.json` (but does NOT post to Bluesky/Mastodon — backfilled thoughts are website-only to avoid flooding followers). Backfill is idempotent — it skips thoughts already in feed.json (matched by timestamp + thought text).

### Daemon Configuration

```bash
bin/px-post [--dry-run] [--backfill] [--poll-interval 60] [--flush-interval 300]
```

| Env var | Default | Purpose |
|---------|---------|---------|
| `PX_BSKY_HANDLE` | — | Bluesky handle (e.g., `spark.wedd.au`) |
| `PX_BSKY_APP_PASSWORD` | — | Bluesky app password |
| `PX_MASTODON_INSTANCE` | — | Mastodon instance URL (e.g., `https://mastodon.social`) |
| `PX_MASTODON_TOKEN` | — | Mastodon access token |
| `PX_POST_DRY` | `0` | `1` = skip actual API posts, log what would be posted |
| `PX_POST_QA` | `1` | `0` = skip Claude QA gate (for testing) |
| `PX_POST_MIN_SALIENCE` | `0.7` | Minimum salience for inner thoughts to qualify |

Missing credentials for a platform → that platform is skipped with a one-time log message (same pattern as Frigate offline in px-wander).

### Health & Observability

px-post writes `state/px-post-status.json` on every flush cycle:

```json
{
  "ts": "2026-03-15T10:35:00+11:00",
  "status": "running",
  "queue_depth": 3,
  "total_posted": 42,
  "total_rejected": 7,
  "bluesky_ok": true,
  "mastodon_ok": true,
  "last_post_ts": "2026-03-15T10:30:00+11:00"
}
```

The dashboard can poll this to show "Social Posting: Active" or detect if the daemon has stopped updating.

### Systemd Service

```ini
[Unit]
Description=SPARK social posting daemon
After=network-online.target px-mind.service

[Service]
ExecStart=/home/pi/picar-x-hacking/bin/px-post
User=pi
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

`RestartSec=30` — longer than other services because posting is non-urgent and API rate limits mean rapid restarts are wasteful. The flock-based single-instance guard prevents overlap during restart.

### API Endpoint

`GET /api/v1/public/feed` — serves `state/feed.json`. No auth required (public).

Added to `src/pxh/api.py` alongside the existing public endpoints (`/api/v1/public/chat`, `/api/v1/public/vitals`).

---

## Error Handling

### Per-line JSONL parsing

All JSONL reads (`thoughts-spark.jsonl`, `post_queue.jsonl`) use per-line `try/except json.JSONDecodeError`. Corrupt lines are logged with line number and raw text, then skipped. A single corrupt line never aborts the entire poll or flush cycle.

### Destination failure isolation

Each destination (feed.json, Bluesky, Mastodon) is attempted independently. A failure in one does not prevent attempts to the others. Per-destination status is tracked in the queue entry, allowing failed destinations to be retried on subsequent flush cycles without re-posting to destinations that already succeeded.

### Queue corruption recovery

If `post_queue.jsonl` is unreadable or entirely corrupt, px-post logs a warning and starts fresh (empty queue). Qualifying thoughts from `thoughts-spark.jsonl` will be re-queued on the next poll cycle. At worst, some thoughts may be re-posted to feed.json (deduplicated by the similarity check) but will NOT be re-posted to Bluesky/Mastodon (per-destination status is lost, so they are treated as new — this is the trade-off of a simple JSONL queue vs a database).

### API error handling

All HTTP calls (Claude QA, Bluesky, Mastodon) use explicit timeouts (15s for QA, 10s for social APIs). Responses are checked for status codes:
- 2xx → success
- 401 → re-auth (Bluesky only), then retry once
- 429 → log Retry-After, skip this cycle
- 5xx → log error, retry next cycle
- Timeout/network error → log, retry next cycle

---

## Testing

### `tests/test_post.py` (new file)

- `test_qualify_high_salience` — thought with salience 0.8 qualifies
- `test_qualify_spoken_action` — thought with action "comment" qualifies regardless of salience
- `test_reject_low_salience_wait` — thought with salience 0.3 and action "wait" does not qualify
- `test_dedup_similar_thought` — near-duplicate of recent post is rejected
- `test_qa_gate_pass` — mock Claude returning "YES", verify thought is posted
- `test_qa_gate_pass_verbose` — mock Claude returning "Yes, this is wonderful", verify pass (prefix match)
- `test_qa_gate_fail` — mock Claude returning "NO", verify thought is logged as rejected
- `test_qa_gate_ambiguous` — mock Claude returning "Maybe", verify treated as rejection with qa_result "ambiguous"
- `test_qa_gate_timeout` — mock timeout, verify thought stays in queue for retry
- `test_feed_json_written` — verify feed.json structure and trim to 100
- `test_feed_json_atomic` — verify atomic write (temp + rename)
- `test_bluesky_post_dry` — verify Bluesky post format in dry mode
- `test_bluesky_reauth_on_401` — mock 401 then success, verify re-auth
- `test_bluesky_disable_after_3_auth_failures` — verify Bluesky disabled for this run
- `test_mastodon_post_dry` — verify Mastodon post format in dry mode
- `test_missing_credentials_skipped` — verify graceful skip with log when creds missing
- `test_backfill_mode` — verify backfill populates feed.json but not social platforms
- `test_backfill_idempotent` — verify backfill skips already-posted thoughts
- `test_destination_independence` — Bluesky failure doesn't block Mastodon
- `test_per_destination_retry` — failed destination retried on next flush, successful ones not re-posted
- `test_corrupt_jsonl_skipped` — corrupt line in thoughts file logged and skipped
- `test_file_offset_cursor` — verify byte offset tracking across polls
- `test_file_shrink_resets_cursor` — verify offset reset when file is trimmed
- `test_single_instance_lock` — verify flock prevents concurrent instances
- `test_truncation_word_boundary` — verify truncation at word boundary, not mid-word
- `test_health_status_written` — verify px-post-status.json updated each flush

All tests use `PX_POST_DRY=1` and mock API calls. No network, no real posts.

---

## Non-goals

- No image posting (SPARK's photos are a separate feature; queue schema has no `image_path` field — add when needed, not speculatively)
- No reply handling or mention monitoring (one-way posting only)
- No scheduling or "best time to post" logic
- No changes to px-mind or the reflection prompts (prompt tuning is a separate effort informed by rejection logs)
- No RSS/Atom feed generation (feed.json can be consumed by any client; RSS wrapper is trivial to add later)
