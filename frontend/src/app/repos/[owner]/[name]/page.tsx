"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ExternalLink, AlertCircle, Star, GitFork } from "lucide-react";
import {
  api,
  ApiError,
  SYNC_EVENT,
  type ContributorsResponse,
  type IssueRow,
  type Paginated,
  type PullRequestRow,
  type RepoSummary,
  type TrafficResponse,
} from "@/lib/api";
import { Tabs, type TabKey } from "@/components/repo-detail/Tabs";
import { OverviewPanel } from "@/components/repo-detail/OverviewPanel";
import { PullsTable } from "@/components/repo-detail/PullsTable";
import { IssuesTable } from "@/components/repo-detail/IssuesTable";
import { ContributorsPanel } from "@/components/repo-detail/ContributorsPanel";

type StateFilter = "all" | "open" | "closed" | "merged";

export default function RepoDetailPage({
  params,
}: {
  params: { owner: string; name: string };
}) {
  const { owner, name } = params;
  const fullName = `${owner}/${name}`;
  const githubUrl = `https://github.com/${fullName}`;

  const [repo, setRepo] = useState<RepoSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("overview");

  const [pulls, setPulls] = useState<Paginated<PullRequestRow> | null>(null);
  const [issues, setIssues] = useState<Paginated<IssueRow> | null>(null);
  const [traffic, setTraffic] = useState<TrafficResponse | null>(null);
  const [contributors, setContributors] = useState<ContributorsResponse | null>(null);
  const [pullsState, setPullsState] = useState<StateFilter>("all");
  const [issuesState, setIssuesState] = useState<"all" | "open" | "closed">("all");

  const loadRepo = useCallback(async () => {
    setError(null);
    try {
      const r = await api<RepoSummary>(`/api/repos/${owner}/${name}`);
      setRepo(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [owner, name]);

  const loadPulls = useCallback(async () => {
    try {
      const r = await api<Paginated<PullRequestRow>>(
        `/api/repos/${owner}/${name}/pulls?state=${pullsState}&limit=50`
      );
      setPulls(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [owner, name, pullsState]);

  const loadIssues = useCallback(async () => {
    try {
      const r = await api<Paginated<IssueRow>>(
        `/api/repos/${owner}/${name}/issues?state=${issuesState}&limit=50`
      );
      setIssues(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [owner, name, issuesState]);

  const loadTraffic = useCallback(async () => {
    try {
      setTraffic(await api<TrafficResponse>(`/api/repos/${owner}/${name}/traffic`));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [owner, name]);

  const loadContributors = useCallback(async () => {
    try {
      setContributors(
        await api<ContributorsResponse>(`/api/repos/${owner}/${name}/contributors`),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [owner, name]);

  // Initial load + sync-event refresh
  useEffect(() => {
    loadRepo();
    loadTraffic();  // Traffic shows on Overview, which is the default tab
    const handler = () => {
      loadRepo();
      loadTraffic();
      if (tab === "pulls") loadPulls();
      if (tab === "issues") loadIssues();
      if (tab === "contributors") loadContributors();
    };
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, [loadRepo, loadTraffic, loadPulls, loadIssues, loadContributors, tab]);

  // Single effect handles tab activation and filter changes.
  // The `if (tab === ...)` guards prevent loading when on a different tab.
  useEffect(() => {
    if (tab === "pulls") loadPulls();
    if (tab === "issues") loadIssues();
    if (tab === "contributors") loadContributors();
  }, [tab, pullsState, issuesState, loadPulls, loadIssues, loadContributors]);

  if (error) {
    return (
      <div className="max-w-4xl">
        <Link
          href="/repos"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 mb-6 transition-colors"
        >
          <ArrowLeft size={12} />
          All repos
        </Link>
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-6 flex items-start gap-3">
          <AlertCircle size={18} className="text-red-400 mt-0.5 shrink-0" />
          <div>
            <div className="text-red-300 font-medium mb-1">Couldn&apos;t load {fullName}</div>
            <div className="text-sm text-red-400/80">{error}</div>
          </div>
        </div>
      </div>
    );
  }

  if (!repo) {
    return <div className="text-zinc-400">Loading {fullName}…</div>;
  }

  return (
    <div className="max-w-5xl">
      <Link
        href="/repos"
        className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 mb-6 transition-colors"
      >
        <ArrowLeft size={12} />
        All repos
      </Link>

      <div className="flex items-start justify-between gap-4 mb-2">
        <div>
          <h1 className="text-2xl font-semibold">{repo.full_name}</h1>
          <div className="flex items-center gap-4 text-xs text-zinc-500 mt-2">
            <span className="inline-flex items-center gap-1">
              <Star size={12} />
              {repo.stars}
            </span>
            <span className="inline-flex items-center gap-1">
              <GitFork size={12} />
              {repo.forks}
            </span>
            <span
              className={
                repo.visibility === "private"
                  ? "text-amber-300 px-1.5 py-0.5 rounded bg-amber-950/50"
                  : "text-zinc-500"
              }
            >
              {repo.visibility}
            </span>
          </div>
        </div>
        <a
          href={githubUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 px-3 py-1.5 rounded-md border border-zinc-800 hover:border-zinc-700 transition-colors shrink-0"
        >
          Open on GitHub
          <ExternalLink size={12} />
        </a>
      </div>

      {repo.description && (
        <p className="text-sm text-zinc-400 mb-8 max-w-3xl">{repo.description}</p>
      )}

      <Tabs
        active={tab}
        onChange={setTab}
        badges={{
          pulls: repo.open_pulls_count,
          issues: repo.open_issues_real_count,
        }}
      />

      {tab === "overview" && <OverviewPanel repo={repo} traffic={traffic} />}

      {tab === "pulls" && (
        <div>
          <StateFilterBar
            options={["all", "open", "merged", "closed"]}
            value={pullsState}
            onChange={(v) => setPullsState(v as StateFilter)}
          />
          {pulls ? (
            <PullsTable rows={pulls.items} total={pulls.total} fullName={fullName} />
          ) : (
            <Skeleton />
          )}
        </div>
      )}

      {tab === "issues" && (
        <div>
          <StateFilterBar
            options={["all", "open", "closed"]}
            value={issuesState}
            onChange={(v) => setIssuesState(v as "all" | "open" | "closed")}
          />
          {issues ? (
            <IssuesTable rows={issues.items} total={issues.total} fullName={fullName} />
          ) : (
            <Skeleton />
          )}
        </div>
      )}

      {tab === "releases" && (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
          See the <Link href="/releases" className="text-teal-400 hover:underline">Releases page</Link> for the full draft-notes view across all repos, or click{" "}
          <a href={`${githubUrl}/releases`} target="_blank" rel="noreferrer" className="text-teal-400 hover:underline">Releases on GitHub</a>.
        </div>
      )}

      {tab === "contributors" && (
        contributors ? (
          <ContributorsPanel rows={contributors.items} fullName={fullName} />
        ) : (
          <Skeleton />
        )
      )}
    </div>
  );
}

function StateFilterBar({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex gap-1 mb-4">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={
            value === o
              ? "px-3 py-1 rounded-md bg-zinc-800 text-zinc-100 text-xs font-medium"
              : "px-3 py-1 rounded-md text-zinc-500 hover:text-zinc-300 text-xs font-medium"
          }
        >
          {o}
        </button>
      ))}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-12 animate-pulse">
      <div className="h-2 bg-zinc-800 rounded w-1/3 mb-3" />
      <div className="h-2 bg-zinc-800 rounded w-2/3 mb-3" />
      <div className="h-2 bg-zinc-800 rounded w-1/2" />
    </div>
  );
}
