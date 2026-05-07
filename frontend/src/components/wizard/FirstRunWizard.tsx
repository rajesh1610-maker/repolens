"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Eye,
  EyeOff,
  Github,
  Sparkles,
  ArrowRight,
  Check,
  Loader2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import {
  api,
  ApiError,
  SYNC_EVENT,
  type SettingsOverview,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * First-run experience: gates the app on a configured user.
 *
 * - Polls `/api/settings` once on mount.
 * - If the user is configured → renders `children` (the normal app).
 * - If not → takes over the viewport with a 3-step wizard:
 *     1. Save GitHub PAT (validates against `/user`, errors are surfaced)
 *     2. Run the first sync (so the Inbox isn't empty when they land)
 *     3. Optional Anthropic key for the AI digest
 * - Once the user finishes (or skips step 3), reloads settings and the
 *   children render.
 *
 * The gate is intentionally NOT a route. A wizard at `/setup` would
 * leave the rest of the app reachable in a half-configured state
 * (manual URL nav, browser history). Inline gating means there is
 * exactly one entry point until setup is done.
 */
export function FirstRunWizard({ children }: { children: React.ReactNode }) {
  const [overview, setOverview] = useState<SettingsOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const o = await api<SettingsOverview>("/api/settings");
      setOverview(o);
    } catch {
      // If settings can't load, still show children — the page-level
      // error UI will surface what's wrong. Don't trap the user behind
      // a wizard when the backend is unreachable.
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-zinc-500 text-sm">
        Loading…
      </div>
    );
  }

  // If settings call failed OR user is configured: render the app.
  if (!overview || overview.user.configured) {
    return <>{children}</>;
  }

  return <Wizard onComplete={refresh} />;
}

type Step = 1 | 2 | 3;

function Wizard({ onComplete }: { onComplete: () => Promise<void> }) {
  const [step, setStep] = useState<Step>(1);
  const [overview, setOverview] = useState<SettingsOverview | null>(null);

  const reload = useCallback(async () => {
    const o = await api<SettingsOverview>("/api/settings");
    setOverview(o);
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-xl space-y-6">
        <header className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-teal-500" />
            <span className="text-sm font-semibold tracking-wide">RepoLens</span>
          </div>
          <h1 className="text-2xl font-semibold">Let&apos;s get you set up</h1>
          <p className="text-sm text-zinc-400">
            Three quick steps. Everything stays self-hosted on this machine —
            your PAT and API key are encrypted at rest.
          </p>
        </header>

        <Stepper step={step} />

        {step === 1 && (
          <PatStep
            overview={overview}
            onSaved={async () => {
              await reload();
              setStep(2);
            }}
          />
        )}

        {step === 2 && (
          <SyncStep
            onDone={async () => {
              await reload();
              setStep(3);
            }}
          />
        )}

        {step === 3 && (
          <AnthropicStep
            onSaved={onComplete}
            onSkip={onComplete}
          />
        )}
      </div>
    </div>
  );
}

function Stepper({ step }: { step: Step }) {
  return (
    <ol className="flex items-center gap-2 text-xs">
      {[
        { n: 1 as const, label: "GitHub PAT" },
        { n: 2 as const, label: "First sync" },
        { n: 3 as const, label: "Anthropic key" },
      ].map(({ n, label }, i, arr) => {
        const done = step > n;
        const active = step === n;
        return (
          <li key={n} className="flex items-center gap-2 flex-1">
            <span
              className={cn(
                "w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0",
                done
                  ? "bg-teal-700 text-white"
                  : active
                    ? "bg-teal-950 border border-teal-700 text-teal-300"
                    : "bg-zinc-900 border border-zinc-800 text-zinc-500"
              )}
            >
              {done ? <Check size={12} /> : n}
            </span>
            <span
              className={cn(
                "truncate",
                active ? "text-zinc-200" : done ? "text-zinc-400" : "text-zinc-600"
              )}
            >
              {label}
            </span>
            {i < arr.length - 1 && (
              <span className="flex-1 h-px bg-zinc-800" aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function PatStep({
  overview,
  onSaved,
}: {
  overview: SettingsOverview | null;
  onSaved: () => Promise<void>;
}) {
  const [pat, setPat] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If a PAT is already saved (e.g. via env), allow advancing without re-entering
  const alreadyConfigured = !!overview?.user.has_pat;

  const submit = async () => {
    if (!pat.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api("/api/settings/pat", {
        method: "POST",
        body: JSON.stringify({ pat: pat.trim() }),
      });
      await onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-zinc-800 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Github size={18} />
        <h2 className="font-semibold">Connect GitHub</h2>
      </div>
      <p className="text-sm text-zinc-400">
        Create a personal access token at{" "}
        <a
          href="https://github.com/settings/tokens"
          target="_blank"
          rel="noreferrer"
          className="text-teal-400 hover:underline"
        >
          github.com/settings/tokens
        </a>
        . Required scopes: <code className="text-zinc-300">repo</code> +{" "}
        <code className="text-zinc-300">read:org</code>. The token is encrypted
        with AES-GCM before being stored.
      </p>

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/30 p-3 flex items-start gap-2 text-xs">
          <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
          <div className="text-red-400/90 break-words">{error}</div>
        </div>
      )}

      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type={show ? "text" : "password"}
            value={pat}
            onChange={(e) => setPat(e.target.value)}
            placeholder="ghp_…"
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm pr-10 focus:outline-none focus:border-teal-600"
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
          >
            {show ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        <button
          onClick={submit}
          disabled={busy || !pat.trim()}
          className={cn(
            "px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-1.5",
            busy || !pat.trim()
              ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
              : "bg-teal-700 hover:bg-teal-600 text-white"
          )}
        >
          {busy ? (
            <>
              <Loader2 size={14} className="animate-spin" /> Validating
            </>
          ) : (
            <>
              Save <ArrowRight size={14} />
            </>
          )}
        </button>
      </div>

      {alreadyConfigured && (
        <button
          onClick={() => onSaved()}
          className="text-xs text-zinc-400 hover:text-zinc-200 underline-offset-2 hover:underline"
        >
          Already have a PAT in .env — continue
        </button>
      )}
    </section>
  );
}

function SyncStep({ onDone }: { onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{
    repos: number;
    pulls: number;
    issues: number;
  } | null>(null);

  const runSync = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api<{
        repos_synced: number;
        pulls_synced: number;
        issues_synced: number;
      }>("/api/sync", { method: "POST" });
      setStats({
        repos: result.repos_synced,
        pulls: result.pulls_synced,
        issues: result.issues_synced,
      });
      window.dispatchEvent(new CustomEvent(SYNC_EVENT));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-zinc-800 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <RefreshCw size={18} />
        <h2 className="font-semibold">Run your first sync</h2>
      </div>
      <p className="text-sm text-zinc-400">
        We&apos;ll pull your repos, open PRs, issues, releases, and 14 days of
        traffic. Takes 5–60 seconds depending on how many repos you have.
      </p>

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/30 p-3 flex items-start gap-2 text-xs">
          <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
          <div className="text-red-400/90 break-words">{error}</div>
        </div>
      )}

      {stats ? (
        <div className="rounded-md bg-zinc-900/50 border border-zinc-800 p-3 text-xs grid grid-cols-3 gap-3">
          <Stat label="Repos" value={stats.repos} />
          <Stat label="Pulls" value={stats.pulls} />
          <Stat label="Issues" value={stats.issues} />
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <button
          onClick={runSync}
          disabled={busy}
          className={cn(
            "px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-1.5",
            busy
              ? "bg-zinc-800 text-zinc-400 cursor-wait"
              : "bg-teal-700 hover:bg-teal-600 text-white"
          )}
        >
          {busy ? (
            <>
              <Loader2 size={14} className="animate-spin" /> Syncing…
            </>
          ) : stats ? (
            "Sync again"
          ) : (
            "Run sync"
          )}
        </button>
        {stats && (
          <button
            onClick={() => onDone()}
            className="px-4 py-2 rounded-md text-sm font-medium border border-zinc-700 text-zinc-200 hover:border-zinc-500 transition-colors flex items-center gap-1.5"
          >
            Continue <ArrowRight size={14} />
          </button>
        )}
      </div>
    </section>
  );
}

function AnthropicStep({
  onSaved,
  onSkip,
}: {
  onSaved: () => Promise<void>;
  onSkip: () => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!key.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api("/api/settings/anthropic-key", {
        method: "POST",
        body: JSON.stringify({ api_key: key.trim() }),
      });
      await onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-zinc-800 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Sparkles size={18} className="text-teal-400" />
        <h2 className="font-semibold">Anthropic API key</h2>
        <span className="text-[10px] uppercase tracking-wide text-zinc-500 ml-auto">
          Optional
        </span>
      </div>
      <p className="text-sm text-zinc-400">
        Powers the weekly digest. Skip if you only want the dashboard for now —
        you can add the key later in Settings. Typical Opus 4.7 digest costs
        ~$0.05–$0.15.
      </p>

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/30 p-3 flex items-start gap-2 text-xs">
          <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
          <div className="text-red-400/90 break-words">{error}</div>
        </div>
      )}

      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type={show ? "text" : "password"}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-ant-…"
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm pr-10 focus:outline-none focus:border-teal-600"
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
          >
            {show ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        <button
          onClick={submit}
          disabled={busy || !key.trim()}
          className={cn(
            "px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-1.5",
            busy || !key.trim()
              ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
              : "bg-teal-700 hover:bg-teal-600 text-white"
          )}
        >
          {busy ? "Saving…" : "Save & finish"}
        </button>
      </div>

      <button
        onClick={() => onSkip()}
        className="text-xs text-zinc-400 hover:text-zinc-200 underline-offset-2 hover:underline"
      >
        Skip for now — go to the app
      </button>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="text-base font-semibold text-zinc-100 tabular-nums">
        {value}
      </div>
    </div>
  );
}
