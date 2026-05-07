"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, Inbox } from "lucide-react";
import { api, ApiError, type RepoSummary, SYNC_EVENT } from "@/lib/api";
import { RepoCard } from "@/components/repo-card/RepoCard";

type SortKey = "active" | "stars" | "alpha";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "active", label: "Most active" },
  { key: "stars", label: "Most stars" },
  { key: "alpha", label: "Alphabetical" },
];

function sortRepos(repos: RepoSummary[], key: SortKey): RepoSummary[] {
  const copy = [...repos];
  switch (key) {
    case "active":
      return copy.sort((a, b) => {
        const ta = a.pushed_at ? new Date(a.pushed_at).getTime() : 0;
        const tb = b.pushed_at ? new Date(b.pushed_at).getTime() : 0;
        return tb - ta;
      });
    case "stars":
      return copy.sort((a, b) => b.stars - a.stars);
    case "alpha":
      return copy.sort((a, b) =>
        a.full_name.toLowerCase().localeCompare(b.full_name.toLowerCase())
      );
  }
}

export default function ReposPage() {
  const [repos, setRepos] = useState<RepoSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("active");

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const r = await api<RepoSummary[]>("/api/repos");
      setRepos(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const handler = () => refresh();
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, [refresh]);

  const sorted = useMemo(
    () => (repos ? sortRepos(repos, sortKey) : null),
    [repos, sortKey]
  );

  return (
    <div>
      <div className="flex items-end justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-semibold mb-1">Repos</h1>
          <p className="text-zinc-400 text-sm">
            Tracked repos across your GitHub surface.
            {repos !== null && (
              <span className="text-zinc-500"> · {repos.length} shown</span>
            )}
          </p>
        </div>
        {repos && repos.length > 0 && (
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-teal-600 cursor-pointer"
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 mb-6 flex items-start gap-3 text-sm">
          <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div className="text-red-400/90">{error}</div>
        </div>
      )}

      {repos === null && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-5 h-44 animate-pulse"
            />
          ))}
        </div>
      )}

      {repos !== null && repos.length === 0 && !error && (
        <div className="rounded-lg border border-zinc-800 p-12 text-center">
          <Inbox size={32} className="mx-auto text-zinc-600 mb-3" />
          <div className="text-zinc-300 font-medium mb-1">No repos to show</div>
          <p className="text-sm text-zinc-500 max-w-md mx-auto">
            Either no sync has run yet, or every visible repo has been untracked.
            Use <span className="text-zinc-300">Sync now</span> in the sidebar, or
            check <Link href="/settings" className="text-teal-400 hover:underline">Settings</Link>.
          </p>
        </div>
      )}

      {sorted && sorted.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sorted.map((r) => (
            <RepoCard key={r.id} repo={r} />
          ))}
        </div>
      )}
    </div>
  );
}
