import os
import tempfile
import pytest

TEST_DIR = tempfile.TemporaryDirectory(prefix='invest-watch-tests-')
os.environ['DATABASE_URL'] = 'sqlite:///'+TEST_DIR.name.replace('\\', '/')+'/test.db'
os.environ['DATA_DIR'] = TEST_DIR.name
from app.db import Base, engine, initialize


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    TEST_DIR.cleanup()


@pytest.fixture(autouse=True)
def database(monkeypatch):
    monkeypatch.delenv('APP_TOKEN', raising=False)
    monkeypatch.delenv('ALLOW_PRIVATE_ENDPOINTS', raising=False)
    Base.metadata.drop_all(engine)
    initialize()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        yield client
