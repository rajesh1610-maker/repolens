export default function ReposPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold mb-1">Repos</h1>
      <p className="text-zinc-400 text-sm mb-6">
        The wall — one card per tracked repo. Phase 3 will render this grid
        from cached GitHub data.
      </p>
      <div className="rounded-lg border border-zinc-800 p-6 text-zinc-400">
        No repos tracked yet. (Phase 0 placeholder.)
      </div>
    </div>
  );
}
