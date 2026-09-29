from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from cre_model.inputs import DealAssumptions, DealResults


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _load_config(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as source:
        return json.load(source)


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _percent(value: float | None) -> str:
    return "N/M" if value is None else f"{value:.1%}"


def render_html(
    deal: DealAssumptions,
    results: DealResults,
    image_paths: dict[str, Path] | None = None,
) -> str:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    environment.filters["money"] = _money
    environment.filters["percent"] = _percent
    template = environment.get_template("om.html")
    total_area = deal.rentable_area
    per_unit_uses = results.total_uses / deal.total_units if deal.total_units else 0
    per_sf_uses = results.total_uses / total_area if total_area else 0
    firm = _load_config("firm_profile.json")
    investor_amount = deal.illustrative_investment_amount
    investor_cash_flows = []
    if results.waterfall and results.waterfall.lp_contributions:
        investor_share = investor_amount / results.waterfall.lp_contributions
        grouped: dict[int, dict[str, float]] = {}
        for period_index, period in enumerate(results.waterfall.monthly_periods):
            elapsed_days = (period.date - deal.analysis_start_date).days
            year = 0 if period_index == 0 else max(1, (elapsed_days + 364) // 365)
            row = grouped.setdefault(year, {"contribution": 0.0, "distribution": 0.0})
            row["contribution"] += period.lp_contribution * investor_share
            row["distribution"] += period.lp_distribution * investor_share
        investor_cash_flows = [
            {
                "year": year,
                "contribution": row["contribution"],
                "distribution": row["distribution"],
                "net_cash_flow": row["distribution"] - row["contribution"],
            }
            for year, row in sorted(grouped.items())
        ]
    total_sources = sum(deal.sources.model_dump().values()) + results.total_debt
    total_months = deal.hold_years * 12
    timeline_stages = [
        {"label": "Construction", "start": 0, "width": deal.construction_months / total_months * 100},
        {
            "label": "Lease-up",
            "start": deal.construction_months / total_months * 100,
            "width": max(0, deal.stabilization_month - deal.construction_months) / total_months * 100,
        },
        {
            "label": "Stabilization",
            "start": min(deal.stabilization_month / total_months * 100, 100),
            "width": max(0, total_months - deal.stabilization_month) / total_months * 100,
        },
    ]
    fallback_images = {
        "cover": "backend/cre_model/report/assets/images/exterior.jpg",
        "sponsor": "backend/cre_model/report/assets/images/illustrative-portrait.jpg",
        "market": "backend/cre_model/report/assets/images/urban-context.jpg",
        "location": "backend/cre_model/report/assets/images/urban-context.jpg",
        "site": "backend/cre_model/report/assets/images/kitchen.jpg",
        "property_exterior": "backend/cre_model/report/assets/images/exterior.jpg",
        "property_living_room": "backend/cre_model/report/assets/images/living-room.jpg",
        "property_kitchen": "backend/cre_model/report/assets/images/kitchen.jpg",
        "property_amenity": "backend/cre_model/report/assets/images/amenity.jpg",
        "track_record_exterior": "backend/cre_model/report/assets/images/exterior.jpg",
        "track_record_context": "backend/cre_model/report/assets/images/urban-context.jpg",
    }
    selected_images = image_paths or {}
    images = {
        slot: path.as_uri() if (path := selected_images.get(slot)) else fallback
        for slot, fallback in fallback_images.items()
    }
    uploaded_images = {slot: slot in selected_images for slot in fallback_images}
    return template.render(
        deal=deal,
        results=results,
        firm=firm,
        legal=_load_config("legal.json"),
        theme=_load_config("report_theme.json"),
        sensitivity=results.exit_cap_sensitivity,
        per_unit_uses=per_unit_uses,
        per_sf_uses=per_sf_uses,
        total_sources=total_sources,
        investor_amount=investor_amount,
        investor_cash_flows=investor_cash_flows,
        timeline_stages=timeline_stages,
        unit_mix=deal.unit_mix if deal.property_type == "multifamily" else [],
        rent_roll=deal.rent_roll,
        images=images,
        uploaded_images=uploaded_images,
    )


def render_pdf(
    deal: DealAssumptions,
    results: DealResults,
    output: str | Path,
    image_paths: dict[str, Path] | None = None,
) -> None:
    Path(output).write_bytes(render_pdf_bytes(deal, results, image_paths))


def render_pdf_bytes(
    deal: DealAssumptions,
    results: DealResults,
    image_paths: dict[str, Path] | None = None,
) -> bytes:
    return HTML(string=render_html(deal, results, image_paths), base_url=str(ROOT)).write_pdf()