const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8004";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // not JSON — use statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export type Healthz = {
  status: string;
  db: string;
  version: string;
};

export type SettingsOverview = {
  user: {
    configured: boolean;
    github_login: string | null;
    avatar_url: string | null;
    has_pat: boolean;
    has_anthropic_key: boolean;
    public_only_mode: boolean;
  };
  repos: {
    total: number;
    tracked: number;
    public: number;
    private: number;
  };
  scheduler: {
    enabled: boolean;
    interval_minutes: number;
    watchdog_minutes: number;
  };
};

export type RepoSummary = {
  id: string;
  github_id: number;
  owner: string;
  name: string;
  full_name: string;
  description: string | null;
  visibility: "public" | "private";
  default_branch: string | null;
  stars: number;
  forks: number;
  open_issues_count: number;
  open_pulls_count: number;
  open_issues_real_count: number;
  merged_pulls_30d: number;
  stars_30d: number[];
  pushed_at: string | null;
  tracked: boolean;
  synced_at: string | null;
};

export type TrafficPoint = {
  day: string;
  views: number;
  unique_views: number;
  clones: number;
  unique_clones: number;
};

export type TrafficResponse = {
  repo_full_name: string;
  days: number;
  series: TrafficPoint[];
  totals: {
    views: number;
    unique_views_max: number;
    clones: number;
    unique_clones_max: number;
  };
};

export type ContributorRow = {
  id: string;
  github_login: string;
  avatar_url: string | null;
  commits_total: number;
  last_commit_at: string | null;
};

export type ContributorsResponse = {
  items: ContributorRow[];
  total: number;
};

export type PullRequestRow = {
  id: string;
  number: number;
  title: string;
  state: "open" | "closed" | "merged";
  draft: boolean;
  author_login: string | null;
  author_avatar_url: string | null;
  labels: string[];
  created_at: string | null;
  updated_at: string | null;
  closed_at: string | null;
  merged_at: string | null;
};

export type IssueRow = {
  id: string;
  number: number;
  title: string;
  state: "open" | "closed";
  author_login: string | null;
  author_avatar_url: string | null;
  labels: string[];
  comments_count: number;
  reactions_total: number;
  created_at: string | null;
  updated_at: string | null;
  closed_at: string | null;
};

export type Paginated<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type SyncRunSummary = {
  id: string;
  status: "running" | "ok" | "failed";
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  repos_synced: number;
  pulls_synced: number;
  issues_synced: number;
  releases_synced?: number;
  traffic_days_synced?: number;
  contributors_synced?: number;
  api_calls: number;
  rate_limit_remaining: number | null;
  error: string | null;
};

export type RecentRunsResponse = {
  items: SyncRunSummary[];
  limit: number;
};

export type InboxKind = "pr" | "issue";

export type InboxRow = {
  id: string;
  kind: InboxKind;
  source_id: string;
  repo_id: string;
  repo_full_name: string;
  repo_visibility: "public" | "private";
  number: number;
  title: string;
  url: string;
  state: string;
  draft: boolean;
  author_login: string | null;
  author_avatar_url: string | null;
  labels: string[];
  reactions_total: number;
  comments_count: number;
  priority_score_static: number;
  total_score: number;
  is_review_request: boolean;
  is_mention: boolean;
  is_needs_response: boolean;
  is_stale: boolean;
  last_activity_at: string | null;
};

export type InboxResponse = {
  items: InboxRow[];
  total: number;
  limit: number;
  offset: number;
  facets: {
    all: number;
    pr: number;
    issue: number;
    with_reactions: number;
  };
};

export type TriageIssue = {
  id: string;
  repo_full_name: string;
  repo_visibility: "public" | "private";
  number: number;
  title: string;
  url: string;
  author_login: string | null;
  author_avatar_url: string | null;
  labels: string[];
  comments_count: number;
  reactions_total: number;
  updated_at: string | null;
  created_at: string | null;
};

export type TriageResponse = {
  stale: TriageIssue[];
  hot: TriageIssue[];
  stuck: TriageIssue[];
};

export type ReleaseOverviewItem = {
  repo_id: string;
  owner: string;
  name: string;
  full_name: string;
  visibility: "public" | "private";
  latest_tag: string | null;
  latest_published_at: string | null;
  unreleased_pr_count: number;
};

export type ReleasesOverviewResponse = {
  items: ReleaseOverviewItem[];
};

export type ReleaseDraftPull = {
  number: number;
  title: string;
  labels: string[];
  author_login: string | null;
  merged_at: string | null;
};

export type ReleaseDraft = {
  repo_full_name: string;
  next_tag: string;
  previous_tag: string | null;
  previous_published_at: string | null;
  pull_count: number;
  pulls: ReleaseDraftPull[];
  notes_markdown: string;
};

export type LastSyncResponse = {
  last_run: SyncRunSummary | null;
};

export const SYNC_EVENT = "repolens:synced";
