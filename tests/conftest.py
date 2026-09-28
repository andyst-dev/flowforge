from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "storage",
        database_path=tmp_path / "storage" / "test.db",
        max_upload_mb=2,
        preview_rows=5,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
