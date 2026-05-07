import { Star, GitFork, GitBranch, Lock } from "lucide-react";
import type { RepoSummary, TrafficResponse } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Sparkline } from "@/components/charts/Sparkline";
import { TrafficChart } from "@/components/charts/TrafficChart";

export function OverviewPanel({
  repo,
  traffic,
}: {
  repo: RepoSummary;
  traffic: TrafficResponse | null;
}) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Stars" value={repo.stars} icon={<Star size={14} />} />
        <StatCard label="Forks" value={repo.forks} icon={<GitFork size={14} />} />
        <StatCard label="Open PRs" value={repo.open_pulls_count} />
        <StatCard label="Open issues" value={repo.open_issues_real_count} />
      </div>

      {/* Traffic chart (28-day) */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold">Traffic — last 28 days</h3>
          {traffic && (
            <div className="text-xs text-zinc-500 tabular-nums">
              {traffic.totals.views} views · {traffic.totals.unique_views_max} peak unique
            </div>
          )}
        </div>
        <TrafficChart
          series={traffic?.series ?? []}
          className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"
        />
      </div>

      {/* Stars history (30-day sparkline) */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold">Stars — last 30 days</h3>
          <div className="text-xs text-zinc-500">
            current: <span className="text-zinc-300 tabular-nums">{repo.stars}</span>
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
          <Sparkline
            data={repo.stars_30d ?? []}
            width={680}
            height={56}
            className="text-teal-400 w-full"
          />
        </div>
      </div>

      {repo.description && (
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wide mb-2">Description</div>
          <p className="text-sm text-zinc-200">{repo.description}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        <Field label="Visibility">
          <span className="inline-flex items-center gap-1.5">
            {repo.visibility === "private" && <Lock size={12} className="text-amber-300" />}
            <span className={repo.visibility === "private" ? "text-amber-300" : "text-zinc-300"}>
              {repo.visibility}
            </span>
          </span>
        </Field>
        <Field label="Default branch">
          <span className="inline-flex items-center gap-1.5 text-zinc-300">
            <GitBranch size={12} />
            {repo.default_branch ?? "—"}
          </span>
        </Field>
        <Field label="Last pushed">
          <span className="text-zinc-300" title={repo.pushed_at ?? undefined}>
            {timeAgo(repo.pushed_at)}
          </span>
        </Field>
        <Field label="Merged PRs (last 30d)">
          <span className="text-zinc-300">{repo.merged_pulls_30d}</span>
        </Field>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: number | string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 px-4 py-3">
      <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1">
        {icon}
        {label}
      </div>
      <div className="text-xl font-semibold">{value}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">{label}</div>
      <div>{children}</div>
    </div>
  );
}
