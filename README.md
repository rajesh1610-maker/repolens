# RepoLens

> Solo-maintainer cockpit for your entire OSS surface.

**Status:** Spec phase — not yet built
**Started:** 2026-05-07

GitHub gives you ten different screens for ten different things. RepoLens is one screen for all of them — across every repo you maintain.

## What it does

- **Unified inbox** — PRs, issues, mentions, review requests across every repo, with smart prioritization
- **Health pulse** — stars, traffic, clones, release cadence, contributor flow per repo, on one wall
- **Triage queue** — issues sorted by staleness, reactions, and "needs response" signal
- **Weekly AI digest** — a short narrative of what changed, what's stuck, what to do next
- **Release radar** — pending PRs vs. last release, draft release notes, "ready to ship?" check
- **Self-hosted, single binary feel** — your data stays on your machine; bring your own GitHub PAT

## Why now

Solo and small-team OSS maintainers are the GitHub long tail. They juggle 5–30 repos, each with its own sparse activity. GitHub's UI is repo-first; maintainers are person-first. RepoLens flips the axis.

## Stack (planned)

- **Backend:** FastAPI + Postgres + APScheduler (sync jobs)
- **Frontend:** Next.js 14 + Tailwind + shadcn/ui
- **AI:** Claude (Anthropic SDK) for digest + triage scoring
- **Auth:** GitHub OAuth (single-user mode for v0.1; multi-user later)
- **Deploy:** Docker Compose; one-command self-host

## Specs

1. [Vision & MVP scope](specs/01_vision_and_mvp.md)
2. [Data model](specs/02_data_model.md)
3. [Pages & UX](specs/03_pages_and_ux.md)
4. [Architecture](specs/04_architecture.md)
5. [GitHub integration](specs/05_github_integration.md)
6. [AI digest design](specs/06_ai_digest.md)
7. [Roadmap](specs/07_roadmap.md)
