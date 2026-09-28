from __future__ import annotations

import io
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.db import Database
from app.schemas import ExportRequest, Operation, RecipeCreate, TransformRequest
from app.services.files import (
    FileValidationError,
    dataframe_preview,
    get_upload_filename,
    load_result,
    load_upload,
    save_result,
    validate_and_save_upload,
)
from app.services.serializers import job_to_dict, recipe_to_dict
from app.services.transformer import TransformationError, transform_dataframe

router = APIRouter(prefix="/api", tags=["data workflows"])


def _db(request: Request) -> Database:
    return request.app.state.database


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request, file: Annotated[UploadFile, File(description="CSV or XLSX file")]
) -> dict[str, object]:
    settings = request.app.state.settings
    content = await file.read()
    try:
        upload_id, frame = validate_and_save_upload(
            file.filename, content, settings.uploads_dir, settings.max_upload_mb
        )
    except FileValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    preview = dataframe_preview(frame, settings.preview_rows)
    return {"upload_id": upload_id, "filename": file.filename, **preview}


@router.post("/preview")
def preview_transform(request: Request, payload: TransformRequest) -> dict[str, object]:
    settings = request.app.state.settings
    database = _db(request)
    recipe_id = payload.recipe_id
    operations = payload.operations

    if recipe_id is not None:
        recipe = database.get_recipe(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="Recipe not found.")
        operations = [Operation.model_validate(item) for item in recipe.operations]

    assert operations is not None
    job_id = uuid4().hex
    input_name = get_upload_filename(payload.upload_id, settings.uploads_dir)
    try:
        frame = load_upload(payload.upload_id, settings.uploads_dir)
        transformed = transform_dataframe(frame, operations)
        result_id = save_result(transformed.dataframe, settings.results_dir)
        output_name = f"processed-{Path(input_name).stem}"
        database.create_job(
            job_id=job_id,
            input_filename=input_name,
            output_filename=output_name,
            recipe_id=recipe_id,
            status="completed",
            stats=transformed.stats.as_dict(),
        )
    except (FileValidationError, FileNotFoundError, TransformationError) as exc:
        database.create_job(
            job_id=job_id,
            input_filename=input_name,
            output_filename=None,
            recipe_id=recipe_id,
            status="failed",
            stats={},
            error_message=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "result_id": result_id,
        "job_id": job_id,
        "before": dataframe_preview(frame, settings.preview_rows),
        "after": dataframe_preview(transformed.dataframe, settings.preview_rows),
        "stats": transformed.stats.as_dict(),
    }


@router.post("/exports")
def export_result(request: Request, payload: ExportRequest) -> StreamingResponse:
    settings = request.app.state.settings
    try:
        frame = load_result(payload.result_id, settings.results_dir)
    except (FileValidationError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    buffer = io.BytesIO()
    if payload.format == "csv":
        frame.to_csv(buffer, index=False)
        media_type = "text/csv"
    else:
        frame.to_excel(buffer, index=False, engine="openpyxl")
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="flowforge-export.{payload.format}"'
        },
    )


@router.get("/recipes")
def list_recipes(request: Request) -> list[dict[str, object]]:
    return [recipe_to_dict(recipe) for recipe in _db(request).list_recipes()]


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
def create_recipe(request: Request, payload: RecipeCreate) -> dict[str, object]:
    try:
        recipe = _db(request).create_recipe(
            payload.name,
            payload.description,
            [operation.model_dump(mode="json") for operation in payload.operations],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return recipe_to_dict(recipe)


@router.get("/recipes/{recipe_id}")
def get_recipe(request: Request, recipe_id: int) -> dict[str, object]:
    recipe = _db(request).get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    return recipe_to_dict(recipe)


@router.delete(
    "/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_recipe(request: Request, recipe_id: int) -> Response:
    if not _db(request).delete_recipe(recipe_id):
        raise HTTPException(status_code=404, detail="Recipe not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs")
def list_jobs(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, object]]:
    return [job_to_dict(job) for job in _db(request).list_jobs(limit)]
