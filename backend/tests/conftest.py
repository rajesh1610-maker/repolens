import pytest

from repolens.db import engine


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    """Drain the SQLAlchemy async pool after each test.

    pytest-asyncio uses a fresh event loop per function by default; without
    this fixture, asyncpg connections in the pool reference a closed loop
    on the next test and raise "Event loop is closed" during teardown.
    """
    yield
    await engine.dispose()
