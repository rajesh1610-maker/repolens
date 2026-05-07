"use client";

import { cn } from "@/lib/utils";

export type TabKey = "overview" | "pulls" | "issues" | "releases" | "contributors";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "pulls", label: "PRs" },
  { key: "issues", label: "Issues" },
  { key: "releases", label: "Releases" },
  { key: "contributors", label: "Contributors" },
];

export function Tabs({
  active,
  onChange,
  badges,
}: {
  active: TabKey;
  onChange: (k: TabKey) => void;
  badges?: Partial<Record<TabKey, number>>;
}) {
  return (
    <div className="border-b border-zinc-800 mb-6">
      <nav className="flex gap-1" aria-label="Tabs">
        {TABS.map(({ key, label }) => {
          const count = badges?.[key];
          const isActive = active === key;
          return (
            <button
              key={key}
              onClick={() => onChange(key)}
              className={cn(
                "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-2",
                isActive
                  ? "border-teal-500 text-white"
                  : "border-transparent text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
              )}
            >
              {label}
              {count !== undefined && count > 0 && (
                <span
                  className={cn(
                    "px-1.5 py-0.5 rounded text-[10px] font-medium",
                    isActive ? "bg-zinc-800 text-zinc-300" : "bg-zinc-800/50 text-zinc-500"
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
