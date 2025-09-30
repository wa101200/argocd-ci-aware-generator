import os
import tempfile
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

from containers import Container
from main import app
from state import DatabaseService


@pytest.fixture
def container() -> AsyncGenerator[Container, None]:
    """A fixture that sets up a container for testing."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)

    container = Container(db_service=providers.Singleton(DatabaseService, db_file=path))

    yield container
    container.db_service().close()
    os.remove(path)


@pytest_asyncio.fixture
async def client(container: Container) -> AsyncClient:
    """A fixture that provides an httpx.AsyncClient for testing an ASGI application."""
    container.wire(modules=["main"])
    app.container = container
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    container.unwire()
