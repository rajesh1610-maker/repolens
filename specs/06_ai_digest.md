# 06 — AI Digest Design

The weekly digest is the feature that turns RepoLens from a dashboard into a *companion*. It's also the riskiest feature — bad AI summaries are worse than no summaries.

## Design principles

1. **Grounded only.** Every claim in the digest must trace back to a fact we pulled from GitHub. No vibes.
2. **Useful > flashy.** The "suggested actions" section is the highest-value part. The narrative is supporting cast.
3. **Cost-aware.** A user with 30 repos should pay <$0.50/week.
4. **Consistent format.** Same five sections every week. Predictability lets the user skim quickly.
5. **Editable.** The digest is markdown the user can edit in-place. They own the output.

## Generation pipeline

```
                ┌────────────────────────┐
                │  Trigger               │
                │  (cron: Sun 22:00)     │
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │  Collector             │
                │  Pulls last-7d facts   │
                │  from Postgres         │
                └───────────┬────────────┘
                            │  structured JSON
                ┌───────────▼────────────┐
                │  Prompter              │
                │  Builds Claude prompt  │
                │  with system + facts   │
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │  Claude API            │
                │  Opus 4.7 (default)    │
                │  Prompt-cached         │
                └───────────┬────────────┘
                            │  markdown
                ┌───────────▼────────────┐
                │  Validator             │
                │  Checks structure,     │
                │  numbers match facts   │
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │  Persist + notify      │
                │  digests table         │
                └────────────────────────┘
```

## The collector

Pulls these facts from Postgres for the period [Mon-Sun]:

```python
{
  "period": {"start": "2026-04-27", "end": "2026-05-03"},
  "user": {"login": "rajeshiyer"},
  "repos": [
    {
      "full_name": "rajeshiyer/metricanchor",
      "stars_delta": 12,
      "stars_total": 247,
      "traffic": {"views": 482, "unique": 110, "clones": 8},
      "prs_opened": 3, "prs_merged": 4, "prs_closed": 1,
      "issues_opened": 7, "issues_closed": 5,
      "releases": [{"tag": "v0.3.0", "published_at": "2026-04-30"}],
      "top_contributors": [...],
      "stale_issues": [...]   # >60d, no activity
    },
    ...
  ],
  "highlights": {
    "biggest_pr": {...},          # most lines / most discussed
    "noisiest_issue": {...},      # most reactions
    "newest_contributor": {...},
  },
  "stuck": [
    {"kind": "pr", "url": "...", "title": "...", "stuck_for_days": 14, "last_activity": "..."},
    ...
  ],
}
```

This JSON is the **only** input to the model. No raw GitHub payloads, no PR diffs (too much token cost, too noisy).

## The prompt (sketch)

### System prompt (cacheable, never changes per user)
```
You are a digest writer for RepoLens, a tool that helps OSS maintainers
keep track of their repositories.

You will receive structured JSON facts about one user's GitHub activity
over the past week. Generate a markdown digest with EXACTLY these five
sections, in this order, with these exact H2 headings:

## Headline
A single sentence (max 25 words) summarizing the week's most important
event for this maintainer.

## What shipped
List of releases this week, one bullet per release, format:
- **{repo} {tag}** — {1-line description from release body, paraphrased}

If no releases: "No releases this week." (no padding text)

## What's stuck
List up to 5 items from the `stuck` array. For each: bullet with
{repo}#{number}, title, days stuck, and a short interpretation of WHY
it might be stuck (label, no reviewer, etc.). Be honest if you don't
know the reason from the data.

## Community pulse
2-4 short paragraphs covering: stars (call out repos with >10 stars/week
gain), traffic spikes, new contributors, and any repo that went silent
(no commits in >30d among tracked).

## Suggested actions for the week ahead
Exactly 3-5 numbered items. Each is a concrete, actionable task. Pull
from `stuck`, low-hanging triage, releases close to ready. Each item
must reference a specific repo/PR/issue when possible.

RULES (non-negotiable):
- Every number you state must appear in the input JSON. If you can't
  verify a number, omit it rather than guess.
- Don't editorialize about the maintainer's personality, work-life
  balance, or "good job" pep talk. They're an adult.
- Don't predict the future. Stick to what happened and what's
  actionable.
- If the data is sparse (quiet week), the digest should be short.
  No filler.
```

### User message (per-week)
```
Here is the data for the period {start} to {end}:

```json
{collector output}
```

Generate the digest now.
```

## Model & cost

- **Default:** `claude-opus-4-7` (Opus 4.7 1M context if available, regular Opus otherwise)
- **Cheap mode:** `claude-haiku-4-5` (user-toggle in Settings → AI; ~10× cheaper, slightly less coherent narrative)
- **Prompt caching:** the system prompt is identical every week → cache it. Saves ~60% on input tokens.
- **Estimated tokens per week:** 8K input (most cached) + 1.5K output. ~$0.08/week with Opus, ~$0.005 with Haiku.

## Validator

Before persisting, check:
- All five required H2 headings present, in order
- "What shipped" releases referenced are in the input JSON
- Numbers in the body appear in the input JSON (regex extract digits, set-membership check)
- Total length 200–800 words

If any check fails: regenerate up to 2× with the same input. If still failing, persist anyway with a `validation_warnings` field shown to user — never hide errors.

## Failure modes

| Failure | Handling |
|---|---|
| Anthropic API down | Retry with backoff; if 3 fails, write a "stub" digest from the input JSON (templated, no AI), mark with `model: "fallback-template"` |
| API key invalid | Disable digest generation, banner in Digest page directs to Settings |
| Budget cap hit | Skip generation; banner: "Monthly Anthropic budget reached. Update in Settings." |
| Validator rejects 3× | Persist with warnings; user can regenerate manually |

## On-demand regeneration

User can regenerate any past or current digest from the Digest page. Click → confirm modal showing estimated cost → run. Useful when:
- They edited tracked repos and want a fresh take
- They just shipped something major and want it reflected
- The first run was a fallback template

## Why this is differentiated

Most "AI dashboard" tools throw the entire raw activity into a prompt and pray. RepoLens collects facts deterministically, lets the model do narrative + prioritization, and validates output against the source data. The model is the *narrator*, not the *researcher*.

That separation is what makes the digest trustworthy — and trustworthy is what makes it forwardable. A digest you'd CC your co-maintainer is the bar.
