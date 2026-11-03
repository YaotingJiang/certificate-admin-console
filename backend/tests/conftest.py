import os
import pathlib
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["APP_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="certadmin-"), "test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs lifespan: schema + quick-start seed on the temp DB
        yield c
