"""Generate FlowForge's deterministic customer demo dataset."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
FIRST_NAMES = ["Avery", "Maya", "Jonas", "Elena", "Noah", "Amara", "Luca", "Sofia"]
LAST_NAMES = ["Chen", "Patel", "Müller", "Rossi", "Brown", "Okafor", "Silva", "Martin"]
CITIES = [
    ("Zurich", "zh"),
    ("Geneva", "ge"),
    ("Basel", "bs"),
    ("Lausanne", "vd"),
    ("Bern", "be"),
]
DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"]


def make_valid_row(index: int) -> dict[str, str]:
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    last = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
    city, state = CITIES[(index * 7) % len(CITIES)]
    joined = date(2021, 1, 3) + timedelta(days=(index * 13) % 1800)
    padding = " " if index % 4 == 0 else ""
    name_case = str.upper if index % 3 == 0 else (str.lower if index % 3 == 1 else lambda x: x)
    return {
        "customer_id": f"C-{10000 + index}",
        "first_name": f"{padding}{name_case(first)}{padding}",
        "last_name": f"{padding}{name_case(last)}{padding}",
        "email": f"{padding}{first}.{last}{index}@Example.COM{padding}",
        "phone": ""
        if index % 17 == 0
        else f"+41 79 {100 + index % 900:03d} {index % 100:02d} {index * 3 % 100:02d}",
        "city": f"{padding}{name_case(city)}{padding}",
        "state": state if index % 2 else state.upper(),
        "signup_date": joined.strftime(DATE_FORMATS[index % len(DATE_FORMATS)]),
        "lifetime_value": f"{250 + (index * 37) % 12000:,}"
        if index % 5 == 0
        else str(250 + (index * 37) % 12000),
        "segment": ["growth", "core", "enterprise"][index % 3],
    }


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    valid_rows = [make_valid_row(index) for index in range(1187)]
    invalid_rows = [make_valid_row(2000 + index) for index in range(25)]
    for index, row in enumerate(invalid_rows):
        row["lifetime_value"] = ["unknown", "n/a?", "12O0", "—", "pending"][index % 5]
    duplicate_rows = [row.copy() for row in valid_rows[:41]]
    dirty_rows = valid_rows + invalid_rows + duplicate_rows

    fieldnames = list(valid_rows[0])
    with (SAMPLES / "customer_data_dirty.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dirty_rows)

    clean_rows = []
    for row in valid_rows:
        clean = {key: value.strip() for key, value in row.items()}
        for key in ("first_name", "last_name", "email", "city"):
            clean[key] = clean[key].lower()
        clean["state"] = clean["state"].upper()
        clean["signup_date"] = date.fromisoformat(
            (
                date(2021, 1, 3)
                + timedelta(days=(int(clean["customer_id"][2:]) - 10000) * 13 % 1800)
            ).isoformat()
        ).isoformat()
        clean["lifetime_value"] = clean["lifetime_value"].replace(",", "")
        clean["phone"] = clean["phone"] or "Not provided"
        clean_rows.append(clean)

    with (SAMPLES / "customer_data_clean_expected.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(clean_rows)

    print(f"Generated {len(dirty_rows)} dirty rows and {len(clean_rows)} expected clean rows.")


if __name__ == "__main__":
    main()
