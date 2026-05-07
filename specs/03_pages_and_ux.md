# 03 — Pages & UX

Seven pages in v0.1. Sidebar nav, no top-bar tabs (saves vertical space).

## Sidebar nav

```
RepoLens
─────────
🏠  Inbox            ← default landing
🧱  Repos            ← the wall
🎯  Triage
📦  Releases
✨  Digest
⚙️  Settings
```

Bottom of sidebar: last sync time + manual "Sync now" button. Active rate-limit indicator (e.g. "4,521 / 5,000 remaining") on hover.

---

## 1. Inbox (`/`)

**Purpose:** "What needs me, across everything?"

### Layout
- **Top:** filter chips — `All`, `Needs response`, `Mentions`, `Review requests`, `Stale`
- **Body:** vertical list of inbox items, sorted by `priority_score desc`
- Each row: avatar · `repo/name#123` · title · age · priority chip (red/amber/green) · action shortcut

### Row interactions
- Click row → expand inline: first comment, last comment, label list, "open on GitHub" link
- Hover row → hotkeys: `j/k` to move, `o` to open externally, `s` to snooze (v0.2)

### Empty states
- Zero items: *"Inbox zero. Go build something."* (with a tiny RepoLens mascot)
- No tracked repos: CTA to Settings → pick repos

### What it gets right
- No infinite scroll — paginated 50 at a time. The whole point is to *finish* the inbox.

---

## 2. Repos (`/repos`)

**Purpose:** the health wall. One glance tells you which repos are alive, which are sick, which are dead.

### Layout
- Grid of cards, 3 columns desktop, 1 mobile
- Sort dropdown: `Most active`, `Most stars`, `Last release`, `Alphabetical`

### Card content (per repo)
```
┌──────────────────────────────────────┐
│  owner/repo-name           ⭐ 1,247  │  ← +12 this week (green)
│  short description text here…        │
│                                      │
│  ┌─────┬─────┬─────┬─────┐          │
│  │ PRs │ Iss │ Rel │ Trf │          │
│  │  3  │ 17  │ 2w  │ 482 │          │
│  └─────┴─────┴─────┴─────┘          │
│                                      │
│  ▁▂▅▃▆▇▅  stars 30d sparkline        │
│                                      │
│  Last commit 3h ago · main           │
└──────────────────────────────────────┘
```

- Click card → repo detail page
- Visual cue: card border tinted red if "needs attention" (open issues > threshold AND no commit in 30d, etc.)

---

## 3. Repo detail (`/repos/[owner]/[name]`)

**Purpose:** drill-down for a single repo without leaving RepoLens.

### Tabs (within the page)
1. **Overview** — readme excerpt, key stats, traffic chart (28 days), star history (90 days)
2. **PRs** — table; columns: #, title, author, age, reviewers, status
3. **Issues** — table; columns: #, title, author, age, reactions, labels
4. **Releases** — list with collapsible bodies
5. **Contributors** — last-90d activity grid

### Top of page
- `← All repos` breadcrumb
- Repo name (large), description, topic tags, "Open on GitHub" button
- Action row: `Sync now` · `Untrack` · `Open repo`

---

## 4. Triage (`/triage`)

**Purpose:** specifically for issues you've been ignoring. Different vibe from Inbox — this is "OSS hygiene" not "today's work."

### Layout
Three columns (drag/drop in v0.2; static in v0.1):
- **Stale** — open >60d, no recent activity
- **Hot** — high reactions, no maintainer response
- **Stuck** — labeled `needs-info` / `awaiting-response` for >14d

Each column = scrollable list of issue cards. Card shows: repo · title · age · reactions · labels · last commenter avatar.

### Bulk actions (v0.2)
- Multi-select → bulk apply label, close, lock. v0.1: just *view*, not act.

---

## 5. Releases (`/releases`)

**Purpose:** what's ready to ship across all repos.

### Layout
Two-pane:
- **Left:** list of repos with unreleased commits (by `commits since last release` count, desc)
- **Right:** detail of selected repo:
  - Last release: tag, date, body
  - Unreleased PRs since that tag (categorized: feat / fix / breaking / chore by label or commit prefix)
  - Draft release notes (AI-suggested, editable, copy button — does NOT post to GitHub in v0.1)

### Why this is here
Most maintainers know they *should* ship more often but don't because writing notes is friction. RepoLens removes that friction.

---

## 6. Digest (`/digest`)

**Purpose:** the weekly narrative.

### Layout
- **Top:** date selector — defaults to most recent week, dropdown lists prior weeks
- **Body:** rendered markdown of the digest
- **Right rail:** metadata — period, model used, tokens, cost, regenerate button

### Sections in a digest (consistent format)
1. **Headline** — one sentence
2. **What shipped** — releases this week, by repo
3. **What's stuck** — high-priority items still unresolved
4. **Community pulse** — stars/traffic/contributor highlights
5. **Suggested actions for the week ahead** — AI-generated todo list, 3–5 items
6. **Numbers** — appendix table of raw stats

### Actions
- `Copy markdown` · `Download .md` · `Regenerate` (uses Claude credits — confirm modal)

---

## 7. Settings (`/settings`)

Single-page sectioned form:
1. **GitHub connection** — PAT entry, scopes status, "Test connection" button
2. **Tracked repos** — checklist of all your repos; check/uncheck to track. "Track all" / "Untrack all" shortcuts
3. **Visibility** — `[ ] Public-only mode` toggle. When on, every page hides private repos. The section explains: *"Useful for screenshots, demos, and screen-shares. Toggling is instant and does not re-sync — your data stays put."* Counter shows e.g. *"Currently visible: 12 repos (4 private hidden)."*
4. **AI** — Anthropic API key entry, model selector (Opus / Sonnet / Haiku), monthly budget cap
5. **Digest** — schedule (day/time/timezone), enable/disable, recipients (just you in v0.1)
6. **Sync** — frequency (15m / 30m / 1h / 4h), "Sync now" button, last 10 sync runs table
7. **Danger zone** — wipe local data, re-init schema

---

## Cross-cutting UX notes

### Visual language
- Borrow from MetricAnchor / household-os: clean sidebar, generous whitespace, calm palette
- Dark mode default; light mode toggle in sidebar bottom
- One accent color (suggest: a deep teal — distinct from GitHub's blue and Vercel's black)

### Performance budget
- Initial paint of any page ≤ 200ms when data is cached locally
- Inbox list: virtualized if > 200 items
- All charts client-side rendered (Recharts or Visx) — no server-rendered images

### Keyboard
- `g i` Inbox · `g r` Repos · `g t` Triage · `g d` Digest · `g s` Settings
- `j/k` move within lists · `o` open externally · `?` show shortcut overlay

### Motion
- Subtle. Fade transitions on route changes (150ms). No celebratory animations — this is a maintenance tool, not a game.

### Empty / error states
- Every page handles: no data yet (first run), API rate-limited, network error, sync in progress
- A "first run" mode shows a 4-step setup wizard before the Inbox is meaningful
