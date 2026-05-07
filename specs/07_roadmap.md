# 07 — Roadmap

Rough phasing. Dates are aspirational and based on weekend builds, not full-time work.

## v0.1 — "Personal cockpit" (target: 2 weekends)

**Goal:** the user can dogfood it on their own GitHub repos.

- [ ] Project scaffolding (Docker Compose, FastAPI, Next.js, Postgres)
- [ ] Alembic migrations for all tables in `02_data_model.md`
- [ ] PAT auth flow + encryption
- [ ] GitHub sync service: repos, PRs, issues, releases, traffic, stars
- [ ] APScheduler with 30-min sync cadence
- [ ] Inbox page (with priority scoring)
- [ ] Repos page (the wall)
- [ ] Repo detail page (overview tab + PRs/issues tabs)
- [ ] Triage page (3 columns, static)
- [ ] Releases page (list + draft notes, copy-only)
- [ ] Digest generator + Sunday cron + Digest page
- [ ] Settings page (PAT, tracked repos, AI key, digest schedule)
- [ ] First-run wizard
- [ ] README with screenshots, "self-host in 5 minutes" guide
- [ ] Push to public GitHub repo, MIT license

**Definition of done:** user replaces 80% of their github.com tab usage with RepoLens for one week.

---

## v0.2 — "Public-ready" (target: +1 weekend)

**Goal:** ready for /r/selfhosted and Hacker News.

- [ ] GitHub OAuth app (in addition to PAT)
- [ ] Snooze inbox items (UI + DB column)
- [ ] Bulk actions in Triage (multi-select → label/close)
- [ ] Hotkey overlay (`?`)
- [ ] Mobile-responsive sidebar (drawer)
- [ ] Light/dark theme toggle in sidebar
- [ ] Performance pass: virtualized inbox, prefetch on hover
- [ ] Render.com / Fly.io / Coolify recipes in `/deploy/`
- [ ] Demo screenshots in README
- [ ] Show HN post draft

**Definition of done:** a stranger can self-host RepoLens in under 10 minutes from a fresh VM.

---

## v0.3 — "Live & loud" (target: +2 weekends)

**Goal:** real-time without polling.

- [ ] GitHub webhooks (opt-in; requires public URL)
- [ ] Real-time inbox via SSE
- [ ] Notifications API integration (replaces substring mention detection)
- [ ] Email digest delivery (SMTP-configurable)
- [ ] Slack/Discord webhook output for digest
- [ ] Custom inbox filters (saved searches)

---

## v0.4 — "Multi-user" (stretch)

**Goal:** small team can share an instance.

- [ ] Multi-user accounts, GitHub OAuth required
- [ ] Per-user tracked-repo lists
- [ ] Shared org view (everyone tracks the same set, individual inboxes)
- [ ] Role: admin / member
- [ ] Per-user Anthropic key OR shared org key with quota

This is where RepoLens stops being a personal tool and starts being a *team* tool. It's also where complexity explodes — only do it if v0.1–0.3 get traction.

---

## v0.5+ — Speculative

Things to consider only if there's pull from real users:

- **Comparator** — "your repo vs. similar repos" (stars, issue close rate, contributor count) — needs careful framing to avoid feeling judgmental
- **GitLab + Bitbucket** — different APIs, lots of work for niche audiences
- **Custom rules engine** — if X happens, do Y. (Or: just point users at GitHub Actions and stay focused.)
- **Plugin SDK** — third parties extend the dashboard. Premature.
- **Hosted SaaS version of RepoLens** — possible monetization, but compromises the OSS ethos. Decide later.

---

## What we won't do (the long "no" list)

These come up a lot in feedback for tools like this. Keep saying no until proven wrong:

- Become a writeable GitHub client (commenting, merging) — github.com is right there
- Become a CI dashboard — Actions tab does it; we'd half-ass it
- Become a project management tool — Linear/Jira/Issues exist
- Add gamification (streaks, badges) — wrong vibe for this user
- Build a marketplace for triage rules / digest templates — overhead trap
- Train a custom model on the user's data — irrelevant differentiation

---

## Decision log (to be filled as we build)

This file plus a `DECISIONS.md` in the repo will track each non-trivial choice with date + reasoning. The point is to make it easy for a contributor (or future-you) to understand *why* things are shaped the way they are.
