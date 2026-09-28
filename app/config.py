from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path = Path(os.getenv("FLOWFORGE_DATA_DIR", BASE_DIR / "storage"))
    database_path: Path = Path(
        os.getenv("FLOWFORGE_DATABASE_PATH", BASE_DIR / "storage" / "flowforge.db")
    )
    max_upload_mb: int = int(os.getenv("FLOWFORGE_MAX_UPLOAD_MB", "15"))
    preview_rows: int = int(os.getenv("FLOWFORGE_PREVIEW_ROWS", "12"))
    file_ttl_hours: int = int(os.getenv("FLOWFORGE_FILE_TTL_HOURS", "24"))

    def __post_init__(self) -> None:
        if self.max_upload_mb < 1:
            raise ValueError("FLOWFORGE_MAX_UPLOAD_MB must be at least 1")
        if self.preview_rows < 1:
            raise ValueError("FLOWFORGE_PREVIEW_ROWS must be at least 1")
        if self.file_ttl_hours < 1:
            raise ValueError("FLOWFORGE_FILE_TTL_HOURS must be at least 1")

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def results_dir(self) -> Path:
        return self.data_dir / "results"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
