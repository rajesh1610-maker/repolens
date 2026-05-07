import { api, type Healthz } from "@/lib/api";

async function getHealth(): Promise<Healthz | null> {
  try {
    return await api<Healthz>("/healthz", { cache: "no-store" });
  } catch {
    return null;
  }
}

export default async function InboxPage() {
  const health = await getHealth();
  return (
    <div>
      <h1 className="text-2xl font-semibold mb-1">Inbox</h1>
      <p className="text-zinc-400 text-sm mb-6">
        Phase 5 will populate this page with prioritized PRs and issues across
        every tracked repo.
      </p>

      <div className="rounded-lg border border-zinc-800 p-6 text-zinc-400">
        Inbox zero. (Phase 0 placeholder — no data sources connected yet.)
      </div>

      <div className="mt-8 rounded-lg border border-zinc-800 p-4 text-xs">
        <div className="text-zinc-500 mb-2">Backend connectivity</div>
        {health ? (
          <pre className="text-teal-400">{JSON.stringify(health, null, 2)}</pre>
        ) : (
          <div className="text-red-400">
            Backend unreachable at {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8004"}.
            Start it with <code className="text-zinc-300">make dev-backend</code>.
          </div>
        )}
      </div>
    </div>
  );
}
