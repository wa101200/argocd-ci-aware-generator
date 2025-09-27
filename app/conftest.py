import os
import tempfile
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from state import setup_db


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """A fixture that provides an httpx.AsyncClient for testing an ASGI application."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture(scope="function", autouse=True)
async def use_temp_db() -> AsyncGenerator[None, None]:
    """A fixture that sets up a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".json")

    os.close(fd)
    db = setup_db(path)
    yield
    db.close()
    os.remove(path)
