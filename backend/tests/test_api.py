import json
import base64
import io
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from cre_model.api import create_app
from cre_model.storage import DealRepository


SAMPLE_PATH = Path(__file__).resolve().parents[2] / "sample_deal.json"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_deal_storage_round_trip_and_calculation(tmp_path: Path) -> None:
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    repository = DealRepository(tmp_path / "deals.sqlite3")
    client = TestClient(create_app(repository))

    created = client.post("/api/deals", json=sample)
    assert created.status_code == 201
    deal_id = created.json()["id"]

    loaded = client.get(f"/api/deals/{deal_id}")
    assert loaded.status_code == 200
    assert loaded.json()["property_name"] == sample["property_name"]
    assert client.get("/api/deals").json()[0]["id"] == deal_id

    calculated = client.post("/api/calculate", json=loaded.json())
    assert calculated.status_code == 200
    assert len(calculated.json()["monthly_cash_flows"]) == sample["hold_years"] * 12

    deleted = client.delete(f"/api/deals/{deal_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/deals/{deal_id}").status_code == 404


def test_report_endpoint_returns_pdf(tmp_path: Path) -> None:
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    client = TestClient(create_app(DealRepository(tmp_path / "deals.sqlite3")))

    response = client.post("/api/report", json=sample)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_commercial_report_uses_suite_table_even_with_old_unit_mix(tmp_path: Path) -> None:
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    sample.update({"property_type": "retail", "total_nra_sf": 1000,
                   "rent_roll": [{"name": "Vacant suite", "suite": "B", "area_sf": 1000,
                                  "lease_start": sample["analysis_start_date"],
                                  "lease_end": sample["analysis_start_date"],
                                  "current_rent": 0, "vacant": True,
                                  "market_rent_per_sf": 24}]})
    client = TestClient(create_app(DealRepository(tmp_path / "deals.sqlite3")))

    response = client.post("/api/report", json=sample)

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_deal_images_are_persistent_and_used_by_report(tmp_path: Path) -> None:
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    repository = DealRepository(tmp_path / "deals.sqlite3")
    client = TestClient(create_app(repository))

    deal_id = client.post("/api/deals", json=sample).json()["id"]
    uploaded = client.post(
        f"/api/deals/{deal_id}/images",
        data={"slot": "cover", "caption": "Subject property"},
        files={"file": ("cover.png", PNG_BYTES, "image/png")},
    )

    assert uploaded.status_code == 201
    assert uploaded.json()["slot"] == "cover"
    assert client.get(f"/api/deals/{deal_id}/images").json()[0]["original_name"] == "cover.png"
    report = client.post(f"/api/report?deal_id={deal_id}", json=sample)
    assert report.status_code == 200
    assert report.content.startswith(b"%PDF")

    image_id = uploaded.json()["id"]
    assert client.delete(f"/api/deals/{deal_id}/images/{image_id}").status_code == 204
    assert client.get(f"/api/deals/{deal_id}/images").json() == []


def test_deal_images_reject_unsupported_types(tmp_path: Path) -> None:
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    client = TestClient(create_app(DealRepository(tmp_path / "deals.sqlite3")))
    deal_id = client.post("/api/deals", json=sample).json()["id"]

    response = client.post(
        f"/api/deals/{deal_id}/images",
        data={"slot": "cover"},
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 400


def test_rent_roll_csv_preview_does_not_save_and_flags_missing_rows(tmp_path: Path) -> None:
    client = TestClient(create_app(DealRepository(tmp_path / "deals.sqlite3")))
    csv_file = (
        "suite,tenant,area_sf,lease_start,lease_end,annual_rent,lease_structure\n"
        "A,Store One,1000,2025-01-01,2030-01-01,24000,nnn\n"
        "B,Store Two,500,2025-01-01,2031-01-01,12000,gross\n"
        "C,No rent,200,2025-01-01,2030-01-01,,nnn\n"
    )
    response = client.post("/api/rent-roll/preview", data={"analysis_date": "2026-09-01"},
                           files={"file": ("roll.csv", csv_file, "text/csv")})

    assert response.status_code == 200
    assert len(response.json()["rows"]) == 2
    assert response.json()["rows"][0]["current_rent"] == 24
    assert response.json()["total_area_sf"] == 1500
    assert response.json()["annual_base_rent"] == 36000
    assert "Row 4 skipped" in response.json()["warnings"][0]
    assert client.get("/api/deals").json() == []


def test_rent_roll_xlsx_preview_handles_vacant_rows(tmp_path: Path) -> None:
    workbook = Workbook()
    workbook.active.append(["Suite", "Status", "Area SF", "Market Rent PSF", "Lease Up Date"])
    workbook.active.append(["11", "Vacant", 800, 18, "2027-01-01"])
    content = io.BytesIO()
    workbook.save(content)
    client = TestClient(create_app(DealRepository(tmp_path / "deals.sqlite3")))

    response = client.post("/api/rent-roll/preview", data={"analysis_date": "2026-09-01"},
                           files={"file": ("roll.xlsx", content.getvalue())})

    assert response.status_code == 200
    assert response.json()["rows"][0]["vacant"] is True
    assert response.json()["rows"][0]["lease_up_date"] == "2027-01-01"
    assert response.json()["occupied_area_sf"] == 0


def test_rent_roll_preview_rejects_unsupported_and_scanned_files(tmp_path: Path) -> None:
    client = TestClient(create_app(DealRepository(tmp_path / "deals.sqlite3")))
    for filename, content in (("roll.txt", b"hello"), ("roll.pdf", b"%PDF-1.4\n%%EOF"),
                              ("roll.csv", b"a" * (10 * 1024 * 1024 + 1))):
        response = client.post("/api/rent-roll/preview", data={"analysis_date": "2026-09-01"},
                               files={"file": (filename, content)})
        assert response.status_code == 400