"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, Inbox } from "lucide-react";
import {
  api,
  ApiError,
  SYNC_EVENT,
  type InboxResponse,
  type InboxRow as InboxRowType,
} from "@/lib/api";
import { InboxFilters, type InboxKindFilter } from "@/components/inbox/InboxFilters";
import { InboxRowItem } from "@/components/inbox/InboxRow";
import { useHotkeys } from "@/hooks/useHotkeys";

const PAGE_SIZE = 50;

export default function InboxPage() {
  const [data, setData] = useState<InboxResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<InboxKindFilter>("all");
  const [hideDrafts, setHideDrafts] = useState(false);
  const [hasReactions, setHasReactions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const rowRefs = useRef<(HTMLLIElement | null)[]>([]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams({
        kind,
        hide_drafts: String(hideDrafts),
        has_reactions: String(hasReactions),
        limit: String(PAGE_SIZE),
      });
      const r = await api<InboxResponse>(`/api/inbox?${params}`);
      setData(r);
      setSelectedIndex((i) => Math.min(i, Math.max(0, r.items.length - 1)));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [kind, hideDrafts, hasReactions]);

  useEffect(() => {
    refresh();
    const handler = () => refresh();
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, [refresh]);

  // Hotkeys: j/k to move, o to open externally
  useHotkeys(
    {
      j: (e) => {
        if (!data || data.items.length === 0) return;
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, data.items.length - 1));
      },
      k: (e) => {
        if (!data || data.items.length === 0) return;
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      },
      o: (e) => {
        const row = data?.items[selectedIndex];
        if (!row) return;
        e.preventDefault();
        window.open(row.url, "_blank", "noopener,noreferrer");
      },
    },
    [data, selectedIndex],
  );

  // Scroll selection into view on hotkey nav
  useEffect(() => {
    const el = rowRefs.current[selectedIndex];
    if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedIndex]);

  return (
    <div className="max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold mb-1">Inbox</h1>
        <p className="text-zinc-400 text-sm">
          Open PRs and issues across your tracked repos, ranked by priority and freshness.{" "}
          <span className="text-zinc-600">
            Hotkeys: <kbd className="kbd">j</kbd>/<kbd className="kbd">k</kbd> move ·{" "}
            <kbd className="kbd">o</kbd> open · <kbd className="kbd">?</kbd> all
          </span>
        </p>
      </div>

      <InboxFilters
        kind={kind}
        onKindChange={setKind}
        hideDrafts={hideDrafts}
        onHideDraftsChange={setHideDrafts}
        hasReactions={hasReactions}
        onHasReactionsChange={setHasReactions}
        facets={data?.facets ?? null}
      />

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 mb-6 flex items-start gap-3 text-sm">
          <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div className="text-red-400/90">{error}</div>
        </div>
      )}

      {!data && !error && <SkeletonList />}

      {data && data.items.length === 0 && (
        <EmptyState totalUnfiltered={data.facets.all} hasFilters={
          kind !== "all" || hideDrafts || hasReactions
        } />
      )}

      {data && data.items.length > 0 && (
        <>
          <ul className="rounded-lg border border-zinc-800 divide-y divide-zinc-800 overflow-hidden">
            {data.items.map((row, idx) => (
              <InboxRowItem
                key={row.id}
                ref={(el) => {
                  rowRefs.current[idx] = el;
                }}
                row={row}
                selected={idx === selectedIndex}
                onSelect={() => setSelectedIndex(idx)}
              />
            ))}
          </ul>
          {data.total > data.items.length && (
            <div className="text-xs text-zinc-500 mt-3">
              Showing {data.items.length} of {data.total}. Pagination beyond {PAGE_SIZE} arrives in a later phase.
            </div>
          )}
        </>
      )}
    </div>
  );
}

function EmptyState({
  totalUnfiltered,
  hasFilters,
}: {
  totalUnfiltered: number;
  hasFilters: boolean;
}) {
  if (hasFilters) {
    return (
      <div className="rounded-lg border border-zinc-800 p-12 text-center">
        <Inbox size={32} className="mx-auto text-zinc-600 mb-3" />
        <div className="text-zinc-300 font-medium mb-1">No items match this filter</div>
        <p className="text-sm text-zinc-500">
          Try widening your filters above.
        </p>
      </div>
    );
  }

  if (totalUnfiltered === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 p-12 text-center">
        <Inbox size={32} className="mx-auto text-zinc-600 mb-3" />
        <div className="text-zinc-300 font-medium mb-1">Inbox zero</div>
        <p className="text-sm text-zinc-500 max-w-md mx-auto">
          No open PRs or issues across your tracked repos. Run a sync from the sidebar
          to refresh, or check <Link href="/settings" className="text-teal-400 hover:underline">Settings</Link>{" "}
          to make sure repos are tracked.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 p-12 text-center text-sm text-zinc-500">
      Inbox empty for the current filter.
    </div>
  );
}

function SkeletonList() {
  return (
    <div className="rounded-lg border border-zinc-800 divide-y divide-zinc-800">
      {[1, 2, 3].map((i) => (
        <div key={i} className="px-4 py-4 animate-pulse">
          <div className="h-2 bg-zinc-800 rounded w-1/3 mb-2" />
          <div className="h-2 bg-zinc-800 rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}
