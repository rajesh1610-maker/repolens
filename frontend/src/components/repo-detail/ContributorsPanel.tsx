"use client";

import { GitCommit } from "lucide-react";
import type { ContributorRow } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export function ContributorsPanel({
  rows,
  fullName,
}: {
  rows: ContributorRow[];
  fullName: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
        No contributor data yet. GitHub computes this asynchronously — it
        usually appears on the next sync after a fresh repo is added.
      </div>
    );
  }

  // Highest commit count drives the bar scale
  const maxCommits = Math.max(...rows.map((r) => r.commits_total), 1);

  return (
    <div className="rounded-lg border border-zinc-800 overflow-hidden">
      <div className="px-4 py-2 bg-zinc-900/50 text-xs text-zinc-500 border-b border-zinc-800">
        {rows.length} contributor{rows.length === 1 ? "" : "s"} · last 90 days of
        activity, sorted by commits
      </div>
      <ul className="divide-y divide-zinc-800">
        {rows.map((c) => {
          const pct = (c.commits_total / maxCommits) * 100;
          return (
            <li key={c.id} className="px-4 py-3 flex items-center gap-3">
              {c.avatar_url && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={c.avatar_url}
                  alt=""
                  className="w-8 h-8 rounded-full shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <a
                    href={`https://github.com/${c.github_login}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium hover:text-teal-300"
                  >
                    {c.github_login}
                  </a>
                  <span className="text-[10px] text-zinc-500" title={c.last_commit_at ?? undefined}>
                    last commit {timeAgo(c.last_commit_at)}
                  </span>
                </div>
                <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-teal-600/70"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
              <div className="text-xs text-zinc-300 tabular-nums shrink-0 w-16 text-right inline-flex items-center justify-end gap-1">
                <GitCommit size={11} className="text-zinc-500" />
                {c.commits_total}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
