from __future__ import annotations

import io
import json
import re
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
UPLOAD_ID_PATTERN = re.compile(r"^[a-f0-9]{32}\.(csv|xlsx)$")
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_ARCHIVE_FILES = 10_000


class FileValidationError(ValueError):
    """Raised when an uploaded tabular file cannot be safely processed."""


def validate_and_save_upload(
    filename: str | None,
    content: bytes,
    uploads_dir: Path,
    max_upload_mb: int,
) -> tuple[str, str, pd.DataFrame]:
    if not filename:
        raise FileValidationError("The uploaded file needs a filename.")
    safe_filename = sanitize_filename(filename)
    extension = Path(safe_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise FileValidationError("Unsupported file type. Upload a .csv or .xlsx file.")
    if not content:
        raise FileValidationError("The uploaded file is empty.")
    if len(content) > max_upload_mb * 1024 * 1024:
        raise FileValidationError(f"File is larger than the {max_upload_mb} MB limit.")

    try:
        frame = read_dataframe(io.BytesIO(content), extension)
    except FileValidationError:
        raise
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
        json.dumps({"filename": safe_filename}), encoding="utf-8"
    )
    return upload_id, safe_filename, frame


def sanitize_filename(filename: str) -> str:
    """Return a display-safe basename for POSIX or Windows upload paths."""
    safe_filename = Path(filename.replace("\\", "/")).name.strip()
    if not safe_filename:
        raise FileValidationError("The uploaded file needs a filename.")
    return safe_filename


def cleanup_expired_files(
    directories: Iterable[Path], ttl_hours: int, *, now: float | None = None
) -> int:
    """Remove generated upload and result files older than the configured TTL."""
    cutoff = (time.time() if now is None else now) - (ttl_hours * 3600)
    removed = 0
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
    return removed


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
    validate_xlsx_archive(source)
    return pd.read_excel(source, dtype=object, engine="openpyxl")


def validate_xlsx_archive(source: Path | io.BytesIO) -> None:
    """Reject malformed or unexpectedly large XLSX archives before extraction."""
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise FileValidationError(
            "We could not read this XLSX file. Check that it is a valid workbook."
        ) from exc
    finally:
        if hasattr(source, "seek"):
            source.seek(0)

    if len(members) > MAX_XLSX_ARCHIVE_FILES:
        raise FileValidationError("The XLSX file contains too many internal files.")
    if sum(member.file_size for member in members) > MAX_XLSX_UNCOMPRESSED_BYTES:
        raise FileValidationError("The XLSX file expands beyond the 100 MB processing limit.")


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
    # Only server-generated files behind validated random IDs can reach this path.
    return pd.read_pickle(path)  # noqa: S301


def prepare_export(frame: pd.DataFrame) -> pd.DataFrame:
    """Prevent text cells from becoming formulas when opened in spreadsheet software."""
    safe = frame.copy()
    for column in safe.columns:
        safe[column] = safe[column].map(_neutralize_formula)
    return safe


def _neutralize_formula(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(SPREADSHEET_FORMULA_PREFIXES):
        return f"'{value}"
    return value
