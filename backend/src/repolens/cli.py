from __future__ import annotations

import asyncio
import sys

import click

from .db import SessionLocal, engine
from .services.auth import resolve_pat
from .services.crypto import CryptoError
from .services.github_client import GitHubClient
from .services.sync import run_full_sync


@click.group()
def cli() -> None:
    """RepoLens CLI."""


@cli.command("sync")
def sync_cmd() -> None:
    """Run a full sync: repos + PRs + issues for every tracked repo."""
    asyncio.run(_run_sync())


async def _run_sync() -> None:
    try:
        async with SessionLocal() as db:
            try:
                pat = await resolve_pat(db)
            except CryptoError as exc:
                click.echo(
                    f"Error: cannot decrypt the saved PAT — {exc}\n"
                    f"\n"
                    f"This usually means REPOLENS_ENCRYPTION_KEY in backend/.env "
                    f"is missing, malformed, or different from the key used when "
                    f"the PAT was originally saved.\n"
                    f"\n"
                    f"Fix: restore the original key, or DELETE the saved PAT "
                    f"(curl -X DELETE http://localhost:8004/api/settings/pat) "
                    f"and re-save through the Settings page.",
                    err=True,
                )
                sys.exit(2)
            if not pat:
                click.echo(
                    "Error: no PAT available. Save one via the Settings page "
                    "(http://localhost:3003/settings) or set GITHUB_PAT in backend/.env.",
                    err=True,
                )
                sys.exit(1)
            async with GitHubClient(token=pat) as github:
                run = await run_full_sync(db, github)
        elapsed = (run.finished_at - run.started_at).total_seconds() if run.finished_at else 0.0
        click.echo(
            f"✓ synced {run.repos_synced} repos, {run.pulls_synced} PRs, "
            f"{run.issues_synced} issues in {elapsed:.1f}s "
            f"(api calls: {run.api_calls}, rate limit remaining: {run.rate_limit_remaining})"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    cli()
