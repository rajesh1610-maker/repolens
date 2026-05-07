# RepoLens

> Solo-maintainer cockpit for your entire OSS surface.

**Status:** v0.1 — all 9 build phases complete · self-hosted single user
**Stack:** FastAPI · Postgres 15 · Next.js 14 · Anthropic Claude (optional)

GitHub gives you ten different screens for ten different things. RepoLens is one screen for all of them — across every repo you maintain.

## What it does

- **Unified inbox** — PRs, issues, mentions, review requests across every repo, with smart prioritization (`j`/`k` to navigate, `o` to open on GitHub, `?` for all shortcuts)
- **Health pulse** — stars, traffic, clones, release cadence, contributor flow per repo, on one wall
- **Triage queue** — three columns (Stale · Hot · Stuck) so you don't miss the issue that's been blocked for three weeks
- **Weekly AI digest** — Claude reads the last 7 days of repo activity and writes a 5-section narrative (Headline · What shipped · What's stuck · Community pulse · Suggested actions). Persists with full token + cost tracking.
- **Release radar** — pending PRs vs. last release, deterministic draft release notes, "ready to ship?" check
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

## Quick Start

Prerequisites: Docker (for Postgres), Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 18+.

```bash
# 1. Clone
git clone https://github.com/rajesh1610-maker/repolens.git
cd repolens

# 2. Postgres up
docker compose up -d postgres

# 3. Configure (the wizard will prompt for the PAT, but the encryption
#    key + DB url need to live in env)
cp .env.example backend/.env
python -c "import secrets; print('REPOLENS_ENCRYPTION_KEY=' + secrets.token_hex(32))" >> backend/.env

# 4. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn repolens.main:app --port 8004 --reload &

# 5. Frontend
cd ../frontend
npm install
npm run dev   # → http://localhost:3003

# 6. First run: open http://localhost:3003 — the in-app wizard walks you
#    through PAT entry, the first sync, and (optionally) an Anthropic key
#    for the weekly digest.
```

The PAT and Anthropic key are encrypted with AES-GCM at rest (master key from `REPOLENS_ENCRYPTION_KEY`). Public-only mode in Settings hides every private repo from the UI in one click — useful for screenshots and demos.

## Stack

- **Backend:** FastAPI + SQLAlchemy 2.0 (async) + asyncpg + Postgres 15 + APScheduler
- **Frontend:** Next.js 14 (App Router) + React 18 + Tailwind + hand-rolled SVG charts
- **AI:** Anthropic Claude (`claude-opus-4-7`, adaptive thinking) — only used for the weekly digest, only with your own key
- **Auth:** GitHub PAT (single-user mode in v0.1; multi-user planned for v0.4)
- **Crypto:** AES-GCM for PAT + API key at rest

## Operational notes

- **After editing `backend/.env`, restart the backend.** Settings are loaded once at process startup; `uvicorn --reload` reloads on Python source changes but not on `.env` changes.
- **Background scheduler is OFF by default** in dev (`uvicorn --reload` would restart it on every code change and burn API quota). Set `SCHEDULER_ENABLED=true` for the periodic sync + Sun-22:00-UTC weekly digest cron.
- **GitHub `/stats/contributors` is async on the GitHub side.** First call for a large repo returns 202; we record 0 contributors and pick them up on the next sync once GitHub finishes building the cache.

## Specs

1. [Vision & MVP scope](specs/01_vision_and_mvp.md)
2. [Data model](specs/02_data_model.md)
3. [Pages & UX](specs/03_pages_and_ux.md)
4. [Architecture](specs/04_architecture.md)
5. [GitHub integration](specs/05_github_integration.md)
6. [AI digest design](specs/06_ai_digest.md)
7. [Roadmap](specs/07_roadmap.md)
