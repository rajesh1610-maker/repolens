from __future__ import annotations

import asyncio
import sys

import click

from .config import get_settings
from .db import SessionLocal, engine
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
    settings = get_settings()
    if not settings.github_pat:
        click.echo(
            "Error: GITHUB_PAT not set. Add it to backend/.env or export it.",
            err=True,
        )
        sys.exit(1)

    try:
        async with GitHubClient(token=settings.github_pat) as github:
            async with SessionLocal() as db:
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
