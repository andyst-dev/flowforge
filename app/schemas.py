from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
        if self.type == OperationType.RENAME_COLUMN:
            new_name = self.new_name.strip() if self.new_name else ""
            if not new_name:
                raise ValueError("'rename_column' requires a non-empty new_name")
            self.new_name = new_name
        if self.type == OperationType.FILTER_ROWS and not self.operator:
            raise ValueError("'filter_rows' requires an operator")
        value_optional_operators = {"is_empty", "is_not_empty"}
        if (
            self.type == OperationType.FILTER_ROWS
            and self.operator not in value_optional_operators
            and self.value is None
        ):
            raise ValueError(f"'{self.operator}' requires a filter value")
        return self


class RecipeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    operations: list[Operation] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Recipe name cannot be blank")
        return value


class RecipeResponse(RecipeCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class DataPreview(BaseModel):
    columns: list[str]
    rows: list[dict[str, str]]
    total_rows: int


class UploadResponse(DataPreview):
    upload_id: str
    filename: str


class ProcessingStatsResponse(BaseModel):
    input_rows: int
    output_rows: int
    duplicates_removed: int
    empty_rows_removed: int
    invalid_rows: int
    changed_cells: int


class TransformResponse(BaseModel):
    result_id: str
    job_id: str
    before: DataPreview
    after: DataPreview
    stats: ProcessingStatsResponse


class JobResponse(BaseModel):
    id: str
    input_filename: str
    output_filename: str | None
    recipe_id: int | None
    status: Literal["completed", "failed"]
    stats: dict[str, int]
    error_message: str | None
    created_at: datetime


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
