from __future__ import annotations

import asyncio
import sys

import click

from .db import SessionLocal, engine
from .services.auth import resolve_pat
from .services.github_client import GitHubClient
from .services.sync import sync_repos


@click.group()
def cli() -> None:
    """RepoLens CLI."""


@cli.command("sync-repos")
def sync_repos_cmd() -> None:
    """Pull the user's repo list from GitHub and upsert into local DB."""
    asyncio.run(_sync_repos())


async def _sync_repos() -> None:
    try:
        async with SessionLocal() as db:
            pat = await resolve_pat(db)
            if not pat:
                click.echo(
                    "Error: no PAT available. Save one via the Settings page "
                    "(http://localhost:3003/settings) or set GITHUB_PAT in backend/.env.",
                    err=True,
                )
                sys.exit(1)
            async with GitHubClient(token=pat) as github:
                run = await sync_repos(db, github)
        elapsed = (run.finished_at - run.started_at).total_seconds() if run.finished_at else 0.0
        click.echo(
            f"✓ synced {run.repos_synced} repos in {elapsed:.1f}s "
            f"(api calls: {run.api_calls}, rate limit remaining: {run.rate_limit_remaining})"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    cli()
