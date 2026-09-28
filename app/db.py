from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.models import JobRecord, RecipeRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    operations_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    input_filename TEXT NOT NULL,
    output_filename TEXT,
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    stats_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def create_recipe(
        self, name: str, description: str, operations: list[dict[str, Any]]
    ) -> RecipeRecord:
        with self.connect() as connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO recipes (name, description, operations_json) VALUES (?, ?, ?)",
                    (name.strip(), description.strip(), json.dumps(operations)),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"A recipe named '{name}' already exists") from exc
            row = connection.execute(
                "SELECT * FROM recipes WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._recipe_from_row(row)

    def list_recipes(self) -> list[RecipeRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recipes ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._recipe_from_row(row) for row in rows]

    def get_recipe(self, recipe_id: int) -> RecipeRecord | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        return self._recipe_from_row(row) if row else None

    def delete_recipe(self, recipe_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        return cursor.rowcount > 0

    def create_job(
        self,
        *,
        job_id: str,
        input_filename: str,
        output_filename: str | None,
        recipe_id: int | None,
        status: str,
        stats: dict[str, int],
        error_message: str | None = None,
    ) -> JobRecord:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, input_filename, output_filename, recipe_id,
                    status, stats_json, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    input_filename,
                    output_filename,
                    recipe_id,
                    status,
                    json.dumps(stats),
                    error_message,
                ),
            )
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job_from_row(row)

    def list_jobs(self, limit: int = 20) -> list[JobRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    @staticmethod
    def _recipe_from_row(row: sqlite3.Row) -> RecipeRecord:
        from datetime import datetime

        return RecipeRecord(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            operations=json.loads(row["operations_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> JobRecord:
        from datetime import datetime

        return JobRecord(
            id=row["id"],
            input_filename=row["input_filename"],
            output_filename=row["output_filename"],
            recipe_id=row["recipe_id"],
            status=row["status"],
            stats=json.loads(row["stats_json"]),
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
