"use client";

import type { SyncRunSummary } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function SyncRunsTable({ runs }: { runs: SyncRunSummary[] }) {
  if (runs.length === 0) {
    return (
      <div className="text-sm text-zinc-500 italic">No sync runs yet.</div>
    );
  }

  return (
    <div className="rounded-md border border-zinc-800 overflow-hidden">
      <table className="w-full text-xs">
        <thead className="bg-zinc-900/50 text-zinc-500 uppercase tracking-wide">
          <tr>
            <th className="text-left px-3 py-2 font-medium">When</th>
            <th className="text-left px-3 py-2 font-medium">Status</th>
            <th className="text-right px-3 py-2 font-medium">Duration</th>
            <th className="text-right px-3 py-2 font-medium">Repos</th>
            <th className="text-right px-3 py-2 font-medium">PRs</th>
            <th className="text-right px-3 py-2 font-medium">Issues</th>
            <th className="text-right px-3 py-2 font-medium">API</th>
            <th className="text-right px-3 py-2 font-medium">Rate left</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {runs.map((r) => (
            <tr key={r.id} className="hover:bg-zinc-900/30">
              <td className="px-3 py-2 text-zinc-300" title={r.started_at ?? undefined}>
                {timeAgo(r.started_at)}
              </td>
              <td className="px-3 py-2">
                <StatusPill status={r.status} error={r.error} />
              </td>
              <td className="px-3 py-2 text-right text-zinc-400 tabular-nums">
                {r.duration_ms !== null ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}
              </td>
              <td className="px-3 py-2 text-right text-zinc-300 tabular-nums">{r.repos_synced}</td>
              <td className="px-3 py-2 text-right text-zinc-300 tabular-nums">{r.pulls_synced}</td>
              <td className="px-3 py-2 text-right text-zinc-300 tabular-nums">{r.issues_synced}</td>
              <td className="px-3 py-2 text-right text-zinc-400 tabular-nums">{r.api_calls}</td>
              <td className="px-3 py-2 text-right text-zinc-400 tabular-nums">
                {r.rate_limit_remaining ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({
  status,
  error,
}: {
  status: SyncRunSummary["status"];
  error: string | null;
}) {
  const cls =
    status === "ok"
      ? "bg-emerald-950/50 text-emerald-300"
      : status === "failed"
        ? "bg-red-950/50 text-red-300"
        : "bg-zinc-800 text-zinc-400";
  return (
    <span
      className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide", cls)}
      title={error ?? undefined}
    >
      {status}
    </span>
  );
}
