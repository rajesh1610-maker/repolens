"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Lock, Package } from "lucide-react";
import {
  api,
  ApiError,
  SYNC_EVENT,
  type ReleaseDraft,
  type ReleaseOverviewItem,
  type ReleasesOverviewResponse,
} from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ReleaseDraftPanel } from "@/components/releases/ReleaseDraftPanel";

export default function ReleasesPage() {
  const [overview, setOverview] = useState<ReleasesOverviewResponse | null>(null);
  const [selected, setSelected] = useState<ReleaseOverviewItem | null>(null);
  const [draft, setDraft] = useState<ReleaseDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [nextTagOverride, setNextTagOverride] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setError(null);
    try {
      const ov = await api<ReleasesOverviewResponse>("/api/releases");
      setOverview(ov);
      // Default-select the repo with the most unreleased PRs (already sorted)
      if (!selected && ov.items.length > 0) {
        setSelected(ov.items[0]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [selected]);

  const loadDraft = useCallback(async () => {
    if (!selected) {
      setDraft(null);
      return;
    }
    setDraftError(null);
    try {
      const params = new URLSearchParams();
      if (nextTagOverride) params.set("next_tag", nextTagOverride);
      const url = `/api/releases/${selected.owner}/${selected.name}/draft${
        params.toString() ? `?${params}` : ""
      }`;
      setDraft(await api<ReleaseDraft>(url));
    } catch (e) {
      setDraftError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [selected, nextTagOverride]);

  useEffect(() => {
    loadOverview();
    const handler = () => loadOverview();
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, [loadOverview]);

  useEffect(() => {
    loadDraft();
  }, [loadDraft]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold mb-1">Releases</h1>
        <p className="text-zinc-400 text-sm">
          Repos with merged PRs since their last release. Draft notes are
          generated from a deterministic template (Phase 8 will add an AI polish step).
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 mb-6 flex items-start gap-3 text-sm">
          <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div className="text-red-400/90">{error}</div>
        </div>
      )}

      {!overview && !error && (
        <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
          Loading…
        </div>
      )}

      {overview && overview.items.length === 0 && (
        <div className="rounded-lg border border-zinc-800 p-12 text-center">
          <Package size={32} className="mx-auto text-zinc-600 mb-3" />
          <div className="text-zinc-300 font-medium mb-1">No tracked repos</div>
          <p className="text-sm text-zinc-500">Run a sync from the sidebar to populate.</p>
        </div>
      )}

      {overview && overview.items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-6">
          {/* Repo list */}
          <ul className="rounded-lg border border-zinc-800 divide-y divide-zinc-800 overflow-hidden self-start">
            {overview.items.map((r) => {
              const active = selected?.repo_id === r.repo_id;
              return (
                <li
                  key={r.repo_id}
                  onClick={() => {
                    setSelected(r);
                    setNextTagOverride(null);
                  }}
                  className={cn(
                    "p-3 cursor-pointer transition-colors border-l-2",
                    active
                      ? "bg-zinc-900/70 border-l-teal-500"
                      : "border-l-transparent hover:bg-zinc-900/30"
                  )}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-xs font-medium truncate">{r.full_name}</span>
                    {r.visibility === "private" && (
                      <Lock size={10} className="text-amber-300 shrink-0" />
                    )}
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-zinc-500">
                    <span>
                      {r.latest_tag ? `${r.latest_tag} · ${timeAgo(r.latest_published_at)}` : "no releases"}
                    </span>
                    <span
                      className={cn(
                        "tabular-nums px-1.5 py-0.5 rounded text-[10px] font-medium",
                        r.unreleased_pr_count > 0
                          ? "bg-emerald-950/50 text-emerald-300"
                          : "bg-zinc-800 text-zinc-500"
                      )}
                    >
                      {r.unreleased_pr_count} PRs
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>

          {/* Draft */}
          <div>
            {draftError && (
              <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 mb-4 text-sm text-red-400/90">
                {draftError}
              </div>
            )}
            {selected && draft && (
              <ReleaseDraftPanel
                draft={draft}
                onTagChange={(t) => setNextTagOverride(t)}
              />
            )}
            {selected && !draft && !draftError && (
              <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
                Loading draft…
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
