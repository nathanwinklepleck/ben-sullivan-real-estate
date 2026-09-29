from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from itertools import islice
from pathlib import Path

from openpyxl import load_workbook
from pydantic import ValidationError
from pypdf import PdfReader

from cre_model.inputs import TenantAssumptions


class InvalidRentRollError(ValueError):
    pass


def _number(value: object) -> float:
    try:
        return float(str(value).strip().replace(",", "").replace("$", ""))
    except (TypeError, ValueError) as error:
        raise InvalidRentRollError(f"Invalid numeric value: {value}") from error


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for format_string in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(str(value).strip(), format_string).date()
        except ValueError:
            continue
    raise InvalidRentRollError(f"Invalid date: {value}")


def _header(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _column(row: dict[str, object], *names: str) -> object:
    return next((row[name] for name in names if row.get(name) not in (None, "")), None)


def _tabular(content: bytes, suffix: str, analysis_date: date) -> tuple[list[TenantAssumptions], list[str]]:
    if suffix == ".csv":
        try:
            table = list(islice(csv.reader(io.StringIO(content.decode("utf-8-sig"))), 502))
        except UnicodeDecodeError as error:
            raise InvalidRentRollError("CSV must be UTF-8 encoded") from error
    else:
        try:
            book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            table = list(islice(book.active.values, 502))
            book.close()
        except Exception as error:
            raise InvalidRentRollError("Cannot read XLSX spreadsheet") from error
    if not table:
        raise InvalidRentRollError("Rent roll has no rows")
    if len(table) > 501:
        raise InvalidRentRollError("Rent roll exceeds the 500-suite limit")
    headers = [_header(cell) for cell in table[0]]
    rows: list[TenantAssumptions] = []
    warnings: list[str] = []
    for index, values in enumerate(table[1:], start=2):
        row = dict(zip(headers, values))
        if not any(value not in (None, "") for value in values):
            continue
        try:
            name = _column(row, "tenant", "tenant_name", "name")
            suite = _column(row, "suite", "unit", "unit_number")
            area = _column(row, "area_sf", "area", "sf", "square_feet", "rentable_area")
            annual = _column(row, "annual_rent", "annual_base_rent")
            monthly = _column(row, "monthly_rent", "monthly_base_rent")
            per_sf = _column(row, "rent_per_sf", "rent_psf", "current_rent")
            vacant = str(_column(row, "vacant", "status") or "").strip().lower() in ("true", "yes", "vacant", "1")
            if area is None or (not vacant and (not name or all(value is None for value in (annual, monthly, per_sf)))):
                raise InvalidRentRollError("Missing area, tenant, or base rent")
            area_sf = _number(area)
            rent = 0 if vacant else _number(per_sf) if per_sf is not None else _number(monthly) if monthly is not None else _number(annual) / area_sf
            basis = "per_month" if monthly is not None and per_sf is None else "per_sf_year"
            start = _column(row, "lease_start", "lease_from", "start_date")
            end = _column(row, "lease_end", "lease_to", "expiration", "expiration_date")
            if not vacant and (start is None or end is None):
                raise InvalidRentRollError("Missing lease start or expiration")
            if vacant:
                warnings.append(f"Row {index}: set market rent and lease-up date before forecasting this vacant suite")
            structure = str(_column(row, "lease_structure", "structure", "lease_type") or "nnn").strip().lower().replace(" ", "_")
            tenant = TenantAssumptions.model_validate({
                "name": str(name or f"Vacant {suite or index}"), "suite": str(suite or ""),
                "area_sf": area_sf, "lease_start": _date(start) if start else analysis_date,
                "lease_end": _date(end) if end else analysis_date,
                "current_rent": 0 if vacant else rent, "vacant": vacant, "rent_basis": basis,
                "lease_structure": structure, "market_rent_per_sf": _number(_column(row, "market_rent_per_sf", "market_rent_psf") or 0),
                "lease_up_date": _date(row["lease_up_date"]) if row.get("lease_up_date") else None,
            })
            rows.append(tenant)
        except (InvalidRentRollError, ValidationError, ZeroDivisionError) as error:
            warnings.append(f"Row {index} skipped: {error}")
    return rows, warnings


DATE = r"\d{1,2}/\d{1,2}/\d{4}"
MONEY = r"[\d,]+\.\d{2}"


def _pdf(content: bytes, analysis_date: date) -> tuple[list[TenantAssumptions], list[str]]:
    try:
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > 50:
            raise InvalidRentRollError("PDF exceeds the 50-page limit")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except InvalidRentRollError:
        raise
    except Exception as error:
        raise InvalidRentRollError("Cannot read PDF") from error
    if not text.strip():
        raise InvalidRentRollError("PDF contains no selectable text; scanned files need OCR")
    text = re.sub(r"(\d[\d,]*\.\d)\s*\n\s*(\d)\b", r"\1\2", text)
    text = re.sub(r"(\d{1,2}/\d{1,2})\s*\n\s*(/\d{4})", r"\1\2", text)
    groups: list[str] = []
    for line in text.splitlines():
        if re.match(r"^\d+[\d-]*\s+.+?\s+(?:NNN|NN|Gross)\s+" + DATE, line, re.I):
            groups.append(line)
        elif groups:
            groups[-1] += " " + line
    rows: list[TenantAssumptions] = []
    warnings: list[str] = []
    for group in groups:
        header = re.match(r"^(\d+[\d-]*)\s+(.+?)\s+(NNN|NN|Gross)\s+(" + DATE + r")\s+(" + DATE + r")\s+(" + MONEY + r")", group, re.I)
        current = re.search(r"\bCurrent\s+(" + MONEY + r")", group)
        if not header or not current:
            warnings.append(f"Could not read tenant row: {group[:90]}")
            continue
        suite, name, structure, start, end, area = header.groups()
        area_sf = _number(area)
        try:
            tenant = TenantAssumptions(
                name=name, suite=suite, lease_structure=structure.lower(),
                lease_start=_date(start), lease_end=_date(end), area_sf=area_sf,
                current_rent=_number(current.group(1)) / area_sf,
            )
        except (ValidationError, InvalidRentRollError) as error:
            warnings.append(f"Suite {suite} skipped: {error}")
            continue
        for change in re.finditer(r"(?:Increase|New Lease)\s+(.+?)\s+(" + MONEY + r")(?=\s+(?:" + MONEY + r"|\d+[\d-]*\s+.+?\s+NNN)|$)", group):
            dates = re.findall(DATE, change.group(1))
            if not dates:
                warnings.append(f"Suite {suite}: increase has no effective date")
                continue
            effective = _date(dates[-1])
            if effective <= analysis_date or effective > tenant.lease_end or "Submitted extension request" in name:
                warnings.append(f"Suite {suite}: verify proposed increase or extension on {effective}")
                continue
            data = tenant.model_dump()
            data["rent_steps"].append({"effective_date": effective, "rent": _number(change.group(2)) / area_sf})
            tenant = TenantAssumptions.model_validate(data)
        rows.append(tenant)
    if not rows:
        raise InvalidRentRollError("No current tenant rows found in PDF; upload a CSV/XLSX or review the PDF layout")
    stated = re.search(r"Current Base Rent\s+\$(" + MONEY + r")", text)
    if stated and abs(sum(row.current_rent * row.area_sf for row in rows) - _number(stated.group(1))) > 1:
        warnings.append(f"Current rent total differs from PDF's stated ${stated.group(1)}; verify source rows")
    return rows, warnings


def preview_rent_roll(filename: str, content: bytes, analysis_date: date) -> dict[str, object]:
    suffix = Path(filename).suffix.lower()
    if suffix not in (".csv", ".xlsx", ".pdf"):
        raise InvalidRentRollError("Upload a CSV, XLSX, or text-extractable PDF")
    if not content or len(content) > 10 * 1024 * 1024:
        raise InvalidRentRollError("File must be nonempty and no larger than 10 MB")
    rows, warnings = _pdf(content, analysis_date) if suffix == ".pdf" else _tabular(content, suffix, analysis_date)
    if not rows:
        raise InvalidRentRollError("No valid tenant rows found")
    if len(rows) > 500:
        raise InvalidRentRollError("Rent roll exceeds the 500-suite limit")
    suites = [row.suite for row in rows if row.suite]
    for suite in sorted(set(suites)):
        if suites.count(suite) > 1:
            warnings.append(f"Suite {suite} appears more than once; verify area and ownership")
    return {
        "rows": [row.model_dump(mode="json") for row in rows],
        "warnings": warnings,
        "total_area_sf": sum(row.area_sf for row in rows),
        "occupied_area_sf": sum(row.area_sf for row in rows if not row.vacant),
        "annual_base_rent": sum(row.current_rent * (row.area_sf if row.rent_basis == "per_sf_year" else 12) for row in rows),
    }