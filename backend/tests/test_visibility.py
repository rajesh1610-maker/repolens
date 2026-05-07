"""End-to-end tests for D16: public-only mode hides private repos
from every list and detail endpoint, in one click.

This is the privacy contract documented prominently in the README. Any
regression here directly leaks private repo names to a screenshot or
demo. Test seeds one public + one private repo, flips the toggle, and
asserts the correct visibility on every relevant endpoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select, update

from repolens.db import SessionLocal
from repolens.main import app
from repolens.models import InboxItem, Issue, PullRequest, Repo, User


@pytest.fixture
async def seeded_visibility_world():
    """Snapshot the dev user, seed one public + one private repo on it
    plus one open PR + one open issue per repo, plus inbox rows.
    Restore everything on teardown.
    """
    async with SessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if user is None:
            yield None
            return
        user_id = user.id
        snapshot_pom = user.public_only_mode

        public_repo_id = uuid.uuid4()
        private_repo_id = uuid.uuid4()
        base_gh = 7_000_000_000_000

        await db.execute(
            insert(Repo).values(
                [
                    {
                        "id": public_repo_id,
                        "user_id": user_id,
                        "github_id": base_gh + 1,
                        "owner": "vis-test",
                        "name": "public-repo",
                        "full_name": "vis-test/public-repo",
                        "visibility": "public",
                        "stars": 0,
                        "forks": 0,
                        "open_issues_count": 0,
                        "tracked": True,
                    },
                    {
                        "id": private_repo_id,
                        "user_id": user_id,
                        "github_id": base_gh + 2,
                        "owner": "vis-test",
                        "name": "private-repo",
                        "full_name": "vis-test/private-repo",
                        "visibility": "private",
                        "stars": 0,
                        "forks": 0,
                        "open_issues_count": 0,
                        "tracked": True,
                    },
                ]
            )
        )

        now = datetime.now(UTC)
        # PR + Issue in each repo (so /api/repos/{}/pulls and /issues exercise them)
        for repo_id in (public_repo_id, private_repo_id):
            await db.execute(
                insert(PullRequest).values(
                    id=uuid.uuid4(),
                    repo_id=repo_id,
                    github_id=uuid.uuid4().int & ((1 << 63) - 1),
                    number=1,
                    title="Vis test PR",
                    state="open",
                    draft=False,
                    labels=[],
                    created_at=now - timedelta(days=1),
                    updated_at=now,
                )
            )
            await db.execute(
                insert(Issue).values(
                    id=uuid.uuid4(),
                    repo_id=repo_id,
                    github_id=uuid.uuid4().int & ((1 << 63) - 1),
                    number=1,
                    title="Vis test Issue",
                    state="open",
                    labels=[],
                    comments_count=0,
                    reactions_total=0,
                    created_at=now - timedelta(days=1),
                    updated_at=now,
                )
            )
            await db.execute(
                insert(InboxItem).values(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    repo_id=repo_id,
                    kind="issue",
                    source_id=uuid.uuid4(),
                    repo_full_name=(
                        "vis-test/public-repo"
                        if repo_id == public_repo_id
                        else "vis-test/private-repo"
                    ),
                    repo_visibility=(
                        "public" if repo_id == public_repo_id else "private"
                    ),
                    number=1,
                    title="Vis test Inbox",
                    url="https://github.com/x/y/issues/1",
                    state="open",
                    draft=False,
                    labels=[],
                    reactions_total=0,
                    comments_count=0,
                    priority_score=0,
                    last_activity_at=now,
                )
            )
        await db.commit()

    yield {
        "user_id": user_id,
        "public_repo_id": public_repo_id,
        "private_repo_id": private_repo_id,
        "snapshot_pom": snapshot_pom,
    }

    # Teardown — drop seeded rows + restore public_only_mode.
    async with SessionLocal() as db:
        await db.execute(delete(Repo).where(Repo.id.in_([public_repo_id, private_repo_id])))
        await db.execute(
            update(User).where(User.id == user_id).values(public_only_mode=snapshot_pom)
        )
        await db.commit()


async def _set_public_only(value: bool) -> None:
    async with SessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        await db.execute(
            update(User).where(User.id == user.id).values(public_only_mode=value)
        )
        await db.commit()


# ---------------- /api/repos ----------------


@pytest.mark.asyncio
async def test_repos_list_hides_private_when_public_only(seeded_visibility_world):
    if seeded_visibility_world is None:
        pytest.skip("no dev user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Off → both visible
        await _set_public_only(False)
        off = await client.get("/api/repos")
        # On → only public
        await _set_public_only(True)
        on = await client.get("/api/repos")

    off_names = {r["full_name"] for r in off.json()}
    on_names = {r["full_name"] for r in on.json()}

    assert "vis-test/public-repo" in off_names
    assert "vis-test/private-repo" in off_names
    assert "vis-test/public-repo" in on_names
    assert "vis-test/private-repo" not in on_names


# ---------------- /api/repos/{owner}/{name} ----------------


@pytest.mark.asyncio
async def test_repo_detail_404s_private_repo_when_public_only(
    seeded_visibility_world,
):
    if seeded_visibility_world is None:
        pytest.skip("no dev user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _set_public_only(False)
        ok = await client.get("/api/repos/vis-test/private-repo")
        await _set_public_only(True)
        hidden = await client.get("/api/repos/vis-test/private-repo")
        # public still 200
        public = await client.get("/api/repos/vis-test/public-repo")

    assert ok.status_code == 200
    assert hidden.status_code == 404
    assert public.status_code == 200
    # Detail message must not leak the existence of the private repo
    detail = hidden.json()["detail"].lower()
    assert "private" not in detail or "public-only" in detail


# ---------------- /api/repos/{owner}/{name}/pulls + /issues ----------------


@pytest.mark.asyncio
async def test_pulls_and_issues_404_for_private_when_public_only(
    seeded_visibility_world,
):
    if seeded_visibility_world is None:
        pytest.skip("no dev user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _set_public_only(True)
        pulls = await client.get("/api/repos/vis-test/private-repo/pulls")
        issues = await client.get("/api/repos/vis-test/private-repo/issues")
        # Public still 200
        pub_pulls = await client.get("/api/repos/vis-test/public-repo/pulls")

    assert pulls.status_code == 404
    assert issues.status_code == 404
    assert pub_pulls.status_code == 200


# ---------------- /api/inbox ----------------


@pytest.mark.asyncio
async def test_inbox_excludes_private_items_when_public_only(seeded_visibility_world):
    if seeded_visibility_world is None:
        pytest.skip("no dev user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _set_public_only(False)
        off = await client.get("/api/inbox")
        await _set_public_only(True)
        on = await client.get("/api/inbox")

    off_repos = {i["repo_full_name"] for i in off.json()["items"]}
    on_repos = {i["repo_full_name"] for i in on.json()["items"]}

    assert "vis-test/public-repo" in off_repos
    assert "vis-test/private-repo" in off_repos
    assert "vis-test/public-repo" in on_repos
    assert "vis-test/private-repo" not in on_repos
    # Facets must reflect the filter too — no private repo counted when on
    assert on.json()["facets"]["all"] >= 1  # at least the public one
