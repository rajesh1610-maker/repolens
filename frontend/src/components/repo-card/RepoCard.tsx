"use client";

import Link from "next/link";
import { Star, GitFork, CircleDot, GitBranch, Lock } from "lucide-react";
import type { RepoSummary } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function RepoCard({ repo }: { repo: RepoSummary }) {
  const href = `/repos/${repo.owner}/${repo.name}`;
  const isPrivate = repo.visibility === "private";

  return (
    <Link
      href={href}
      className={cn(
        "group block rounded-lg border border-zinc-800 bg-zinc-950/50 p-5",
        "hover:border-zinc-700 hover:bg-zinc-900/50 transition-colors"
      )}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold truncate group-hover:text-teal-300 transition-colors">
              {repo.full_name}
            </h3>
            {isPrivate && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-950/50 text-amber-300 font-medium shrink-0">
                <Lock size={10} />
                private
              </span>
            )}
          </div>
        </div>
      </div>

      {repo.description && (
        <p className="text-xs text-zinc-400 line-clamp-2 mb-4 min-h-[2rem]">
          {repo.description}
        </p>
      )}
      {!repo.description && <div className="min-h-[2rem] mb-4" />}

      <div className="grid grid-cols-3 gap-2 mb-4 text-xs">
        <Stat icon={Star} label="stars" value={repo.stars} />
        <Stat icon={GitFork} label="forks" value={repo.forks} />
        <Stat icon={CircleDot} label="issues" value={repo.open_issues_count} />
      </div>

      <div className="flex items-center justify-between text-[11px] text-zinc-500 pt-3 border-t border-zinc-800/60">
        <span className="flex items-center gap-1.5">
          <GitBranch size={11} />
          {repo.default_branch ?? "—"}
        </span>
        <span title={repo.pushed_at ?? undefined}>
          pushed {timeAgo(repo.pushed_at)}
        </span>
      </div>
    </Link>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Star;
  label: string;
  value: number;
}) {
  return (
    <div className="flex items-center gap-1.5 text-zinc-400">
      <Icon size={12} />
      <span className="font-medium text-zinc-200">{value}</span>
      <span className="text-zinc-600">{label}</span>
    </div>
  );
}
