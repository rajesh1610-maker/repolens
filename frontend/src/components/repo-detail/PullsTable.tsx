import { ExternalLink, MessageSquare } from "lucide-react";
import type { PullRequestRow } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PullsTable({
  rows,
  total,
  fullName,
}: {
  rows: PullRequestRow[];
  total: number;
  fullName: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
        No PRs match this filter.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 overflow-hidden">
      <div className="px-4 py-2 bg-zinc-900/50 text-xs text-zinc-500 border-b border-zinc-800">
        Showing {rows.length} of {total} PRs
      </div>
      <ul className="divide-y divide-zinc-800">
        {rows.map((pr) => (
          <li key={pr.id} className="p-4 hover:bg-zinc-900/30 transition-colors">
            <div className="flex items-start gap-3">
              {pr.author_avatar_url && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={pr.author_avatar_url}
                  alt=""
                  className="w-6 h-6 rounded-full mt-0.5 shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <StatePill state={pr.state} draft={pr.draft} />
                  <a
                    href={`https://github.com/${fullName}/pull/${pr.number}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium hover:text-teal-300 truncate group inline-flex items-center gap-1"
                  >
                    <span className="text-zinc-500">#{pr.number}</span>
                    <span className="truncate">{pr.title}</span>
                    <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 shrink-0" />
                  </a>
                </div>
                <div className="flex items-center gap-3 text-xs text-zinc-500">
                  <span>{pr.author_login}</span>
                  <span>updated {timeAgo(pr.updated_at)}</span>
                  {pr.labels.length > 0 && (
                    <div className="flex gap-1 flex-wrap">
                      {pr.labels.slice(0, 3).map((l) => (
                        <span
                          key={l}
                          className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[10px]"
                        >
                          {l}
                        </span>
                      ))}
                      {pr.labels.length > 3 && (
                        <span className="text-zinc-600 text-[10px]">
                          +{pr.labels.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StatePill({ state, draft }: { state: PullRequestRow["state"]; draft: boolean }) {
  const label = draft ? "draft" : state;
  const cls =
    draft
      ? "bg-zinc-800 text-zinc-400"
      : state === "open"
        ? "bg-emerald-950/50 text-emerald-300"
        : state === "merged"
          ? "bg-purple-950/50 text-purple-300"
          : "bg-zinc-800 text-zinc-500";
  return (
    <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide shrink-0", cls)}>
      {label}
    </span>
  );
}
