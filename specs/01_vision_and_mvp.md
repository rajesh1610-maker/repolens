# 01 — Vision & MVP Scope

## Vision

**RepoLens is the cockpit a solo OSS maintainer wishes GitHub had.**

GitHub's UI is repo-first: every screen forces you to pick a repo, then drill in. But maintainers don't think repo-first — they think *"what needs me today, across everything I own?"* RepoLens flips that axis: maintainer-first, repo-as-attribute.

## Target user

The **solo / small-team OSS maintainer** with 5–30 active repos. Patterns:
- Mix of dormant and busy repos; can't tell at a glance which is which
- Drowns in GitHub email; can't separate noise from "actual response needed"
- Sometimes goes weeks without checking issues on a long-tail repo
- Wants release hygiene but ships ad-hoc because changelog work is a chore
- Cares about community health (stars/traffic) but only checks insights once a quarter

**Not the target (yet):**
- Large org maintainers with dedicated triage tooling
- Bot-driven workflows (Renovate, Dependabot, Probot) — RepoLens *displays* their output, doesn't replace them

## Value proposition

> Spend 10 minutes a day in RepoLens instead of 45 minutes scattered across GitHub tabs.

Three concrete promises:
1. **One inbox.** Every actionable thing across every repo, ranked.
2. **One pulse.** Star/traffic/issue/release health for every repo on one screen.
3. **One narrative.** A weekly AI digest that summarizes the week and tells you what to do Monday morning.

## Why people will star this

- Ships as a self-hostable Docker Compose app (no SaaS lock-in)
- Solves a real pain that GitHub itself isn't solving (because it would cannibalize their own surfaces)
- Lives *on top of* GitHub — every screenshot of RepoLens is implicitly an ad for itself among GitHub power users
- Hooks into a category (developer dashboards) that consistently produces breakout OSS hits

## MVP scope (v0.1)

**Goal:** dogfood-able by one person (the user) on their own GitHub repos within 2 weekends of build time.

### In scope for v0.1

| Area | What ships |
|---|---|
| **Auth** | GitHub OAuth, single-user mode. PAT stored encrypted at rest. |
| **Repo sync** | Pull list of all repos owned by the user (and orgs they admin). User picks which to track. |
| **Data sync** | Background job pulls PRs, issues, releases, traffic, stars every 30 min. Incremental via `since` param + ETags. |
| **Inbox page** | Unified list of PRs + issues across tracked repos. Filters: needs-response, mentions, stale, by-repo. |
| **Repo wall** | Grid card per repo: stars (+delta 7d), open PRs, open issues, last release, last commit. |
| **Repo detail** | One repo's PR list, issue list, recent releases, traffic chart, contributor list. |
| **Triage queue** | Issues ranked by staleness × reactions × "needs response" heuristic. |
| **Weekly digest** | AI-generated markdown summary, generated Sunday night, viewable + downloadable. |
| **Settings** | PAT entry, tracked repos toggle, digest schedule, Anthropic API key. |

### Explicitly out of scope for v0.1

- Multi-user / team mode
- Writing back to GitHub (commenting, closing, merging) — read-only first
- Slack/Discord/email notifications — you check the app
- Mobile-native — responsive web only
- GitLab/Bitbucket — GitHub only
- Self-hosted runners, Actions monitoring — out
- Custom rules / webhooks — out

## Success criteria for v0.1

A maintainer with 10 repos can:
1. Auth in under 60 seconds
2. See all 10 repos on the wall with live data within 5 minutes of first sync
3. Find every PR that needs their review without opening github.com
4. Read a weekly digest that they'd actually forward to a co-maintainer

If any of those fails, the MVP isn't done.

## Non-goals (the "no" list — important)

- **Don't be GitHub.** No issue editor, no PR review UI. Click-through to github.com is a feature, not a regression.
- **Don't replace bots.** Surface Dependabot output, don't compete with it.
- **Don't build a notification engine in v0.1.** The web UI is the notification.
- **Don't gate features behind accounts/billing.** This is OSS; self-hosted; the AI digest needs a user-supplied API key.

## Privacy & visibility model

A first-class concern, not a footnote. RepoLens is read-only against GitHub
and runs entirely on the user's own machine — but several common situations
need explicit handling.

### Three layers of control

1. **The token's scope.** RepoLens cannot see what the user's PAT cannot
   see. A `public_repo`-only token will never expose private data; a `repo`
   token will. Document scope choice prominently in the README and the
   first-run wizard.
2. **Per-repo tracking** (always available). Each visible repo has a
   `tracked` flag in `repos`. Untracking a repo excludes it from sync, UI,
   priority scoring, and the digest immediately.
3. **Public-only mode** (global toggle). A single Settings toggle that
   hides all private repos from every page. Implemented as a *display*
   filter, not a sync filter — toggling it is instant and reversible
   without re-syncing.

### Why public-only mode is a display filter, not a sync filter

- Toggling between modes is instant; no waiting for a re-sync
- The user can record a demo / take screenshots / share a stream without
  leaking private repo names, and flip back without losing data
- One source of truth: the local DB always reflects everything the token
  can see; the UI decides what to show

### Defaults

- All visible repos start as `tracked = true` after first sync
- Public-only mode starts **off** (it's your dashboard; you presumably want
  to see everything)
- The first-run wizard surfaces both controls explicitly so the user makes
  a deliberate choice before any data is rendered

### What never leaves the machine

- No telemetry, no analytics pings, no remote logging by default
- No third-party calls except GitHub (always) and Anthropic (only when the
  user generates a digest, with the user's own API key)
- Postgres volume is the only stateful artifact — backup and rotate it
  exactly as the user would any other private DB
