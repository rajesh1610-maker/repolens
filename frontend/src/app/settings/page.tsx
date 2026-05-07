"use client";

import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, Github, Lock, Trash2, Check, AlertCircle, Lock as LockIcon, RefreshCw } from "lucide-react";
import { api, ApiError, type SettingsOverview, type RepoSummary, type RecentRunsResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SyncRunsTable } from "@/components/settings/SyncRunsTable";

export default function SettingsPage() {
  const [overview, setOverview] = useState<SettingsOverview | null>(null);
  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [recentRuns, setRecentRuns] = useState<RecentRunsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [patInput, setPatInput] = useState("");
  const [showPat, setShowPat] = useState(false);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [o, r, runs] = await Promise.all([
        api<SettingsOverview>("/api/settings"),
        api<RepoSummary[]>("/api/repos?include_untracked=true"),
        api<RecentRunsResponse>("/api/sync/runs?limit=10"),
      ]);
      setOverview(o);
      setRepos(r);
      setRecentRuns(runs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const savePat = async () => {
    if (!patInput.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api("/api/settings/pat", {
        method: "POST",
        body: JSON.stringify({ pat: patInput.trim() }),
      });
      setPatInput("");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setSaving(false);
    }
  };

  const deletePat = async () => {
    if (!confirm("Remove the saved PAT? RepoLens will fall back to GITHUB_PAT in .env (if set).")) return;
    try {
      await api("/api/settings/pat", { method: "DELETE" });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  };

  const togglePublicOnly = async () => {
    if (!overview) return;
    try {
      await api("/api/settings", {
        method: "PATCH",
        body: JSON.stringify({ public_only_mode: !overview.user.public_only_mode }),
      });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  };

  const toggleTracked = async (repo: RepoSummary) => {
    const action = repo.tracked ? "untrack" : "track";
    try {
      await api(`/api/repos/${repo.id}/${action}`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  };

  if (loading) {
    return <div className="text-zinc-400">Loading settings…</div>;
  }

  // Compute visible count from repos[] so it correctly intersects
  // tracked AND visibility (the API counts are unconditional).
  const publicOnly = overview?.user.public_only_mode ?? false;
  const visibleCount = repos.filter(
    (r) => r.tracked && (!publicOnly || r.visibility === "public")
  ).length;
  const hiddenPrivateCount = publicOnly
    ? repos.filter((r) => r.tracked && r.visibility === "private").length
    : 0;

  return (
    <div className="max-w-3xl space-y-10">
      <div>
        <h1 className="text-2xl font-semibold mb-1">Settings</h1>
        <p className="text-zinc-400 text-sm">
          Configure GitHub access, visibility, and which repos RepoLens tracks.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 flex items-start gap-3 text-sm">
          <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div>
            <div className="text-red-300 font-medium">Error</div>
            <div className="text-red-400/80">{error}</div>
          </div>
        </div>
      )}

      {/* GitHub connection */}
      <section className="rounded-lg border border-zinc-800 p-6">
        <div className="flex items-center gap-2 mb-1">
          <Github size={16} />
          <h2 className="text-base font-semibold">GitHub connection</h2>
        </div>
        <p className="text-zinc-500 text-xs mb-4">
          Required scopes: <code className="text-zinc-300">repo</code> +{" "}
          <code className="text-zinc-300">read:org</code>. The PAT is encrypted with AES-GCM
          before being stored.
        </p>

        {overview?.user.configured ? (
          <div className="flex items-center gap-3 mb-4 p-3 rounded-md bg-zinc-900">
            {overview.user.avatar_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={overview.user.avatar_url} alt="" className="w-10 h-10 rounded-full" />
            )}
            <div className="flex-1">
              <div className="text-sm font-medium">{overview.user.github_login}</div>
              <div className="text-xs text-zinc-400 flex items-center gap-2">
                {overview.user.has_pat ? (
                  <>
                    <Lock size={12} className="text-teal-400" />
                    <span className="text-teal-400">PAT saved (encrypted)</span>
                  </>
                ) : (
                  <span className="text-amber-400">Using GITHUB_PAT env fallback</span>
                )}
              </div>
            </div>
            {overview.user.has_pat && (
              <button
                onClick={deletePat}
                className="text-xs text-zinc-400 hover:text-red-400 flex items-center gap-1"
              >
                <Trash2 size={12} />
                Disconnect
              </button>
            )}
          </div>
        ) : (
          <div className="text-sm text-amber-400 mb-4">
            Not connected. Save a PAT below or set <code>GITHUB_PAT</code> in <code>backend/.env</code>.
          </div>
        )}

        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type={showPat ? "text" : "password"}
              value={patInput}
              onChange={(e) => setPatInput(e.target.value)}
              placeholder={overview?.user.has_pat ? "Replace existing PAT…" : "ghp_…"}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm pr-10 focus:outline-none focus:border-teal-600"
            />
            <button
              type="button"
              onClick={() => setShowPat((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
            >
              {showPat ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          <button
            onClick={savePat}
            disabled={saving || !patInput.trim()}
            className={cn(
              "px-4 py-2 rounded-md text-sm font-medium transition-colors",
              saving || !patInput.trim()
                ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                : "bg-teal-700 hover:bg-teal-600 text-white"
            )}
          >
            {saving ? "Validating…" : "Save"}
          </button>
        </div>
      </section>

      {/* Visibility */}
      <section className="rounded-lg border border-zinc-800 p-6">
        <div className="flex items-center gap-2 mb-1">
          <LockIcon size={16} />
          <h2 className="text-base font-semibold">Visibility</h2>
        </div>
        <p className="text-zinc-500 text-xs mb-4">
          Public-only mode hides every private repo from the Inbox, Repos wall, Triage, Releases,
          and Digest. Useful for screenshots, demos, and screen-shares. Toggling is instant —
          no re-sync, no data loss.
        </p>

        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Public-only mode</div>
            {overview && (
              <div className="text-xs text-zinc-400 mt-1">
                Currently visible: {visibleCount} repo{visibleCount === 1 ? "" : "s"}
                {hiddenPrivateCount > 0 && (
                  <span className="text-amber-400">
                    {" "}({hiddenPrivateCount} private hidden)
                  </span>
                )}
              </div>
            )}
          </div>
          <button
            onClick={togglePublicOnly}
            disabled={!overview?.user.configured}
            className={cn(
              "relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0",
              !overview?.user.configured && "opacity-40 cursor-not-allowed",
              overview?.user.public_only_mode ? "bg-teal-600" : "bg-zinc-700"
            )}
          >
            <span
              className={cn(
                "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
                overview?.user.public_only_mode ? "translate-x-6" : "translate-x-1"
              )}
            />
          </button>
        </div>
      </section>

      {/* Sync */}
      <section className="rounded-lg border border-zinc-800 p-6">
        <div className="flex items-center gap-2 mb-1">
          <RefreshCw size={16} />
          <h2 className="text-base font-semibold">Sync</h2>
        </div>
        <p className="text-zinc-500 text-xs mb-4">
          {overview?.scheduler.enabled ? (
            <>
              Background sync runs every <span className="text-zinc-300">{overview.scheduler.interval_minutes} min</span>.
              Stale runs older than <span className="text-zinc-300">{overview.scheduler.watchdog_minutes} min</span> are
              auto-marked failed by the watchdog.
            </>
          ) : (
            <>
              Background scheduler is <span className="text-amber-400">disabled</span>.
              Set <code className="text-zinc-300">REPOLENS_SCHEDULER_ENABLED=true</code> in <code>backend/.env</code>{" "}
              to enable. Manual sync via the sidebar always works.
            </>
          )}
        </p>
        {recentRuns && <SyncRunsTable runs={recentRuns.items} />}
      </section>

      {/* Tracked repos */}
      <section className="rounded-lg border border-zinc-800 p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-base font-semibold">Tracked repos</h2>
          {overview && (
            <span className="text-xs text-zinc-500">
              {overview.repos.tracked} / {overview.repos.total} tracked
            </span>
          )}
        </div>
        <p className="text-zinc-500 text-xs mb-4">
          Uncheck a repo to exclude it from sync, Inbox, the wall, and the digest.
          Untracked repos keep their existing data but stop receiving updates.
        </p>

        {repos.length === 0 ? (
          <div className="text-sm text-zinc-500 italic">
            No repos synced yet. Run <code>uv run repolens sync-repos</code> in the backend folder.
          </div>
        ) : (
          <ul className="divide-y divide-zinc-800">
            {repos.map((r) => (
              <li key={r.id} className="flex items-center gap-3 py-3">
                <input
                  type="checkbox"
                  checked={r.tracked}
                  onChange={() => toggleTracked(r)}
                  className="w-4 h-4 accent-teal-600 cursor-pointer"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{r.full_name}</div>
                  <div className="text-xs text-zinc-500 flex items-center gap-2 mt-0.5">
                    <span
                      className={cn(
                        "px-1.5 py-0.5 rounded text-[10px] font-medium",
                        r.visibility === "private"
                          ? "bg-amber-950/50 text-amber-300"
                          : "bg-zinc-800 text-zinc-400"
                      )}
                    >
                      {r.visibility}
                    </span>
                    <span>{r.stars}★</span>
                    <span>{r.open_issues_count} issues</span>
                  </div>
                </div>
                {r.tracked && <Check size={14} className="text-teal-500 shrink-0" />}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
