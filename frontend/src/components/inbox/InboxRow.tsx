"use client";

import { ExternalLink, GitPullRequest, CircleDot, MessageSquare, Heart, Lock } from "lucide-react";
import { forwardRef, type Ref } from "react";
import type { InboxRow as InboxRowType } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

type Props = {
  row: InboxRowType;
  selected: boolean;
  onSelect: () => void;
};

export const InboxRowItem = forwardRef(function InboxRowItem(
  { row, selected, onSelect }: Props,
  ref: Ref<HTMLLIElement>,
) {
  const Icon = row.kind === "pr" ? GitPullRequest : CircleDot;
  const score = row.total_score;

  return (
    <li
      ref={ref}
      onClick={onSelect}
      className={cn(
        "group cursor-pointer border-l-2 transition-colors",
        selected
          ? "bg-zinc-900/70 border-l-teal-500"
          : "bg-transparent border-l-transparent hover:bg-zinc-900/30"
      )}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <Icon
          size={14}
          className={cn(
            "shrink-0",
            row.kind === "pr"
              ? row.draft
                ? "text-zinc-500"
                : "text-emerald-400"
              : "text-emerald-400"
          )}
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[11px] text-zinc-500 shrink-0">
              {row.repo_full_name}#{row.number}
            </span>
            {row.repo_visibility === "private" && (
              <Lock size={10} className="text-amber-300 shrink-0" />
            )}
            <a
              href={row.url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-sm font-medium truncate hover:text-teal-300 inline-flex items-center gap-1"
            >
              <span className="truncate">{row.title}</span>
              <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 shrink-0" />
            </a>
            {row.draft && (
              <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[10px] uppercase tracking-wide shrink-0">
                draft
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-zinc-500">
            <span>{row.author_login ?? "unknown"}</span>
            <span title={row.last_activity_at ?? undefined}>
              {timeAgo(row.last_activity_at)}
            </span>
            {row.comments_count > 0 && (
              <span className="inline-flex items-center gap-1">
                <MessageSquare size={10} />
                {row.comments_count}
              </span>
            )}
            {row.reactions_total > 0 && (
              <span className="inline-flex items-center gap-1 text-amber-400">
                <Heart size={10} />
                {row.reactions_total}
              </span>
            )}
            {row.labels.slice(0, 2).map((l) => (
              <span
                key={l}
                className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[10px]"
              >
                {l}
              </span>
            ))}
            {row.labels.length > 2 && (
              <span className="text-zinc-600 text-[10px]">+{row.labels.length - 2}</span>
            )}
          </div>
        </div>

        <span
          className={cn(
            "tabular-nums text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0",
            score > 5
              ? "bg-emerald-950/50 text-emerald-300"
              : score < -10
                ? "bg-zinc-800 text-zinc-500"
                : "bg-zinc-800/60 text-zinc-400"
          )}
          title={`Static: ${row.priority_score_static.toFixed(2)} · Total: ${score.toFixed(2)}`}
        >
          {score > 0 ? `+${score.toFixed(0)}` : score.toFixed(0)}
        </span>
      </div>
    </li>
  );
});
