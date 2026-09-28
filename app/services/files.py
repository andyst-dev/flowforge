from __future__ import annotations

import io
import json
import re
from pathlib import Path
from uuid import uuid4

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
UPLOAD_ID_PATTERN = re.compile(r"^[a-f0-9]{32}\.(csv|xlsx)$")


class FileValidationError(ValueError):
    """Raised when an uploaded tabular file cannot be safely processed."""


def validate_and_save_upload(
    filename: str | None,
    content: bytes,
    uploads_dir: Path,
    max_upload_mb: int,
) -> tuple[str, pd.DataFrame]:
    if not filename:
        raise FileValidationError("The uploaded file needs a filename.")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise FileValidationError("Unsupported file type. Upload a .csv or .xlsx file.")
    if not content:
        raise FileValidationError("The uploaded file is empty.")
    if len(content) > max_upload_mb * 1024 * 1024:
        raise FileValidationError(f"File is larger than the {max_upload_mb} MB limit.")

    try:
        frame = read_dataframe(io.BytesIO(content), extension)
    except Exception as exc:
        raise FileValidationError(
            "We could not read this file. Check that it is a valid, "
            "non-password-protected CSV or XLSX file."
        ) from exc

    if not len(frame.columns):
        raise FileValidationError("The file does not contain any columns.")

    upload_id = f"{uuid4().hex}{extension}"
    (uploads_dir / upload_id).write_bytes(content)
    (uploads_dir / f"{upload_id}.json").write_text(
        json.dumps({"filename": Path(filename).name}), encoding="utf-8"
    )
    return upload_id, frame


def load_upload(upload_id: str, uploads_dir: Path) -> pd.DataFrame:
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
        raise FileValidationError("Invalid upload identifier.")
    path = uploads_dir / upload_id
    if not path.is_file():
        raise FileNotFoundError("The uploaded file is no longer available. Upload it again.")
    try:
        return read_dataframe(path, path.suffix)
    except Exception as exc:
        raise FileValidationError("The stored file can no longer be read.") from exc


def get_upload_filename(upload_id: str, uploads_dir: Path) -> str:
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
        return upload_id
    metadata_path = uploads_dir / f"{upload_id}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return str(metadata["filename"])
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return upload_id


def read_dataframe(source: Path | io.BytesIO, extension: str) -> pd.DataFrame:
    if extension == ".csv":
        try:
            return pd.read_csv(source, dtype=object, keep_default_na=True)
        except UnicodeDecodeError:
            if hasattr(source, "seek"):
                source.seek(0)
            return pd.read_csv(source, dtype=object, encoding="latin-1", keep_default_na=True)
    return pd.read_excel(source, dtype=object, engine="openpyxl")


def dataframe_preview(frame: pd.DataFrame, rows: int) -> dict[str, object]:
    preview = frame.head(rows).copy().astype("string").fillna("").astype(str)
    return {
        "columns": [str(column) for column in frame.columns],
        "rows": preview.to_dict(orient="records"),
        "total_rows": len(frame),
    }


def save_result(frame: pd.DataFrame, results_dir: Path) -> str:
    result_id = uuid4().hex
    frame.to_pickle(results_dir / f"{result_id}.pkl")
    return result_id


def load_result(result_id: str, results_dir: Path) -> pd.DataFrame:
    if not re.fullmatch(r"[a-f0-9]{32}", result_id):
        raise FileValidationError("Invalid result identifier.")
    path = results_dir / f"{result_id}.pkl"
    if not path.is_file():
        raise FileNotFoundError("This preview has expired. Run the transformation again.")
    return pd.read_pickle(path)
