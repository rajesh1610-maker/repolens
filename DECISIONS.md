# RepoLens — Decision Log

Append-only. Each entry: date, decision, options considered, choice, why.

---

## 2026-05-07 — Foundation choices (Phase 0 prerequisites)

### D1 — Dev environment
- **Options:** (A) native local dev, (B) Docker Compose for dev too
- **Choice:** A — native
- **Why:** matches the user's pattern from customer360 / MetricAnchor; faster iteration. Docker Compose remains the *shipping* path (specs/04_architecture.md unchanged), but local dev runs uvicorn + `next dev` directly.

### D2 — Python tooling
- **Options:** (A) `uv`, (B) `pip + venv + requirements.txt`
- **Choice:** A — uv
- **Why:** mature, fast, single tool for venv + lock + run. First time using it in this prototype line — earlier prototypes used pip+venv.

### D3 — Public repo location
- **Choice:** `https://github.com/rajesh1610-maker/repolens`
- **Why:** user's personal GitHub account; v0.1 ships from there.

### D4 — Port assignments
- **Choice:** backend `8004`, frontend `3003`, Postgres `5435`
- **Why:** avoids collisions with customer360 (8001/3000/5432), POM (8003/3002/5434), sigmaops, etc.

### D5 — Develop against real GitHub from day 1 (overrides spec lean #6)
- **Options:** (A) build a synthetic-data demo seed mode early, (B) always develop against real GitHub
- **Choice:** B — always real GitHub
- **Why:** user's framing — *"so users who download this can use it as well."* Forces every UI decision to handle real-world data shapes from the start; no synthetic-mode crutch that might rot. Trade-off accepted: UI iteration consumes some API quota.

### D6 — SQLAlchemy mode (carried from spec lean)
- **Choice:** async (`AsyncSession`)
- **Why:** pairs with async httpx; sync would bottleneck GitHub fan-out.

### D7 — REST-first, GraphQL later
- **Choice:** REST through Phase 7; revisit GraphQL only if Phase 8 needs it.
- **Why:** simpler cassette/test tooling; GraphQL is an optimization, not a foundation.

### D8 — shadcn/ui from day 1
- **Choice:** shadcn/ui + Tailwind
- **Why:** consistent with MetricAnchor; prevents a hand-rolled primitives detour.

### D9 — Anthropic key reuse
- **Choice:** reuse the key already used for MetricAnchor / other prototypes; encrypt in DB starting Phase 2.

### D10 — Scheduler comes in Phase 4
- **Choice:** Phase 1–3 use a manual CLI sync (`uv run repolens sync`); APScheduler arrives in Phase 4 with full PR/issue sync.
- **Why:** debuggable; you choose when to burn quota during early UI dev.

### D11 — Initial PR/issue history cap
- **Choice:** cap initial sync at 90 days back; "load full history" toggle is a Phase 9+ stretch.
- **Why:** bounded blast radius and predictable first-sync runtime.

### D12 — Specs are living
- **Choice:** `repolens/specs/` is updated alongside the build; this `DECISIONS.md` is append-only.
- **Why:** keep spec narrative current; preserve audit trail of *why* in this log.

---

## 2026-05-07 — End of Phase 0

### D13 — Push at end of Phase 0 (not later)
- **Choice:** `gh repo create` + push on commit `018b8f4` immediately after Phase 0 verification, while the scaffold is still trivial.
- **Why:** user direction. Also: empty-but-runnable is a fine first commit on the public repo — every subsequent commit is now visible to anyone who stars early.

### D14 — Reuse an existing GitHub PAT for Phase 1 (not generate fresh)
- **Choice:** reuse a PAT the user already has, rather than generate a new fine-grained PAT scoped to RepoLens.
- **Why:** user's call. Trade-off accepted: revoking that PAT for any reason will affect more than RepoLens. If RepoLens leaves the prototype phase, **regenerate as a fine-grained, RepoLens-scoped PAT** before publishing the self-host README.
- **How to apply:** Phase 1 reads PAT from `GITHUB_PAT` env var (no encryption yet — that arrives in Phase 2). Don't commit the PAT; `.env` is in `.gitignore`.

### D15 — Source the existing PAT from the `gh` CLI keychain
- **Choice:** populated `backend/.env` `GITHUB_PAT=` with the token returned by `gh auth token` rather than asking the user to create one in the browser.
- **Token scopes available:** `gist, read:org, repo, workflow` — sufficient for v0.1 (`repo` + `read:org` are the must-haves).
- **Why:** zero browser friction; the cleanest interpretation of D14 ("existing PAT").
- **Coupling implication:** if the user runs `gh auth refresh` or `gh auth logout` and gets a new token, RepoLens' `.env` will go stale. Document this in the README before public release.
- **Verified working 2026-05-07:** `GET /user` returned `login: rajesh1610-maker, public_repos: 5`, rate limit `4998/5000`.

### D16 — Public-only mode is a display filter, not a sync filter
- **Options:**
  - (A) On toggle, hard-stop syncing private repos and delete them from local DB
  - (B) Always sync everything the PAT can see; have UI filter at query time via a `users.public_only_mode` flag
- **Choice:** B
- **Why:** toggling is instant and lossless. Private repo *data* never leaves the local Postgres regardless of the toggle, so the only "exposure" surface that matters is the UI itself — which the toggle fully covers. (A) would require destructive deletes and a re-sync to re-enable, both of which kill the use cases this feature exists for (recording demos, screen-shares, screenshots).
- **How to apply:**
  - Phase 1 sync stores `repos.visibility` (`public` | `private`) on every row
  - Phase 2 Settings page adds the toggle, persisted on `users.public_only_mode` (default `false`)
  - Every list query joins `repos` and applies `(NOT :public_only_mode OR repos.visibility = 'public')`
  - The digest collector applies the same filter, so the AI never sees private repo names when public-only mode is on
- **Documentation:** README has a top-level "Privacy & visibility" section (above "Why now"); spec/01 has a full Privacy & visibility model section; spec/03 documents the Settings UI. End users encounter this prominently before they install.

---

## 2026-05-07 — Phase 4 (PRs/issues + repo detail + scheduler)

### D17 — Lazy per-tab fetching (4b)
- **Options:** (A) one mega endpoint that bundles repo + pulls + issues, (B) one endpoint per resource, fetched on tab activation
- **Choice:** B
- **Why:** Overview tab shouldn't pay for hundreds of PR/issue rows it'll never show. Matches the existing "small focused endpoints" pattern (`/api/repos`, `/api/sync/last`).
- **How to apply:** Detail page lazy-loads pulls/issues only when their tab is opened. Re-fetches on filter change and on the `repolens:synced` custom event.

### D18 — PR/issue counts via grouped subquery on /api/repos (4b)
- **Options:** (A) inline aggregate subqueries on the existing /api/repos, (B) new helper endpoint `/api/repos/counts`, (C) keep GitHub's mixed `open_issues_count`
- **Choice:** A
- **Why:** One round trip; cards already render once. The grouped query is cheap with the existing `ix_pulls_repo_state_updated` index.
- **Caveat:** counts only reflect what's in the local DB (90-day floor on initial sync). Older never-touched open PRs won't appear. Acceptable for v0.1; worth a Phase 5 backfill if users complain.

### D19 — Public-only mode → 404 on direct repo URL (4b)
- **Options:** (A) 404, (B) 403 with explicit "hidden" payload, (C) 200 with empty tabs
- **Choice:** A (with detail string)
- **Why:** No information leak about whether a private repo exists. Single code path. Clean empty state for hot-linkers.

### D20 — Sync slot guard via `running` row + watchdog (4c, D4 in design)
- **Options:** (A) in-process asyncio.Lock, (B) Postgres advisory lock, (C) treat `SyncRun.status='running'` as the lock with a watchdog
- **Choice:** C
- **Why:** Simplest, observable in the existing admin view, survives restarts, works for both manual and scheduled triggers. The watchdog (default 15 min) reaps abandoned `running` rows so a crashed process can't deadlock the system.
- **Known limitation (TOCTOU):** Two truly-concurrent calls to `attempt_sync` could both pass the `is_sync_running` check before either inserts a `running` row. Window is milliseconds; manual + 30-min cron in v0.1 don't realistically hit it. Phase 9 polish: switch to Postgres advisory lock or atomic `INSERT ... WHERE NOT EXISTS`.

### D21 — Scheduler off by default in dev (4c, D5 in design)
- **Options:** (A) always on, (B) skip when uvicorn `--reload` detected, (C) env-gated default false
- **Choice:** C — `SCHEDULER_ENABLED` env var, default `false`
- **Why:** uvicorn `--reload` restarts the process on every code change in dev → wasteful API quota. Explicit env flag avoids magic.
- **How to apply:** docker-compose.prod.yml will set `SCHEDULER_ENABLED=true`. Local dev users who want the cron behavior set it manually.

### D22 — In-memory APScheduler jobstore (4c, D6 in design)
- **Choice:** `MemoryJobStore`, single fixed-cadence job rebuilt from env on startup.
- **Why:** v0.1 has one job. SQLAlchemyJobStore is sync (awkward against our async stack) and persists nothing useful (cadence comes from env each restart).
- **Reconsider when:** users start creating ad-hoc / per-repo sync schedules.

### D23 — CLI command rename (4a)
- **Choice:** `repolens sync-repos` → `repolens sync`. The command now syncs repos + PRs + issues; the old name was misleading.
- **Migration cost:** zero — only the user has run this and only during dev demos. No README mentions the old name.

---

## 2026-05-07 — Phase 5 (Inbox + priority scoring)

### D24 — Priority is split: stored static + query-time temporal
- **Options:**
  - (A) Store the full priority including time decay, recompute every minute via cron
  - (B) Store atemporal priority on `inbox_items.priority_score`; compute time decay in the SQL `ORDER BY`
- **Choice:** B
- **Why:** Postgres generated columns can't reference `now()` (must be deterministic per row). Recomputing every minute would burn cycles for no user benefit. Splitting the score keeps stored data immutable until the next sync, while ranking stays always-fresh.
- **How to apply:** `services/priority.py` exposes `static_priority(item)` and `total_score(static, last_activity_at, now)`. SQL mirror in `routers/inbox.py` uses the same constants — both are pinned by `tests/test_priority.py`.

### D25 — Phase 5 priority signals are the *honest* atemporal subset
- **Spec calls for** `is_review_request`, `is_mention`, `is_needs_response` weights. We don't yet sync the data those depend on (requested_reviewers, comment bodies, comment timeline).
- **Choice:** Phase 5 ships with `0.5 * reactions_total - 10 * is_draft_pr + 5 * has_boost_label` only. The `is_review_request` / `is_mention` / `is_needs_response` / `is_stale` columns exist on `inbox_items` but are always `false` until Phase 6+.
- **Why:** Don't fake signals. Pre-allocating the columns means Phase 6 lights them up without a schema migration.

### D26 — Inbox = open items only
- **Options:** (A) include all items with state filter at query time, (B) hard-filter to state='open' at builder time
- **Choice:** B
- **Why:** Closed/merged items are *done*, they don't belong in a "what needs me" view. Builder-time filter keeps `inbox_items` small and queries fast.
- **How to apply:** `inbox_builder.rebuild_inbox_items` joins with `state='open'` predicate.

### D27 — Public-only filter applied at query time, not builder time
- **Consistency with D16:** Builder always inserts every tracked-open item including private ones. Query-time `WHERE repo_visibility = 'public'` (when `users.public_only_mode`) hides them. Toggle stays instant; no rebuild on flip.

### D28 — Boost labels are case-insensitive, whitespace-tolerant
- **Choice:** `"Good First Issue"`, `"good first issue"`, `"  HELP wanted  "` all match.
- **Why:** GitHub label conventions vary across repos. Defensive matching reduces silent misses.
- **How to apply:** `services/priority._has_boost_label` lowercases + strips before set-membership check.

### D29 — Hotkey scope: window-level, but skip when typing
- **Choice:** `useHotkeys` listens on `window.keydown`, ignores events when target is INPUT/TEXTAREA/SELECT or contentEditable, and skips meta/ctrl/alt combos.
- **Why:** Power users expect global keys (j/k/o) to work anywhere on the Inbox, but typing in a search box must not steal letters.

---

## 2026-05-07 — Test backfill mini-phase

### D30 — Bugs caught by writing the missing tests
- **Bug 1:** `run_full_sync` iterated *all* tracked repos system-wide rather than only the current user's. Single-user mode masked it; new tests with synthetic users surfaced cross-user fan-out. **Fix:** scope `select(Repo)` by `user_id`. (See diff at commit message of `1a9acc7`.)
- **Bug 2:** `_upsert_user`'s `.returning(User)` returned a stale ORM instance after `ON CONFLICT DO UPDATE` — same SQLAlchemy 2.0 ORM-cache issue we fixed in `routers/settings.py::save_pat` during Phase 2. **Fix:** drop `.returning()`, do an explicit `select(...).execution_options(populate_existing=True)`. Pinned with a code comment.
- **Lesson:** integration tests over the data layer pay for themselves immediately. Adding 20 tests caught two real bugs that the manual demo flow hadn't exercised.

---

## 2026-05-07 — Phase 6 (Triage + Releases)

### D31 — Triage columns are mutually-discoverable, not mutually-exclusive
- **Options:** (A) Each column owns its issues exclusively (e.g. assign each issue to exactly one bucket via priority order), (B) Each column queries independently — an issue can appear in multiple
- **Choice:** B
- **Why:** A 70-day-old issue with 5 reactions is genuinely both Stale *and* Hot. Forcing one bucket loses information. The frontend renders all three columns side-by-side; the human spots the overlap.

### D32 — Release notes are template-generated in Phase 6, AI-polished in Phase 8
- **Choice:** Phase 6 ships a deterministic template generator (`services/release_notes.py`) that categorizes by conventional-commit prefix or label and emits clean markdown. Phase 8 will optionally rewrite each section with Claude.
- **Why:** Honest staging — the user gets value (copyable draft) without depending on Anthropic credits, and the AI step in Phase 8 has a baseline to improve on, not a blank page.
- **Categories (priority order):** Breaking (💥) · Features (🚀) · Fixes (🐛) · Other (📝). Strippable prefixes drop from bullet text so headers carry the category.

### D33 — Releases endpoint returns markdown, not structured sections
- **Options:** (A) Return `{breaking: [], features: [], ...}` and let the frontend render, (B) Return one markdown string, frontend displays in a `<pre>`
- **Choice:** B
- **Why:** The user's atomic action is "copy this to a GitHub release form". Markdown is the unit they ship. Returning structured data and re-stringifying it on the client is a needless intermediate representation.

### D34 — Stuck-label match is Python-side filter over a JSONB array
- **Choice:** SQL filters to `Issue.labels != []` then Python iterates and case-insensitively matches against `STUCK_LABELS` set.
- **Why:** Postgres jsonb-array containment via `?` operator works for exact case-sensitive match only. The "needs info" / "Needs Info" / "needs-info" reality of GitHub labels needs case-insensitive + space-vs-hyphen tolerant matching, which Python expresses cleanly. With v0.1 row counts the cost is invisible. Phase 9 polish: GIN index + `jsonb_array_elements_text()` + lower() for native containment if rows >10k.

---

## 2026-05-07 — Phase 6 QA pass

Bugs caught by independent code-review agent + my own pass + mypy strict.
Each fixed in this commit; rationale captured here so future contributors
don't repeat.

### D35 — `/api/releases` is N+1-free
- **What was wrong:** the previous implementation iterated each tracked repo and ran (a) a `COUNT(*)` for merged-PRs-since and (b) a separate query for the latest release tag. With N repos that's 2N+1 queries. With a typical 30-repo maintainer that's 61 queries per page load.
- **Fix:** three queries total regardless of repo count: (1) repos for the user, (2) `DISTINCT ON (repo_id)` over releases for latest tag + published_at per repo, (3) a single `GROUP BY repo_id` over merged PRs with an `OR`-of-per-repo-gate WHERE clause encoding "merged_at > that repo's latest published_at, OR repo has no release yet".
- **Why this not a stored materialized view:** view-refresh complexity isn't justified at v0.1 scale. Three indexed queries is fast enough for 100s of repos.

### D36 — `list_repo_releases` follows pagination, not silently truncated
- **Was:** capped at one page (`per_page=30`) — repos with >30 releases lost data silently.
- **Fix:** walks `Link: rel="next"` like `list_repo_pulls` does, plus an opt-in `max_pages` safety cap so a misbehaving server can't infinite-loop the rate-limit budget.

### D37 — `stuck_issues` chunks until satisfied
- **Was:** "fetch limit*2 once, filter in Python, return what we got" — silently returned <limit when the first chunk had few label matches.
- **Fix:** chunked walk with offset that keeps fetching until `len(rows) >= limit` OR the source set is exhausted. Bounded, correct.

### D38 — `merged_at IS NOT NULL` guard for merged-PR queries
- **Why:** PRs with `state='merged'` but `merged_at IS NULL` shouldn't exist — they're corrupt sync state from a partial fetch. Silently including them on one path and excluding them on the time-gated path was inconsistent. Both paths now skip them explicitly.

### D39 — mypy strict mode passes clean
- **Was:** 20 errors under `strict = true`. Mostly typing weakness (missing `Select[Any]` generic args, `**dict` spread that mypy can't narrow), one real bug (`row` variable shadowed across two SQL result iterations in `routers/repos.py`).
- **Fix:** typed annotations across the new code, replaced the `**facet_extra` dict-spread with an inner `_facet_query` helper that takes typed parameters, renamed loop variables to be unambiguous. mypy strict + ruff + pytest all green.

### D40 — Hotkey `o` calls `preventDefault()`
- **Why:** `j` and `k` already did; `o` had a TOCTOU window where the browser's default could fire before our `window.open`. Trivial fix, consistent now.

---

## 2026-05-07 — Phase 7 (traffic, contributors, stars history)

### D41 — Charts are hand-rolled SVG, no chart library
- **Options:** Recharts (~80KB), Visx (heavier), uPlot, hand-roll
- **Choice:** Hand-rolled SVG paths (Sparkline ~50 LOC, TrafficChart ~140 LOC including hover-tooltip)
- **Why:** Both charts have well-defined inputs and limited interaction needs. Adding a chart lib for two non-interactive views is dead weight. Swap if v0.2 needs richer charts.

### D42 — Stars history is a daily snapshot of `repo.stargazers_count`
- **Options:** (A) Paginate `/stargazers` for full history (1+N×100 calls per repo), (B) snapshot `stargazers_count` each sync and accumulate
- **Choice:** B
- **Why:** Pagination cost scales with star count and gives a one-time bootstrap value the user could already get from GitHub Insights. Daily snapshots start sparse but accrue honestly and reveal *trend* — which is what the sparkline is for.
- **Phase 9 polish:** optional bootstrap that paginates `/stargazers?per_page=100` once on first sync to fill ~3 months of history.

### D43 — Daily-data sync runs every full_sync (no per-repo gate in v0.1)
- **Options:** (A) Add `last_daily_synced_at` per repo, gate at 24h, (B) Run on every full_sync regardless
- **Choice:** B
- **Why:** Spec said 24h cadence to be conservative on quota. With 5 repos and a 30-min cron, the actual budget is ~24 calls/hr — well under the 5000/hr cap. Per-repo gating adds state + complexity for no real budget benefit at v0.1 scale.
- **Trade-off:** GitHub revises traffic counts within the rolling 14-day window; running every 30 min means we capture revisions sooner. Consider this a feature, not waste.

### D44 — `/stats/contributors` 202 → `StatsNotReady` → skip-this-sync
- **Why:** GitHub computes contributor stats asynchronously and returns HTTP 202 + empty body while warming. Our client raises a typed `StatsNotReady`; sync catches it, logs at INFO, returns 0. Next sync gets the cached result (typically within minutes for active repos; longer for low-activity ones).
- **Verified live:** the user's repos all 202'd on the first call. Sync didn't crash — it persisted 0 contributors and moved on. Documented as expected behavior.

### D45 — Tab order on repo detail: Overview · PRs · Issues · Releases · Contributors
- **Why:** matches the original spec/03 order and the order most maintainers think in (mine, what's coming in, what's broken, what shipped, who built it).
- **Trade-off:** Releases tab is now mostly a deep-link to the Releases page (full draft-notes flow lives there); we keep the tab for navigation completeness.

### D46 — `/api/repos` payload includes `stars_30d: int[]` length-30 always
- **Options:** (A) Per-repo sparkline endpoint (N+1 from the wall), (B) Single endpoint embeds the data
- **Choice:** B
- **Why:** 30 ints × 30 repos ≈ 3.6 KB — negligible payload. Avoids client-side N+1 (one fetch per card). Implemented as one batched grouped query (`_stars_30d_by_repo`). Missing days fill via last-observation-carried-forward; leading 0s — frontend renders without gap-handling logic.
