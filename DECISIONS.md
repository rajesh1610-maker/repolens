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
