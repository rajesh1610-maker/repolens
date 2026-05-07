"use client";

import { cn } from "@/lib/utils";
import type { InboxResponse } from "@/lib/api";

export type InboxKindFilter = "all" | "pr" | "issue";

export function InboxFilters({
  kind,
  onKindChange,
  hideDrafts,
  onHideDraftsChange,
  hasReactions,
  onHasReactionsChange,
  facets,
}: {
  kind: InboxKindFilter;
  onKindChange: (k: InboxKindFilter) => void;
  hideDrafts: boolean;
  onHideDraftsChange: (v: boolean) => void;
  hasReactions: boolean;
  onHasReactionsChange: (v: boolean) => void;
  facets: InboxResponse["facets"] | null;
}) {
  const KINDS: { key: InboxKindFilter; label: string; count: keyof InboxResponse["facets"] | null }[] = [
    { key: "all", label: "All", count: "all" },
    { key: "pr", label: "PRs", count: "pr" },
    { key: "issue", label: "Issues", count: "issue" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2 mb-6">
      <div className="flex gap-1">
        {KINDS.map((k) => {
          const active = kind === k.key;
          const count = facets && k.count ? facets[k.count] : null;
          return (
            <button
              key={k.key}
              onClick={() => onKindChange(k.key)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center gap-2",
                active
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              {k.label}
              {count !== null && (
                <span
                  className={cn(
                    "px-1.5 rounded text-[10px] font-medium",
                    active ? "bg-zinc-900 text-zinc-300" : "bg-zinc-800/50 text-zinc-500"
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="ml-auto flex gap-2 text-xs">
        <ToggleChip
          active={hideDrafts}
          onClick={() => onHideDraftsChange(!hideDrafts)}
          label="Hide drafts"
        />
        <ToggleChip
          active={hasReactions}
          onClick={() => onHasReactionsChange(!hasReactions)}
          label={`Has reactions${facets ? ` · ${facets.with_reactions}` : ""}`}
        />
      </div>
    </div>
  );
}

function ToggleChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-3 py-1.5 rounded-md font-medium border transition-colors",
        active
          ? "border-teal-700 bg-teal-950/40 text-teal-300"
          : "border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
      )}
    >
      {label}
    </button>
  );
}
