"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Inbox,
  LayoutGrid,
  Target,
  Package,
  Sparkles,
  Settings,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Inbox", icon: Inbox },
  { href: "/repos", label: "Repos", icon: LayoutGrid },
  { href: "/triage", label: "Triage", icon: Target },
  { href: "/releases", label: "Releases", icon: Package },
  { href: "/digest", label: "Digest", icon: Sparkles },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-60 shrink-0 border-r border-zinc-800 p-4 flex flex-col">
      <div className="text-lg font-semibold mb-6 px-2 flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-teal-500" />
        RepoLens
      </div>
      <nav className="flex-1 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                active
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto pt-4 border-t border-zinc-800 text-xs text-zinc-500 space-y-2">
        <div>
          Last sync: <span className="text-zinc-400">never</span>
        </div>
        <button
          disabled
          className="w-full flex items-center justify-center gap-2 py-2 rounded-md bg-zinc-800/40 text-zinc-500 cursor-not-allowed"
        >
          <RefreshCw size={14} />
          Sync now
        </button>
        <div className="text-[10px] text-zinc-600 pt-1">v0.1.0 · phase 0</div>
      </div>
    </aside>
  );
}
