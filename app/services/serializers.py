from __future__ import annotations

from app.models import JobRecord, RecipeRecord


def recipe_to_dict(recipe: RecipeRecord) -> dict[str, object]:
    return {
        "id": recipe.id,
        "name": recipe.name,
        "description": recipe.description,
        "operations": recipe.operations,
        "created_at": recipe.created_at.isoformat(),
        "updated_at": recipe.updated_at.isoformat(),
    }


def job_to_dict(job: JobRecord) -> dict[str, object]:
    return {
        "id": job.id,
        "input_filename": job.input_filename,
        "output_filename": job.output_filename,
        "recipe_id": job.recipe_id,
        "status": job.status,
        "stats": job.stats,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
    }
