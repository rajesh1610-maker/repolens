"use client";

import { ExternalLink, Heart, MessageSquare, Lock } from "lucide-react";
import type { TriageIssue } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function TriageColumn({
  title,
  description,
  emptyMessage,
  items,
  accent,
}: {
  title: string;
  description: string;
  emptyMessage: string;
  items: TriageIssue[];
  accent: "amber" | "rose" | "zinc";
}) {
  const accentClass =
    accent === "amber"
      ? "border-amber-900/40"
      : accent === "rose"
        ? "border-rose-900/40"
        : "border-zinc-800";

  return (
    <div className={cn("rounded-lg border bg-zinc-950/40 flex flex-col min-h-[400px]", accentClass)}>
      <div className="px-4 py-3 border-b border-zinc-800/60">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">{title}</h3>
          <span className="text-[10px] text-zinc-500 tabular-nums">{items.length}</span>
        </div>
        <p className="text-[11px] text-zinc-500 mt-0.5">{description}</p>
      </div>
      <div className="flex-1 overflow-auto">
        {items.length === 0 ? (
          <div className="p-6 text-xs text-zinc-500 text-center">{emptyMessage}</div>
        ) : (
          <ul className="divide-y divide-zinc-800/60">
            {items.map((it) => (
              <TriageRow key={it.id} item={it} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TriageRow({ item }: { item: TriageIssue }) {
  return (
    <li className="p-3 hover:bg-zinc-900/50 transition-colors">
      <div className="flex items-start gap-2 mb-1">
        <span className="text-[10px] text-zinc-500 shrink-0">
          {item.repo_full_name}#{item.number}
        </span>
        {item.repo_visibility === "private" && (
          <Lock size={10} className="text-amber-300 shrink-0" />
        )}
      </div>
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer"
        className="text-xs font-medium text-zinc-200 hover:text-teal-300 line-clamp-2 inline-flex items-start gap-1 group"
      >
        <span>{item.title}</span>
        <ExternalLink size={10} className="opacity-0 group-hover:opacity-100 mt-0.5 shrink-0" />
      </a>
      <div className="flex items-center gap-2 text-[10px] text-zinc-500 mt-2 flex-wrap">
        <span title={item.updated_at ?? undefined}>{timeAgo(item.updated_at)}</span>
        {item.comments_count > 0 && (
          <span className="inline-flex items-center gap-0.5">
            <MessageSquare size={9} />
            {item.comments_count}
          </span>
        )}
        {item.reactions_total > 0 && (
          <span className="inline-flex items-center gap-0.5 text-amber-400">
            <Heart size={9} />
            {item.reactions_total}
          </span>
        )}
        {item.labels.slice(0, 2).map((l) => (
          <span key={l} className="px-1 py-0.5 rounded bg-zinc-800/80 text-zinc-400 text-[9px]">
            {l}
          </span>
        ))}
      </div>
    </li>
  );
}
