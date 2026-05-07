import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";

export default function RepoDetailPage({
  params,
}: {
  params: { owner: string; name: string };
}) {
  const fullName = `${params.owner}/${params.name}`;
  const githubUrl = `https://github.com/${fullName}`;

  return (
    <div className="max-w-4xl">
      <Link
        href="/repos"
        className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 mb-6 transition-colors"
      >
        <ArrowLeft size={12} />
        All repos
      </Link>

      <div className="flex items-start justify-between gap-4 mb-2">
        <h1 className="text-2xl font-semibold">{fullName}</h1>
        <a
          href={githubUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 px-3 py-1.5 rounded-md border border-zinc-800 hover:border-zinc-700 transition-colors"
        >
          Open on GitHub
          <ExternalLink size={12} />
        </a>
      </div>

      <p className="text-zinc-400 text-sm mb-8">
        Phase 4 lights up this page with PRs, issues, releases, and traffic.
      </p>

      <div className="rounded-lg border border-zinc-800 p-8 text-center text-zinc-500 text-sm">
        Repo detail (Phase 4 placeholder)
      </div>
    </div>
  );
}
