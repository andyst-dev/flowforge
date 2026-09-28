from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import Operation, RecipeCreate


def test_recipe_name_is_trimmed_and_cannot_be_blank() -> None:
    recipe = RecipeCreate(
        name="  Customer cleanup  ",
        operations=[Operation(type="drop_duplicates")],
    )
    assert recipe.name == "Customer cleanup"

    with pytest.raises(ValidationError, match="Recipe name cannot be blank"):
        RecipeCreate(name="   ", operations=[Operation(type="drop_duplicates")])


def test_parameterized_operations_require_meaningful_values() -> None:
    with pytest.raises(ValidationError, match="non-empty new_name"):
        Operation(type="rename_column", column="email", new_name="   ")

    with pytest.raises(ValidationError, match="requires a filter value"):
        Operation(type="filter_rows", column="status", operator="equals")

    operation = Operation(type="filter_rows", column="email", operator="is_empty")
    assert operation.value is None


def test_settings_reject_non_positive_limits(tmp_path) -> None:
    with pytest.raises(ValueError, match="MAX_UPLOAD_MB"):
        Settings(data_dir=tmp_path, database_path=tmp_path / "db.sqlite", max_upload_mb=0)

    with pytest.raises(ValueError, match="PREVIEW_ROWS"):
        Settings(data_dir=tmp_path, database_path=tmp_path / "db.sqlite", preview_rows=0)
