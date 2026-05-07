# RepoLens

> Solo-maintainer cockpit for your entire OSS surface.

**Status:** Phases 0–7 complete (incl. test backfill + 2 QA passes) · Phase 8 (AI digest) next · v0.1 target
**Started:** 2026-05-07

GitHub gives you ten different screens for ten different things. RepoLens is one screen for all of them — across every repo you maintain.

## What it does

- **Unified inbox** — PRs, issues, mentions, review requests across every repo, with smart prioritization
- **Health pulse** — stars, traffic, clones, release cadence, contributor flow per repo, on one wall
- **Triage queue** — issues sorted by staleness, reactions, and "needs response" signal
- **Weekly AI digest** — a short narrative of what changed, what's stuck, what to do next
- **Release radar** — pending PRs vs. last release, draft release notes, "ready to ship?" check
- **Self-hosted, single binary feel** — your data stays on your machine; bring your own GitHub PAT

## 🔒 Privacy & visibility — read this first

**RepoLens sees exactly what your GitHub token sees.** A token with the `repo`
scope can read your private repos; a token without it cannot. Choose your
token's scope deliberately.

Two independent controls decide what shows up in the UI:

| Control | Default | Where | Effect |
|---|---|---|---|
| **Per-repo tracking** | every visible repo on | Settings → Tracked repos | Untrack a repo to exclude it from sync, Inbox, wall, digest |
| **Public-only mode** | off | Settings → Visibility | Hides every *private* repo from Inbox, Repos wall, Triage, Releases, and Digest in one click. Useful for screenshots, demos, recording streams |

The data model is honest: every repo your token can see gets pulled into the
local Postgres so toggles are instant — but **nothing about your private
repos ever leaves your machine.** RepoLens has no telemetry, no cloud
backend, and no third-party services beyond GitHub itself and (optionally)
the Anthropic API for the weekly digest. The digest sender is your own key,
and the prompt only includes the facts you've allowed in.

If you're sharing screenshots of RepoLens publicly, flip on public-only
mode in Settings — the entire UI then shows only what GitHub already shows
the world.

## Why now

Solo and small-team OSS maintainers are the GitHub long tail. They juggle 5–30 repos, each with its own sparse activity. GitHub's UI is repo-first; maintainers are person-first. RepoLens flips the axis.

## Stack (planned)

- **Backend:** FastAPI + Postgres + APScheduler (sync jobs)
- **Frontend:** Next.js 14 + Tailwind + shadcn/ui
- **AI:** Claude (Anthropic SDK) for digest + triage scoring
- **Auth:** GitHub OAuth (single-user mode for v0.1; multi-user later)
- **Deploy:** Docker Compose; one-command self-host

## Operational notes

Sharp edges to be aware of while RepoLens is in active development. Phase 9
will replace this with a proper self-host guide.

- **After editing `backend/.env`, restart the backend.** Settings are loaded
  once at process startup; `uvicorn --reload` reloads on Python source
  changes but not on `.env` changes.

## Specs

1. [Vision & MVP scope](specs/01_vision_and_mvp.md)
2. [Data model](specs/02_data_model.md)
3. [Pages & UX](specs/03_pages_and_ux.md)
4. [Architecture](specs/04_architecture.md)
5. [GitHub integration](specs/05_github_integration.md)
6. [AI digest design](specs/06_ai_digest.md)
7. [Roadmap](specs/07_roadmap.md)
