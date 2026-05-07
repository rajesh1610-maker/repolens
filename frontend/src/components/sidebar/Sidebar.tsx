"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
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
import { api, ApiError, type LastSyncResponse, type SettingsOverview, SYNC_EVENT } from "@/lib/api";
import { timeAgo } from "@/lib/format";

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
  const [lastSync, setLastSync] = useState<LastSyncResponse | null>(null);
  const [overview, setOverview] = useState<SettingsOverview | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, o] = await Promise.all([
        api<LastSyncResponse>("/api/sync/last"),
        api<SettingsOverview>("/api/settings"),
      ]);
      setLastSync(s);
      setOverview(o);
    } catch {
      // sidebar shouldn't block — just leave stale state
    }
  }, []);

  useEffect(() => {
    refresh();
    const handler = () => refresh();
    window.addEventListener(SYNC_EVENT, handler);
    const interval = setInterval(refresh, 30_000);
    return () => {
      window.removeEventListener(SYNC_EVENT, handler);
      clearInterval(interval);
    };
  }, [refresh]);

  const triggerSync = async () => {
    setSyncing(true);
    setSyncError(null);
    try {
      await api("/api/sync", { method: "POST" });
      await refresh();
      window.dispatchEvent(new CustomEvent(SYNC_EVENT));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setSyncError("Already running…");
      } else {
        setSyncError(e instanceof ApiError ? e.detail : String(e));
      }
    } finally {
      setSyncing(false);
    }
  };

  const lastRun = lastSync?.last_run;
  const canSync = !!overview?.user.configured || !!overview?.user.has_pat;
  const lastTime = lastRun?.finished_at ?? lastRun?.started_at ?? null;

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
        <div className="flex items-center justify-between">
          <span>Last sync:</span>
          <span
            className={cn(
              "font-medium",
              lastRun?.status === "failed" ? "text-red-400" : "text-zinc-300"
            )}
            title={lastTime ?? undefined}
          >
            {timeAgo(lastTime)}
          </span>
        </div>
        {lastRun?.rate_limit_remaining !== null && lastRun?.rate_limit_remaining !== undefined && (
          <div className="flex items-center justify-between text-zinc-600">
            <span>Rate limit:</span>
            <span>{lastRun.rate_limit_remaining}/5000</span>
          </div>
        )}
        <button
          onClick={triggerSync}
          disabled={!canSync || syncing}
          className={cn(
            "w-full flex items-center justify-center gap-2 py-2 rounded-md transition-colors",
            !canSync
              ? "bg-zinc-800/40 text-zinc-500 cursor-not-allowed"
              : syncing
                ? "bg-zinc-800 text-zinc-400 cursor-wait"
                : "bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
          )}
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : undefined} />
          {syncing ? "Syncing…" : "Sync now"}
        </button>
        {syncError && (
          <div className="text-[10px] text-red-400 break-words">{syncError}</div>
        )}
        <div className="text-[10px] text-zinc-600 pt-1">v0.1.0 · phase 3</div>
      </div>
    </aside>
  );
}
