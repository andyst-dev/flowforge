from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.schemas import Operation, OperationType


class TransformationError(ValueError):
    """Raised when a recipe cannot be applied to a dataframe."""


@dataclass(slots=True)
class ProcessingStats:
    input_rows: int
    output_rows: int = 0
    duplicates_removed: int = 0
    empty_rows_removed: int = 0
    invalid_rows: int = 0
    changed_cells: int = 0
    _invalid_indices: set[Any] = field(default_factory=set, repr=False)

    def as_dict(self) -> dict[str, int]:
        return {
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "duplicates_removed": self.duplicates_removed,
            "empty_rows_removed": self.empty_rows_removed,
            "invalid_rows": self.invalid_rows,
            "changed_cells": self.changed_cells,
        }


@dataclass(frozen=True, slots=True)
class TransformResult:
    dataframe: pd.DataFrame
    stats: ProcessingStats


def transform_dataframe(frame: pd.DataFrame, operations: list[Operation]) -> TransformResult:
    result = frame.copy()
    result.columns = [str(column) for column in result.columns]
    stats = ProcessingStats(input_rows=len(result))

    for step, operation in enumerate(operations, start=1):
        try:
            result = _apply_operation(result, operation, stats)
        except TransformationError:
            raise
        except Exception as exc:
            raise TransformationError(f"Step {step} ({operation.type}) failed: {exc}") from exc

    stats.output_rows = len(result)
    stats.invalid_rows = len(stats._invalid_indices)
    return TransformResult(dataframe=result.reset_index(drop=True), stats=stats)


def _apply_operation(
    frame: pd.DataFrame, operation: Operation, stats: ProcessingStats
) -> pd.DataFrame:
    op = operation.type
    if op == OperationType.RENAME_COLUMN:
        _require_columns(frame, [operation.column])
        if operation.new_name in frame.columns and operation.new_name != operation.column:
            raise TransformationError(f"Column '{operation.new_name}' already exists.")
        return frame.rename(columns={operation.column: operation.new_name})

    if op == OperationType.DROP_DUPLICATES:
        subset = _selected_columns(frame, operation.columns)
        before = len(frame)
        frame = frame.drop_duplicates(subset=subset or None, keep="first")
        stats.duplicates_removed += before - len(frame)
        return frame

    if op == OperationType.DROP_EMPTY_ROWS:
        subset = _selected_columns(frame, operation.columns)
        targets = subset or list(frame.columns)
        prepared = frame[targets].replace(r"^\s*$", pd.NA, regex=True)
        empty_mask = prepared.isna().all(axis=1)
        if operation.how == "any":
            empty_mask = prepared.isna().any(axis=1)
        stats.empty_rows_removed += int(empty_mask.sum())
        return frame.loc[~empty_mask]

    if op == OperationType.FILL_MISSING:
        column = _require_column(frame, operation.column)
        missing = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
        stats.changed_cells += int(missing.sum())
        frame.loc[missing, column] = operation.value
        return frame

    if op in {OperationType.TRIM_WHITESPACE, OperationType.LOWERCASE, OperationType.UPPERCASE}:
        columns = _text_columns(frame, operation.columns)
        for column in columns:
            original = frame[column].copy()
            mask = original.notna()
            text = original.loc[mask].astype(str)
            if op == OperationType.TRIM_WHITESPACE:
                transformed = text.str.strip()
            elif op == OperationType.LOWERCASE:
                transformed = text.str.lower()
            else:
                transformed = text.str.upper()
            stats.changed_cells += int((text != transformed).sum())
            frame.loc[mask, column] = transformed
        return frame

    if op == OperationType.NORMALIZE_DATES:
        column = _require_column(frame, operation.column)
        original = frame[column].copy()
        non_empty = original.notna() & original.astype(str).str.strip().ne("")
        parsed = pd.to_datetime(original, errors="coerce", format="mixed", dayfirst=False)
        invalid_mask = non_empty & parsed.isna()
        stats._invalid_indices.update(frame.index[invalid_mask].tolist())
        valid_mask = parsed.notna()
        formatted = parsed.loc[valid_mask].dt.strftime(operation.date_format)
        stats.changed_cells += int((original.loc[valid_mask].astype(str) != formatted).sum())
        frame.loc[valid_mask, column] = formatted
        return _handle_invalid(frame, column, invalid_mask, operation.invalid)

    if op == OperationType.CONVERT_NUMERIC:
        column = _require_column(frame, operation.column)
        original = frame[column].copy()
        text = original.astype(str).str.strip().str.replace(",", "", regex=False)
        non_empty = original.notna() & text.ne("")
        parsed = pd.to_numeric(text, errors="coerce")
        invalid_mask = non_empty & parsed.isna()
        stats._invalid_indices.update(frame.index[invalid_mask].tolist())
        valid_mask = parsed.notna()
        converted = parsed.loc[valid_mask]
        if not converted.empty and converted.mod(1).eq(0).all():
            converted = converted.astype("int64")
        stats.changed_cells += int(
            (original.loc[valid_mask].astype(str) != converted.astype(str)).sum()
        )
        frame.loc[valid_mask, column] = converted.astype(object)
        return _handle_invalid(frame, column, invalid_mask, operation.invalid)

    if op == OperationType.FILTER_ROWS:
        column = _require_column(frame, operation.column)
        mask = _filter_mask(frame[column], operation.operator, operation.value)
        return frame.loc[mask]

    raise TransformationError(f"Unsupported operation: {op}")


def _handle_invalid(
    frame: pd.DataFrame, column: str, invalid_mask: pd.Series, behavior: str
) -> pd.DataFrame:
    if behavior == "drop":
        return frame.loc[~invalid_mask]
    if behavior == "empty":
        frame.loc[invalid_mask, column] = pd.NA
    return frame


def _filter_mask(series: pd.Series, operator: str | None, value: Any) -> pd.Series:
    text = series.fillna("").astype(str)
    if operator == "is_empty":
        return series.isna() | text.str.strip().eq("")
    if operator == "is_not_empty":
        return series.notna() & text.str.strip().ne("")
    if operator == "contains":
        return text.str.contains(str(value), case=False, regex=False, na=False)
    if operator == "not_contains":
        return ~text.str.contains(str(value), case=False, regex=False, na=False)
    if operator in {"greater_than", "greater_or_equal", "less_than", "less_or_equal"}:
        numeric = pd.to_numeric(series, errors="coerce")
        try:
            target = float(value)
        except (TypeError, ValueError) as exc:
            raise TransformationError(f"Filter value '{value}' is not numeric.") from exc
        comparisons = {
            "greater_than": numeric > target,
            "greater_or_equal": numeric >= target,
            "less_than": numeric < target,
            "less_or_equal": numeric <= target,
        }
        return comparisons[operator].fillna(False)
    if operator == "equals":
        return text.str.casefold() == str(value).casefold()
    if operator == "not_equals":
        return text.str.casefold() != str(value).casefold()
    raise TransformationError(f"Unsupported filter operator: {operator}")


def _require_column(frame: pd.DataFrame, column: str | None) -> str:
    _require_columns(frame, [column])
    return str(column)


def _require_columns(frame: pd.DataFrame, columns: list[str | None]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        names = ", ".join(f"'{name}'" for name in missing)
        raise TransformationError(f"Recipe is not compatible: missing column(s) {names}.")


def _selected_columns(frame: pd.DataFrame, columns: list[str] | None) -> list[str]:
    if not columns:
        return []
    _require_columns(frame, columns)
    return columns


def _text_columns(frame: pd.DataFrame, columns: list[str] | None) -> list[str]:
    if columns:
        _require_columns(frame, columns)
        return columns
    return [column for column in frame.columns if frame[column].dtype == object]
