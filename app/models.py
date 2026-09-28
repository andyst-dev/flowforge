from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RecipeRecord:
    id: int
    name: str
    description: str
    operations: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    input_filename: str
    output_filename: str | None
    recipe_id: int | None
    status: str
    stats: dict[str, int]
    error_message: str | None
    created_at: datetime
