from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class OperationType(StrEnum):
    RENAME_COLUMN = "rename_column"
    DROP_DUPLICATES = "drop_duplicates"
    DROP_EMPTY_ROWS = "drop_empty_rows"
    FILL_MISSING = "fill_missing"
    TRIM_WHITESPACE = "trim_whitespace"
    LOWERCASE = "lowercase"
    UPPERCASE = "uppercase"
    NORMALIZE_DATES = "normalize_dates"
    CONVERT_NUMERIC = "convert_numeric"
    FILTER_ROWS = "filter_rows"


class Operation(BaseModel):
    type: OperationType
    column: str | None = None
    columns: list[str] | None = None
    new_name: str | None = None
    value: Any = None
    operator: (
        Literal[
            "equals",
            "not_equals",
            "contains",
            "not_contains",
            "greater_than",
            "greater_or_equal",
            "less_than",
            "less_or_equal",
            "is_empty",
            "is_not_empty",
        ]
        | None
    ) = None
    date_format: str = "%Y-%m-%d"
    invalid: Literal["keep", "empty", "drop"] = "empty"
    how: Literal["any", "all"] = "all"

    @model_validator(mode="after")
    def validate_for_type(self) -> Operation:
        column_required = {
            OperationType.RENAME_COLUMN,
            OperationType.FILL_MISSING,
            OperationType.NORMALIZE_DATES,
            OperationType.CONVERT_NUMERIC,
            OperationType.FILTER_ROWS,
        }
        if self.type in column_required and not self.column:
            raise ValueError(f"'{self.type}' requires a column")
        if self.type == OperationType.RENAME_COLUMN and not self.new_name:
            raise ValueError("'rename_column' requires a new_name")
        if self.type == OperationType.FILTER_ROWS and not self.operator:
            raise ValueError("'filter_rows' requires an operator")
        return self


class RecipeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    operations: list[Operation] = Field(min_length=1)


class RecipeResponse(RecipeCreate):
    id: int
    created_at: str
    updated_at: str


class TransformRequest(BaseModel):
    upload_id: str
    operations: list[Operation] | None = None
    recipe_id: int | None = None

    @model_validator(mode="after")
    def require_recipe_or_operations(self) -> TransformRequest:
        if self.recipe_id is None and not self.operations:
            raise ValueError("Provide recipe_id or at least one operation")
        if self.recipe_id is not None and self.operations:
            raise ValueError("Provide recipe_id or operations, not both")
        return self


class ExportRequest(BaseModel):
    result_id: str
    format: Literal["csv", "xlsx"]
