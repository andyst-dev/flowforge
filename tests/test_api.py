from __future__ import annotations

import io
import tomllib
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import __version__


def upload_csv(client: TestClient) -> dict[str, object]:
    content = (
        b"name,email,amount\n"
        b" Alice ,A@EXAMPLE.COM,100\n"
        b" Alice ,A@EXAMPLE.COM,100\n"
        b"Bob,b@example.com,bad\n"
    )
    response = client.post("/api/uploads", files={"file": ("customers.csv", content, "text/csv")})
    assert response.status_code == 201
    return response.json()


def test_health_and_dashboard(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "Turn messy tables" in response.text
    assert "MAX 2 MB" in response.text
    assert "Try demo data" in response.text
    assert "Sales report cleanup" in response.text
    assert "Inventory catalog cleanup" in response.text
    assert response.text.count("data-sample-url") == 3
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


@pytest.mark.parametrize(
    ("dataset_name", "recipe_name", "expected_recipe", "expected_stats"),
    [
        (
            "customer_data_dirty.csv",
            "customer_cleanup_recipe.json",
            "Customer export cleanup",
            {
                "input_rows": 1_253,
                "output_rows": 1_187,
                "duplicates_removed": 41,
                "empty_rows_removed": 0,
                "invalid_rows": 25,
                "changed_cells": 6_776,
            },
        ),
        (
            "sales_report_dirty.csv",
            "sales_report_recipe.json",
            "Sales report cleanup",
            {
                "input_rows": 18,
                "output_rows": 11,
                "duplicates_removed": 2,
                "empty_rows_removed": 0,
                "invalid_rows": 3,
                "changed_cells": 73,
            },
        ),
        (
            "inventory_dirty.csv",
            "inventory_cleanup_recipe.json",
            "Inventory catalog cleanup",
            {
                "input_rows": 16,
                "output_rows": 14,
                "duplicates_removed": 2,
                "empty_rows_removed": 0,
                "invalid_rows": 2,
                "changed_cells": 62,
            },
        ),
    ],
)
def test_demo_assets_load_and_apply(
    client: TestClient,
    dataset_name: str,
    recipe_name: str,
    expected_recipe: str,
    expected_stats: dict[str, int],
) -> None:
    dataset = client.get(f"/samples/{dataset_name}")
    recipe = client.get(f"/samples/{recipe_name}")

    assert dataset.status_code == 200
    assert recipe.status_code == 200
    assert recipe.json()["name"] == expected_recipe

    uploaded = client.post(
        "/api/uploads",
        files={"file": (dataset_name, dataset.content, "text/csv")},
    )
    assert uploaded.status_code == 201

    preview = client.post(
        "/api/preview",
        json={
            "upload_id": uploaded.json()["upload_id"],
            "operations": recipe.json()["operations"],
        },
    )
    assert preview.status_code == 200
    assert preview.json()["stats"] == expected_stats
    assert preview.json()["before"]["total_rows"] == expected_stats["input_rows"]
    assert preview.json()["after"]["total_rows"] == expected_stats["output_rows"]


def test_version_is_consistent_across_package_metadata_and_api(client: TestClient) -> None:
    root = Path(__file__).resolve().parent.parent
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == "1.0.0"
    assert project["project"]["version"] == __version__
    assert client.get("/openapi.json").json()["info"]["version"] == __version__


def test_upload_preview_export_and_history(client: TestClient) -> None:
    uploaded = upload_csv(client)
    assert uploaded["total_rows"] == 3
    assert uploaded["columns"] == ["name", "email", "amount"]

    response = client.post(
        "/api/preview",
        json={
            "upload_id": uploaded["upload_id"],
            "operations": [
                {"type": "trim_whitespace"},
                {"type": "lowercase", "columns": ["email"]},
                {"type": "convert_numeric", "column": "amount", "invalid": "drop"},
                {"type": "drop_duplicates"},
            ],
        },
    )
    assert response.status_code == 200
    preview = response.json()
    assert preview["stats"]["input_rows"] == 3
    assert preview["stats"]["output_rows"] == 1
    assert preview["stats"]["duplicates_removed"] == 1
    assert preview["stats"]["invalid_rows"] == 1
    assert preview["after"]["rows"][0]["email"] == "a@example.com"

    csv_export = client.post(
        "/api/exports", json={"result_id": preview["result_id"], "format": "csv"}
    )
    assert csv_export.status_code == 200
    assert "a@example.com" in csv_export.text

    xlsx_export = client.post(
        "/api/exports", json={"result_id": preview["result_id"], "format": "xlsx"}
    )
    assert xlsx_export.status_code == 200
    frame = pd.read_excel(io.BytesIO(xlsx_export.content))
    assert frame.to_dict(orient="records")[0]["name"] == "Alice"

    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "completed"


def test_recipe_crud_and_reuse(client: TestClient) -> None:
    uploaded = upload_csv(client)
    recipe_payload = {
        "name": "Normalize emails",
        "description": "Trim and lowercase incoming contact data.",
        "operations": [
            {"type": "trim_whitespace"},
            {"type": "lowercase", "columns": ["email"]},
        ],
    }
    created = client.post("/api/recipes", json=recipe_payload)
    assert created.status_code == 201
    recipe_id = created.json()["id"]
    assert client.get("/api/recipes").json()[0]["name"] == "Normalize emails"

    preview = client.post(
        "/api/preview", json={"upload_id": uploaded["upload_id"], "recipe_id": recipe_id}
    )
    assert preview.status_code == 200
    assert preview.json()["after"]["rows"][0]["email"] == "a@example.com"

    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404


def test_invalid_files_and_incompatible_recipes_return_clear_errors(client: TestClient) -> None:
    response = client.post("/api/uploads", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 422
    assert "Unsupported file type" in response.json()["detail"]

    uploaded = upload_csv(client)
    response = client.post(
        "/api/preview",
        json={
            "upload_id": uploaded["upload_id"],
            "operations": [{"type": "uppercase", "columns": ["missing_column"]}],
        },
    )
    assert response.status_code == 422
    assert "not compatible" in response.json()["detail"]
    assert client.get("/api/jobs").json()[0]["status"] == "failed"


def test_xlsx_upload_and_corrupt_workbook_handling(client: TestClient) -> None:
    workbook = io.BytesIO()
    pd.DataFrame({"customer": ["Ada", "Grace"], "spend": [120, 240]}).to_excel(
        workbook, index=False
    )

    response = client.post(
        "/api/uploads",
        files={
            "file": (
                "customers.xlsx",
                workbook.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201
    assert response.json()["columns"] == ["customer", "spend"]
    assert response.json()["total_rows"] == 2

    corrupt = client.post(
        "/api/uploads",
        files={"file": ("broken.xlsx", b"not a workbook", "application/octet-stream")},
    )
    assert corrupt.status_code == 422
    assert "could not read" in corrupt.json()["detail"]


def test_upload_limit_is_enforced(client: TestClient) -> None:
    oversized = b"value\n" + (b"x" * (2 * 1024 * 1024))
    response = client.post("/api/uploads", files={"file": ("oversized.csv", oversized, "text/csv")})

    assert response.status_code == 422
    assert response.json()["detail"] == "File is larger than the 2 MB limit."


def test_exports_neutralize_spreadsheet_formulas(client: TestClient) -> None:
    uploaded = client.post(
        "/api/uploads",
        files={"file": ("formulas.csv", b"name,note\nAda,=2+2\n", "text/csv")},
    ).json()
    preview = client.post(
        "/api/preview",
        json={
            "upload_id": uploaded["upload_id"],
            "operations": [{"type": "trim_whitespace"}],
        },
    ).json()

    csv_export = client.post(
        "/api/exports", json={"result_id": preview["result_id"], "format": "csv"}
    )
    assert "'=2+2" in csv_export.text

    xlsx_export = client.post(
        "/api/exports", json={"result_id": preview["result_id"], "format": "xlsx"}
    )
    frame = pd.read_excel(io.BytesIO(xlsx_export.content), dtype=object)
    assert frame.loc[0, "note"] == "'=2+2"
