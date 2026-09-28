from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest

from app.config import Settings
from app.services import files
from app.services.files import FileValidationError, cleanup_expired_files, sanitize_filename


def test_sanitize_filename_handles_client_paths() -> None:
    assert sanitize_filename("../exports/customers.csv") == "customers.csv"
    assert sanitize_filename(r"C:\Users\client\customers.xlsx") == "customers.xlsx"


def test_cleanup_expired_files_only_removes_old_files(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    old_file = uploads / "old.csv"
    recent_file = uploads / "recent.csv"
    old_file.write_text("old", encoding="utf-8")
    recent_file.write_text("recent", encoding="utf-8")
    now = 10_000.0
    os.utime(old_file, (now - 7_200, now - 7_200))
    os.utime(recent_file, (now - 60, now - 60))

    assert cleanup_expired_files((uploads,), 1, now=now) == 1
    assert not old_file.exists()
    assert recent_file.exists()


def test_xlsx_expansion_limit_is_checked_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    workbook = io.BytesIO()
    with zipfile.ZipFile(workbook, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/large.xml", "x" * 101)
    workbook.seek(0)
    monkeypatch.setattr(files, "MAX_XLSX_UNCOMPRESSED_BYTES", 100)

    with pytest.raises(FileValidationError, match="expands beyond"):
        files.validate_xlsx_archive(workbook)


def test_settings_reject_invalid_file_retention(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="FILE_TTL_HOURS"):
        Settings(
            data_dir=tmp_path,
            database_path=tmp_path / "flowforge.db",
            file_ttl_hours=0,
        )
