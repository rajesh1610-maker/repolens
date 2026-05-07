"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Copy,
  Check,
  Sparkles,
  Loader2,
  RefreshCw,
} from "lucide-react";
import {
  api,
  ApiError,
  type DigestSummary,
  type DigestLatestResponse,
  type DigestListResponse,
  type DigestGenerateResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/format";
import { DigestMarkdown } from "@/components/digest/DigestMarkdown";

export default function DigestPage() {
  const [latest, setLatest] = useState<DigestSummary | null>(null);
  const [history, setHistory] = useState<DigestSummary[]>([]);
  const [selected, setSelected] = useState<DigestSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [l, h] = await Promise.all([
        api<DigestLatestResponse>("/api/digests/latest"),
        api<DigestListResponse>("/api/digests?limit=20"),
      ]);
      setLatest(l.digest);
      setHistory(h.items);
      // Default selection: latest. If user already had one selected,
      // keep it (e.g. they clicked an older one before regenerate hit).
      setSelected((prev) => {
        if (prev && h.items.some((d) => d.id === prev.id)) return prev;
        return l.digest;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await api<DigestGenerateResponse>("/api/digests/generate", {
        method: "POST",
        body: JSON.stringify({}),
      });
      // Optimistic select on the freshly generated row.
      setSelected(res.digest);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setGenerating(false);
    }
  };

  const copyMd = async () => {
    if (!selected) return;
    try {
      await navigator.clipboard.writeText(selected.body_md);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard might be blocked */
    }
  };

  if (loading) {
    return <div className="text-zinc-400">Loading digests…</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={18} className="text-teal-400" />
            <h1 className="text-2xl font-semibold">Weekly digest</h1>
          </div>
          <p className="text-zinc-400 text-sm">
            Claude reads the last 7 days of activity in your tracked repos and
            writes a single narrative summary. Generates automatically Sun 22:00 UTC
            when the scheduler is on.
          </p>
        </div>
        <button
          onClick={generate}
          disabled={generating}
          className={cn(
            "px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-2 shrink-0",
            generating
              ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
              : "bg-teal-700 hover:bg-teal-600 text-white"
          )}
        >
          {generating ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Generating…
            </>
          ) : (
            <>
              <RefreshCw size={14} />
              {latest ? "Regenerate this week" : "Generate digest"}
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 flex items-start gap-3 text-sm">
          <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div>
            <div className="text-red-300 font-medium">Could not generate digest</div>
            <div className="text-red-400/80 break-words">{error}</div>
          </div>
        </div>
      )}

      {!selected ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-[1fr_240px] gap-6">
          <div className="space-y-5">
            <DigestMeta digest={selected} onCopy={copyMd} copied={copied} />
            {selected.validation_warnings.length > 0 && (
              <Warnings items={selected.validation_warnings} />
            )}
            <article className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-6">
              <DigestMarkdown source={selected.body_md} />
            </article>
          </div>

          <aside className="space-y-3">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500">
              History
            </div>
            {history.length === 0 ? (
              <div className="text-xs text-zinc-500 italic">No past digests.</div>
            ) : (
              <ul className="space-y-1.5">
                {history.map((d) => {
                  const isSelected = selected.id === d.id;
                  return (
                    <li key={d.id}>
                      <button
                        onClick={() => setSelected(d)}
                        className={cn(
                          "w-full text-left px-3 py-2 rounded-md text-xs border transition-colors",
                          isSelected
                            ? "border-teal-700 bg-teal-950/30 text-teal-200"
                            : "border-zinc-800 hover:border-zinc-700 text-zinc-300"
                        )}
                      >
                        <div className="font-medium">
                          {formatPeriod(d.period_start, d.period_end)}
                        </div>
                        <div className="text-zinc-500 mt-0.5">
                          {timeAgo(d.generated_at)} · ${d.cost_usd.toFixed(3)}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-zinc-800 p-10 text-center">
      <Sparkles size={28} className="mx-auto text-zinc-600 mb-3" />
      <div className="text-sm text-zinc-300 mb-1">No digest yet</div>
      <div className="text-xs text-zinc-500 max-w-md mx-auto">
        Click <span className="text-zinc-300">Generate digest</span> to summarize
        the most recent completed week (Mon-Sun). Configure an Anthropic API key
        in Settings first.
      </div>
    </div>
  );
}

function DigestMeta({
  digest,
  onCopy,
  copied,
}: {
  digest: DigestSummary;
  onCopy: () => void;
  copied: boolean;
}) {
  const totals = digest.input_summary.totals ?? {};
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="text-xs text-zinc-500">Week of</div>
          <div className="text-base font-semibold text-zinc-100">
            {formatPeriod(digest.period_start, digest.period_end)}
          </div>
          <div className="text-xs text-zinc-500 mt-1">
            Generated {timeAgo(digest.generated_at)} · {digest.model}
          </div>
        </div>
        <button
          onClick={onCopy}
          className={cn(
            "px-3 py-1.5 rounded-md text-xs font-medium border transition-colors flex items-center gap-1.5",
            copied
              ? "border-teal-700 bg-teal-950/40 text-teal-300"
              : "border-zinc-700 text-zinc-300 hover:border-zinc-500"
          )}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "Copied" : "Copy markdown"}
        </button>
      </div>

      <div className="grid grid-cols-4 gap-3 text-xs">
        <Stat label="Merged PRs" value={totals.merged_prs ?? 0} />
        <Stat label="New issues" value={totals.opened_issues ?? 0} />
        <Stat label="Releases" value={totals.releases ?? 0} />
        <Stat label="Stars" value={signed(totals.stars_delta ?? 0)} />
      </div>

      <div className="mt-4 pt-4 border-t border-zinc-900 flex items-center justify-between text-[11px] text-zinc-500">
        <div className="flex gap-4">
          <span>
            <span className="text-zinc-400">{digest.tokens_in.toLocaleString()}</span> in
          </span>
          <span>
            <span className="text-zinc-400">{digest.tokens_out.toLocaleString()}</span> out
          </span>
          {digest.cache_read_input_tokens > 0 && (
            <span>
              <span className="text-zinc-400">
                {digest.cache_read_input_tokens.toLocaleString()}
              </span>{" "}
              cached
            </span>
          )}
        </div>
        <div>
          <span className="text-zinc-400 font-mono">
            ${digest.cost_usd.toFixed(4)}
          </span>{" "}
          · stop: {digest.stop_reason ?? "—"}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md bg-zinc-900/60 border border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="text-base font-semibold text-zinc-100 mt-0.5">{value}</div>
    </div>
  );
}

function Warnings({ items }: { items: string[] }) {
  return (
    <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-4">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle size={14} className="text-amber-400" />
        <div className="text-xs font-medium text-amber-300">
          Validation noticed
        </div>
      </div>
      <ul className="text-xs text-amber-200/80 space-y-1 pl-5 list-disc marker:text-amber-700">
        {items.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </div>
  );
}

function formatPeriod(start: string, end: string) {
  const s = new Date(start);
  const e = new Date(end);
  const fmt = (d: Date) =>
    d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `${fmt(s)} – ${fmt(e)}, ${e.getFullYear()}`;
}

function signed(n: number): string {
  if (n === 0) return "0";
  return n > 0 ? `+${n}` : String(n);
}
