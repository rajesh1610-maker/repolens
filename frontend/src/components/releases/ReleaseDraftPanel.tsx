"use client";

import { useState } from "react";
import { Copy, Check, ExternalLink } from "lucide-react";
import type { ReleaseDraft } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ReleaseDraftPanel({
  draft,
  onTagChange,
}: {
  draft: ReleaseDraft;
  onTagChange: (next: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [tagInput, setTagInput] = useState(draft.next_tag);

  const copyMd = async () => {
    try {
      await navigator.clipboard.writeText(draft.notes_markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard might be blocked in some contexts */
    }
  };

  const githubReleaseUrl = `https://github.com/${draft.repo_full_name}/releases/new?tag=${encodeURIComponent(
    draft.next_tag,
  )}`;

  return (
    <div>
      <div className="flex items-end gap-3 mb-4">
        <div className="flex-1">
          <label className="text-xs text-zinc-500 block mb-1">Next tag</label>
          <input
            type="text"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onBlur={() => onTagChange(tagInput.trim() || draft.next_tag)}
            placeholder={draft.next_tag}
            className="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-teal-600"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={copyMd}
            className={cn(
              "px-3 py-2 rounded-md text-xs font-medium border transition-colors flex items-center gap-1.5",
              copied
                ? "border-teal-700 bg-teal-950/40 text-teal-300"
                : "border-zinc-700 text-zinc-300 hover:border-zinc-500"
            )}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? "Copied" : "Copy markdown"}
          </button>
          <a
            href={githubReleaseUrl}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-2 rounded-md text-xs font-medium bg-teal-700 hover:bg-teal-600 text-white inline-flex items-center gap-1.5"
          >
            Create on GitHub
            <ExternalLink size={12} />
          </a>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 mb-4 text-xs text-zinc-500 grid grid-cols-3 gap-4">
        <Field label="Previous tag" value={draft.previous_tag ?? "—"} />
        <Field label="Merged PRs" value={String(draft.pull_count)} />
        <Field label="Repo" value={draft.repo_full_name} />
      </div>

      <pre className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 text-xs text-zinc-200 whitespace-pre-wrap font-mono leading-relaxed overflow-auto max-h-[60vh]">
        {draft.notes_markdown}
      </pre>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-600 mb-0.5">
        {label}
      </div>
      <div className="text-zinc-300 truncate" title={value}>
        {value}
      </div>
    </div>
  );
}
