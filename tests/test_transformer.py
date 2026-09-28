from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.schemas import Operation
from app.services.transformer import TransformationError, transform_dataframe


def operations(*items: dict[str, object]) -> list[Operation]:
    return [Operation.model_validate(item) for item in items]


def test_text_cleanup_fill_and_rename() -> None:
    frame = pd.DataFrame(
        {" Full Name ": ["  ALICE ", None, "BoB"], "status": [" ACTIVE ", "", " Paused"]}
    )
    result = transform_dataframe(
        frame,
        operations(
            {"type": "rename_column", "column": " Full Name ", "new_name": "name"},
            {"type": "trim_whitespace"},
            {"type": "lowercase", "columns": ["name", "status"]},
            {"type": "fill_missing", "column": "name", "value": "unknown"},
        ),
    )

    assert result.dataframe.to_dict(orient="list") == {
        "name": ["alice", "unknown", "bob"],
        "status": ["active", "", "paused"],
    }
    assert result.stats.changed_cells == 8


def test_drop_duplicates_and_empty_rows_tracks_stats() -> None:
    frame = pd.DataFrame(
        {
            "email": ["a@example.com", "a@example.com", "", None, "b@example.com"],
            "name": ["A", "A", " ", None, "B"],
        }
    )
    result = transform_dataframe(
        frame,
        operations(
            {"type": "drop_empty_rows", "how": "all"},
            {"type": "drop_duplicates", "columns": ["email"]},
        ),
    )

    assert len(result.dataframe) == 2
    assert result.stats.empty_rows_removed == 2
    assert result.stats.duplicates_removed == 1


def test_drop_rows_with_any_empty_value() -> None:
    frame = pd.DataFrame({"name": ["Ada", "Grace", ""], "email": ["a@example.com", None, "x"]})
    result = transform_dataframe(
        frame,
        operations({"type": "drop_empty_rows", "columns": ["name", "email"], "how": "any"}),
    )

    assert result.dataframe["name"].tolist() == ["Ada"]
    assert result.stats.empty_rows_removed == 2


def test_uppercase_and_keep_invalid_value() -> None:
    frame = pd.DataFrame({"state": ["zh", "be"], "amount": ["12", "unknown"]})
    result = transform_dataframe(
        frame,
        operations(
            {"type": "uppercase", "columns": ["state"]},
            {"type": "convert_numeric", "column": "amount", "invalid": "keep"},
        ),
    )

    assert result.dataframe.to_dict(orient="list") == {
        "state": ["ZH", "BE"],
        "amount": [12, "unknown"],
    }
    assert result.stats.invalid_rows == 1


def test_date_and_numeric_normalization_with_invalid_behaviors() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2025-01-03", "01/04/2025", "not-a-date", ""],
            "amount": ["1,250", "9.5", "bad", None],
        }
    )
    result = transform_dataframe(
        frame,
        operations(
            {"type": "normalize_dates", "column": "date", "invalid": "empty"},
            {"type": "convert_numeric", "column": "amount", "invalid": "drop"},
        ),
    )

    assert len(result.dataframe) == 3
    assert result.dataframe.loc[0, "date"] == "2025-01-03"
    assert result.dataframe.loc[1, "date"] == "2025-01-04"
    assert result.dataframe.loc[0, "amount"] == 1250
    assert result.stats.invalid_rows == 1


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        ("equals", "ALPHA", ["Alpha"]),
        ("not_equals", "alpha", ["beta", "Gamma", ""]),
        ("contains", "mm", ["Gamma"]),
        ("not_contains", "a", [""]),
        ("is_empty", None, [""]),
        ("is_not_empty", None, ["Alpha", "beta", "Gamma"]),
    ],
)
def test_text_filter_operators(operator: str, value: object, expected: list[str]) -> None:
    frame = pd.DataFrame({"label": ["Alpha", "beta", "Gamma", ""]})
    result = transform_dataframe(
        frame,
        operations(
            {"type": "filter_rows", "column": "label", "operator": operator, "value": value}
        ),
    )
    assert result.dataframe["label"].tolist() == expected


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("greater_than", [20, 30]),
        ("greater_or_equal", [10, 20, 30]),
        ("less_than", [5]),
        ("less_or_equal", [5, 10]),
    ],
)
def test_numeric_filter_operators(operator: str, expected: list[int]) -> None:
    frame = pd.DataFrame({"amount": [5, 10, 20, 30, "bad"]})
    result = transform_dataframe(
        frame,
        operations({"type": "filter_rows", "column": "amount", "operator": operator, "value": 10}),
    )
    assert result.dataframe["amount"].tolist() == expected


def test_incompatible_recipe_has_helpful_error() -> None:
    frame = pd.DataFrame({"name": ["Ada"]})
    with pytest.raises(TransformationError, match=r"missing column.*email"):
        transform_dataframe(frame, operations({"type": "lowercase", "columns": ["email"]}))


def test_rename_rejects_existing_column() -> None:
    frame = pd.DataFrame({"name": ["Ada"], "email": ["ada@example.com"]})
    with pytest.raises(TransformationError, match="already exists"):
        transform_dataframe(
            frame, operations({"type": "rename_column", "column": "name", "new_name": "email"})
        )


def test_checked_in_demo_recipe_matches_expected_dataset() -> None:
    root = Path(__file__).resolve().parent.parent
    dirty = pd.read_csv(root / "samples/customer_data_dirty.csv", dtype=object)
    expected = pd.read_csv(root / "samples/customer_data_clean_expected.csv", dtype=object)
    recipe = json.loads((root / "samples/customer_cleanup_recipe.json").read_text())

    result = transform_dataframe(
        dirty, [Operation.model_validate(item) for item in recipe["operations"]]
    )

    assert result.stats.as_dict() == {
        "input_rows": 1253,
        "output_rows": 1187,
        "duplicates_removed": 41,
        "empty_rows_removed": 0,
        "invalid_rows": 25,
        "changed_cells": 6776,
    }
    pd.testing.assert_frame_equal(result.dataframe.astype(str), expected.astype(str))
