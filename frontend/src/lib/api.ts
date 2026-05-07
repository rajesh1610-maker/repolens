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
  pushed_at: string | null;
  tracked: boolean;
  synced_at: string | null;
};
