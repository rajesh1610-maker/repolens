# 02 — Data Model

Postgres 15. All tables in schema `repolens`. UUIDv7 primary keys (sortable). Timestamps in UTC.

## Conventions

- `created_at`, `updated_at` on every table; `synced_at` where data is mirrored from GitHub
- GitHub IDs (numeric) stored alongside our UUIDs for upsert keys
- Soft-delete via `archived_at` rather than `DELETE` for repos/PRs/issues — keeps digests stable
- JSON columns (`raw`) hold the unparsed GitHub payload for forward-compat; queries use extracted columns

## Tables

### `users`
The maintainer using the app. v0.1 supports one row, but schema is multi-user-ready.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| github_id | bigint UNIQUE | |
| github_login | text | |
| email | text | |
| avatar_url | text | |
| pat_encrypted | bytea | GitHub PAT, AES-GCM, key from env |
| anthropic_key_encrypted | bytea | for digest generation |
| public_only_mode | bool | global UI filter; when true, private repos hidden from every page. Default false. |
| created_at | timestamptz | |

### `repos`
Every repo the user has chosen to track.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK users | |
| github_id | bigint UNIQUE | |
| owner | text | |
| name | text | |
| full_name | text | `owner/name` — denormalized for display |
| description | text | |
| visibility | text | public/private |
| default_branch | text | |
| stars | int | |
| forks | int | |
| open_issues_count | int | from GitHub (PRs + issues combined) |
| pushed_at | timestamptz | |
| tracked | bool | toggle from settings |
| archived_at | timestamptz NULL | |
| synced_at | timestamptz | |

Indexes: `(user_id, tracked)`, `full_name`.

### `pull_requests`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| repo_id | uuid FK | |
| github_id | bigint | |
| number | int | |
| title | text | |
| state | text | open/closed/merged |
| draft | bool | |
| author_login | text | |
| author_avatar_url | text | |
| created_at | timestamptz | from GitHub |
| updated_at | timestamptz | from GitHub |
| closed_at | timestamptz NULL | |
| merged_at | timestamptz NULL | |
| review_decision | text NULL | APPROVED / CHANGES_REQUESTED / REVIEW_REQUIRED |
| requested_reviewer_logins | text[] | |
| labels | text[] | |
| comments_count | int | |
| additions | int | |
| deletions | int | |
| raw | jsonb | full GitHub payload |
| synced_at | timestamptz | |

UNIQUE `(repo_id, number)`. Indexes on `(repo_id, state, updated_at desc)`. Labels stored as JSONB (not Postgres ARRAY).

> **Phase 4a built columns:** `id`, `repo_id`, `github_id`, `number`, `title`, `state`, `draft`, `author_login`, `author_avatar_url`, `labels`, `created_at`, `updated_at`, `closed_at`, `merged_at`, `raw`, `synced_at`.
> **Deferred (need extra REST or GraphQL calls):** `review_decision`, `requested_reviewer_logins`, `comments_count`, `additions`, `deletions`. These land in Phase 5+ as priority scoring needs them.

### `issues`
Same shape as `pull_requests` minus PR-specific fields, plus:

| Column | Type | Notes |
|---|---|---|
| reactions_total | int | sum of +1, -1, heart, etc. — fuel for triage ranking |
| is_pull_request | bool | always false here; GitHub mixes them in their API, we split |

Indexes on `(state, reactions_total desc)`, `(repo_id, updated_at desc)`.

### `releases`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| repo_id | uuid FK | |
| github_id | bigint | |
| tag_name | text | |
| name | text | |
| published_at | timestamptz | |
| draft | bool | |
| prerelease | bool | |
| body_md | text | |

### `traffic_daily`
| Column | Type | Notes |
|---|---|---|
| repo_id | uuid FK | |
| day | date | |
| views | int | |
| unique_views | int | |
| clones | int | |
| unique_clones | int | |

PK `(repo_id, day)`. GitHub returns 14 days at a time — we accumulate.

### `stars_daily`
| Column | Type | Notes |
|---|---|---|
| repo_id | uuid FK | |
| day | date | |
| stars_total | int | snapshot |
| stars_delta | int | computed vs prior day |

PK `(repo_id, day)`.

### `contributors`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| repo_id | uuid FK | |
| github_login | text | |
| avatar_url | text | |
| commits_total | int | last 90d |
| last_commit_at | timestamptz | |

UNIQUE `(repo_id, github_login)`.

### `inbox_items` (derived)
Materialized rollup that powers the Inbox page. Rebuilt at end of each sync.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK | |
| repo_id | uuid FK | |
| kind | text | pr / issue / mention / review_request |
| source_id | uuid | FK to PR or issue |
| title | text | |
| url | text | github.com link |
| priority_score | numeric(6,2) | 0–100, see scoring below |
| is_needs_response | bool | |
| is_mention | bool | |
| is_review_request | bool | |
| is_stale | bool | |
| last_activity_at | timestamptz | |

Indexes: `(user_id, priority_score desc)`, `(user_id, kind, last_activity_at desc)`.

### `digests`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK | |
| period_start | date | |
| period_end | date | |
| body_md | text | the generated narrative |
| input_summary | jsonb | what we fed Claude (for repro/debug) |
| model | text | e.g. `claude-opus-4-7` |
| tokens_in | int | |
| tokens_out | int | |
| cost_usd | numeric(10,4) | |
| generated_at | timestamptz | |

### `sync_runs`
Operational table — what synced, when, how long, errors.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| started_at | timestamptz | |
| finished_at | timestamptz NULL | |
| repos_synced | int | |
| api_calls | int | |
| rate_limit_remaining | int | |
| status | text | running / ok / failed |
| error | text NULL | |

## Priority score (inbox ranking)

```
priority_score =
    50 * is_review_request
  + 40 * is_mention
  + 25 * is_needs_response
  + 0.5 * reactions_total           -- popular issues bubble up
  - 5  * days_since_last_activity   -- recent things matter more
  - 10 * is_draft_pr                -- drafts deprioritize
  + 15 * is_blocking_release        -- merged into milestone tagged 'next'
```

Clamp to [0, 100]. The exact weights are placeholders — we'll tune from real usage. The point is the scoring is *transparent and editable* in code, not a black box.

`is_needs_response` heuristic: PR/issue updated by someone other than the maintainer in the last update, AND the maintainer hasn't commented since.

## Why this shape

- **Mirror, don't proxy.** We pull GitHub data into Postgres so the UI is fast and works offline. GitHub is the source of truth; we're a cache + lens.
- **Derived tables are explicit.** `inbox_items` is rebuilt — it's not an opaque view. Easy to inspect, easy to debug.
- **`raw` jsonb everywhere** so we can backfill new extracted columns without re-syncing GitHub from scratch.
