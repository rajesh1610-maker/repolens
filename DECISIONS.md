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
