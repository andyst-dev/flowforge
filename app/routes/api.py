from __future__ import annotations

import io
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.db import Database
from app.schemas import (
    ExportRequest,
    JobResponse,
    Operation,
    RecipeCreate,
    RecipeResponse,
    TransformRequest,
    TransformResponse,
    UploadResponse,
)
from app.services.files import (
    FileValidationError,
    cleanup_expired_files,
    dataframe_preview,
    get_upload_filename,
    load_result,
    load_upload,
    prepare_export,
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


@router.post("/uploads", status_code=status.HTTP_201_CREATED, response_model=UploadResponse)
async def upload_file(
    request: Request, file: Annotated[UploadFile, File(description="CSV or XLSX file")]
) -> dict[str, object]:
    settings = request.app.state.settings
    max_bytes = settings.max_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    cleanup_expired_files((settings.uploads_dir, settings.results_dir), settings.file_ttl_hours)
    try:
        upload_id, filename, frame = validate_and_save_upload(
            file.filename, content, settings.uploads_dir, settings.max_upload_mb
        )
    except FileValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    preview = dataframe_preview(frame, settings.preview_rows)
    return {"upload_id": upload_id, "filename": filename, **preview}


@router.post("/preview", response_model=TransformResponse)
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

    if operations is None:
        raise HTTPException(status_code=422, detail="No transformation operations were provided.")
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
    export_frame = prepare_export(frame)
    if payload.format == "csv":
        export_frame.to_csv(buffer, index=False)
        media_type = "text/csv"
    else:
        export_frame.to_excel(buffer, index=False, engine="openpyxl")
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="flowforge-export.{payload.format}"'
        },
    )


@router.get("/recipes", response_model=list[RecipeResponse])
def list_recipes(request: Request) -> list[dict[str, object]]:
    return [recipe_to_dict(recipe) for recipe in _db(request).list_recipes()]


@router.post("/recipes", status_code=status.HTTP_201_CREATED, response_model=RecipeResponse)
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


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
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


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, object]]:
    return [job_to_dict(job) for job in _db(request).list_jobs(limit)]
