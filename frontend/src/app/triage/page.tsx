"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { api, ApiError, SYNC_EVENT, type TriageResponse } from "@/lib/api";
import { TriageColumn } from "@/components/triage/TriageColumn";

export default function TriagePage() {
  const [data, setData] = useState<TriageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setData(await api<TriageResponse>("/api/triage"));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const handler = () => refresh();
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, [refresh]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold mb-1">Triage</h1>
        <p className="text-zinc-400 text-sm">
          Three views on open issues you might want to revisit. An issue can
          appear in more than one column — that&apos;s information, not duplication.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 mb-6 flex items-start gap-3 text-sm">
          <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div className="text-red-400/90">{error}</div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <TriageColumn
          title="Stale"
          description="Open >60 days, no recent activity"
          emptyMessage="Nothing stale."
          items={data?.stale ?? []}
          accent="zinc"
        />
        <TriageColumn
          title="Hot"
          description="Open issues with reactions, ranked by popularity"
          emptyMessage="No reactions on any open issue."
          items={data?.hot ?? []}
          accent="rose"
        />
        <TriageColumn
          title="Stuck"
          description="Labeled needs-info / awaiting-response / blocked, idle >14 days"
          emptyMessage="Nothing stuck."
          items={data?.stuck ?? []}
          accent="amber"
        />
      </div>
    </div>
  );
}
