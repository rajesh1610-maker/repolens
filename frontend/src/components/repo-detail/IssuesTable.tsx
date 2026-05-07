import { ExternalLink, MessageSquare, Heart } from "lucide-react";
import type { IssueRow } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function IssuesTable({
  rows,
  total,
  fullName,
}: {
  rows: IssueRow[];
  total: number;
  fullName: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
        No issues match this filter.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 overflow-hidden">
      <div className="px-4 py-2 bg-zinc-900/50 text-xs text-zinc-500 border-b border-zinc-800">
        Showing {rows.length} of {total} issues
      </div>
      <ul className="divide-y divide-zinc-800">
        {rows.map((issue) => (
          <li key={issue.id} className="p-4 hover:bg-zinc-900/30 transition-colors">
            <div className="flex items-start gap-3">
              {issue.author_avatar_url && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={issue.author_avatar_url}
                  alt=""
                  className="w-6 h-6 rounded-full mt-0.5 shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <StatePill state={issue.state} />
                  <a
                    href={`https://github.com/${fullName}/issues/${issue.number}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium hover:text-teal-300 truncate group inline-flex items-center gap-1"
                  >
                    <span className="text-zinc-500">#{issue.number}</span>
                    <span className="truncate">{issue.title}</span>
                    <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 shrink-0" />
                  </a>
                </div>
                <div className="flex items-center gap-3 text-xs text-zinc-500">
                  <span>{issue.author_login}</span>
                  <span>updated {timeAgo(issue.updated_at)}</span>
                  <span className="inline-flex items-center gap-1">
                    <MessageSquare size={11} />
                    {issue.comments_count}
                  </span>
                  {issue.reactions_total > 0 && (
                    <span className="inline-flex items-center gap-1 text-amber-400">
                      <Heart size={11} />
                      {issue.reactions_total}
                    </span>
                  )}
                  {issue.labels.length > 0 && (
                    <div className="flex gap-1 flex-wrap">
                      {issue.labels.slice(0, 3).map((l) => (
                        <span
                          key={l}
                          className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[10px]"
                        >
                          {l}
                        </span>
                      ))}
                      {issue.labels.length > 3 && (
                        <span className="text-zinc-600 text-[10px]">
                          +{issue.labels.length - 3}
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

function StatePill({ state }: { state: IssueRow["state"] }) {
  const cls =
    state === "open"
      ? "bg-emerald-950/50 text-emerald-300"
      : "bg-zinc-800 text-zinc-500";
  return (
    <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide shrink-0", cls)}>
      {state}
    </span>
  );
}
