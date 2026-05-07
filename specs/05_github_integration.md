# 05 — GitHub Integration

GitHub is the only data source. Getting this layer right is the whole game.

## API choice: REST + GraphQL

We use both, deliberately:

- **REST** for: list repos, list PRs/issues, releases, traffic, contributors. Simple, well-cached, ETag-friendly.
- **GraphQL** for: review state on PRs, mention detection, batched fetches. One round trip beats N.

Rule of thumb: if a screen needs >3 REST calls to populate, write a GraphQL query instead.

## Auth: PAT (v0.1), OAuth (v0.2)

### v0.1 — Personal Access Token
- User generates a fine-grained PAT in GitHub settings
- Required scopes: `repo` (full), `read:org`, `read:user`, `read:packages` (for releases)
- Pasted into Settings page → encrypted → stored in `users.pat_encrypted`
- Validated via `GET /user` on save; show login + scopes back to user

**Why PAT first:** zero OAuth app registration. User can clone, run, paste PAT, done. Lowest possible friction for a self-hosted tool.

### v0.2 — GitHub OAuth App
- Register a public OAuth app per RepoLens deployment (instance-owned, not centralized)
- Standard authorization code flow
- Scopes same as PAT, but user-friendly consent screen

## Repo visibility filter

RepoLens *syncs* every repo the user's PAT can see; *display* is filtered separately. This split matters.

### What gets synced

`GET /user/repos?affiliation=owner,collaborator,organization_member&per_page=100`

No `visibility` query param. The PAT's scope is the only gate — if the user
gave a public-only token, GitHub returns only public repos. If they gave
a `repo` token, both public and private come back. Each row gets a
`visibility` column (`public` | `private`) populated from the response.

### What gets displayed

Two filters apply at query time on every page:

```sql
WHERE
    repos.tracked = true
AND (NOT :public_only_mode OR repos.visibility = 'public')
```

- `tracked` — per-repo toggle, defaults true on first import
- `public_only_mode` — global Settings toggle, defaults false

Both are stored in `users` (single-user mode). Toggling either is a
no-sync operation; UI re-queries and the change is immediate.

### Implications for downstream pages

- **Inbox / Triage / Releases / Digest** — every list query joins to `repos`
  and applies the same filter. No page can leak a private repo when
  public-only mode is on.
- **Repos wall** — same filter; cards for private repos disappear cleanly
  when toggled.
- **Digest input** — the collector excludes private repos when public-only
  mode is on, so the AI never sees private repo names or stats in
  public-only mode.

### Why not just not-sync private repos when public-only is on?

- Toggling would require a full re-sync (slow, wastes API quota)
- Users frequently want public-only as a *temporary* mode (recording a demo,
  pairing with someone over screen-share). Re-sync friction kills that flow.
- A delete + re-add would lose history (e.g., star deltas, traffic accumulation)

The cost is local: private repo metadata sits in the user's own Postgres.
Acceptable for a self-hosted, single-user app.

## Sync strategy

### Frequency
| Job | Cadence | Why |
|---|---|---|
| Repo list refresh | 4 h | Repos rarely added/removed |
| PR/issue full sync | 30 min | Default; user-configurable |
| Traffic/clones | 24 h | GitHub only updates daily |
| Stars history | 24 h | We snapshot; deltas computed locally |
| Contributors | 24 h | Slow-changing |
| Releases | 30 min | Releases bursty around shipping |

### Incremental, not full
- Use `since` param on PRs/issues: `GET /repos/{r}/issues?since={last_synced_at}`
- Send `If-None-Match` header with stored ETag → 304 = no work, no quota burned
- Only the *changed* objects come back; we upsert on `(repo_id, number)`

### Pagination
- Default page size 100 (max GitHub allows)
- Follow `Link: rel="next"` header until exhausted
- For large-history initial sync, cap at 90 days back; offer "load full history" toggle in settings

### Concurrency
- Sync repos in parallel, max 4 at once (`asyncio.Semaphore(4)`)
- Within a repo, fan out PRs / issues / releases in parallel
- Bounded — never aim to drain rate-limit quota in a sprint

## Rate limit handling

GitHub gives 5,000 req/hr authenticated. With 30 repos × 30-min sync × ~5 calls/repo (with ETag 304s on most), we use ~600 req/hr. Comfortable.

### Defenses
1. **Read every response's `X-RateLimit-Remaining`.** Persist to `sync_runs.rate_limit_remaining`.
2. **Soft-pause at 100 remaining.** Drop to slow mode (1 call / 5s). UI banner: *"GitHub rate limit low. Slowing sync."*
3. **Hard-pause at 20.** Stop sync, show warning, schedule resume after `X-RateLimit-Reset`.
4. **Secondary rate limits (abuse detection):** exponential backoff on 403 with `Retry-After`. Honor the header to the second.
5. **Conditional requests are mandatory.** Any GET that supports ETag must use it. (Code review checklist item.)

## Key endpoints (v0.1)

| Purpose | Endpoint |
|---|---|
| Authenticated user | `GET /user` |
| User's repos | `GET /user/repos?affiliation=owner,collaborator,organization_member&per_page=100` |
| Repo PRs | `GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc` |
| Repo issues | `GET /repos/{owner}/{repo}/issues?state=all&sort=updated&since={iso}` |
| Releases | `GET /repos/{owner}/{repo}/releases?per_page=20` |
| Traffic views | `GET /repos/{owner}/{repo}/traffic/views` |
| Traffic clones | `GET /repos/{owner}/{repo}/traffic/clones` |
| Contributors | `GET /repos/{owner}/{repo}/stats/contributors` (cache; 202 first hit) |
| Stargazers (paginated) | `GET /repos/{owner}/{repo}/stargazers` (only on demand) |

### One GraphQL query per repo (PR detail)
```graphql
query RepoPrs($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 50, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { endCursor hasNextPage }
      nodes {
        number title state isDraft updatedAt mergedAt
        reviewDecision
        reviewRequests(first: 10) { nodes { requestedReviewer { ... on User { login } } } }
        comments { totalCount }
        author { login avatarUrl }
        labels(first: 20) { nodes { name } }
      }
    }
  }
}
```

This single query replaces ~5 REST calls per PR for the detail we need.

## Mention detection

A "mention" = a comment body containing `@{user.github_login}` on an issue/PR in a tracked repo, where the comment author is not the user themselves.

Approach for v0.1: fetch issue/PR comments via `GET /repos/{r}/issues/comments?since=...` (cross-repo endpoint exists for issue comments), substring-match `@{login}`. Cheap, good-enough.

v0.2: switch to GitHub's notifications API (`/notifications`) which surfaces mentions natively, with `reason=mention`.

## Webhook option (v0.3, not v0.1)

Webhooks would let us update in real time and skip the polling waste. But:
- They require a publicly reachable URL — hostile to self-host on a homelab
- They require an OAuth app or org admin
- They're an operational headache (signature verification, replay handling)

So v0.1 is poll-only. v0.3 adds webhooks as an opt-in optimization for users who already have a public HTTPS URL.

## Failure modes & UX

| Failure | What happens |
|---|---|
| Bad PAT | Settings shows red banner, sync paused, user re-enters PAT |
| 401 mid-sync | Same as bad PAT |
| 403 secondary rate limit | Backoff with Retry-After; UI shows "GitHub asked us to slow down" banner |
| 5xx from GitHub | Retry 3× with jitter, then mark this sync run failed; next run retries fresh |
| Repo deleted/transferred | Mark `archived_at`; stop syncing; flag in UI for user to remove from tracked list |
| Private repo, PAT lost access | Same as deleted from our view; UI distinguishes the cause |

## Testing strategy

- Record cassettes (vcrpy or recorded JSON fixtures) of real GitHub responses — 5 representative repos
- Replay against the sync pipeline in tests; assert DB state
- Contract tests against a real GitHub repo we own (a tiny fixture repo) in nightly CI
- No mocking the HTTP client at the unit level beyond the fixtures — tests should exercise real parsing
