from __future__ import annotations

import os

from datetime import date

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile

from cre_model.engine import calculate_deal
from cre_model.inputs import DealAssumptions, DealResults
from cre_model.report.render import render_pdf_bytes
from cre_model.rent_roll_import import InvalidRentRollError, preview_rent_roll
from cre_model.storage import DealNotFoundError, DealRepository, InvalidImageError


def create_app(repository: DealRepository | None = None) -> FastAPI:
    store = repository or DealRepository(os.environ.get("CRE_DATABASE_PATH", "data/deals.sqlite3"))
    application = FastAPI(title="CRE Underwriting", version="0.1.0")

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/rent-roll/preview")
    async def preview_uploaded_rent_roll(file: UploadFile = File(...), analysis_date: date = Form(...)) -> dict[str, object]:
        try:
            content = await file.read(10 * 1024 * 1024 + 1)
            return preview_rent_roll(file.filename or "", content, analysis_date)
        except InvalidRentRollError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.get("/api/deals")
    def list_deals() -> list[dict[str, str]]:
        return store.list()

    @application.post("/api/deals", status_code=201)
    def create_deal(deal: DealAssumptions) -> dict[str, str]:
        return {"id": store.save(deal)}

    @application.get("/api/deals/{deal_id}", response_model=DealAssumptions)
    def get_deal(deal_id: str) -> DealAssumptions:
        try:
            return store.get(deal_id)
        except DealNotFoundError as error:
            raise HTTPException(status_code=404, detail="Deal not found") from error

    @application.put("/api/deals/{deal_id}")
    def update_deal(deal_id: str, deal: DealAssumptions) -> dict[str, str]:
        try:
            store.get(deal_id)
        except DealNotFoundError as error:
            raise HTTPException(status_code=404, detail="Deal not found") from error
        store.save(deal, deal_id)
        return {"id": deal_id}

    @application.delete("/api/deals/{deal_id}", status_code=204)
    def delete_deal(deal_id: str) -> Response:
        try:
            store.delete(deal_id)
        except DealNotFoundError as error:
            raise HTTPException(status_code=404, detail="Deal not found") from error
        return Response(status_code=204)

    @application.get("/api/deals/{deal_id}/images")
    def list_images(deal_id: str) -> list[dict[str, str]]:
        try:
            return store.list_images(deal_id)
        except DealNotFoundError as error:
            raise HTTPException(status_code=404, detail="Deal not found") from error

    @application.post("/api/deals/{deal_id}/images", status_code=201)
    async def upload_image(
        deal_id: str,
        slot: str = Form(...),
        caption: str = Form(""),
        file: UploadFile = File(...),
    ) -> dict[str, str]:
        try:
            content = await file.read()
            return store.save_image(deal_id, slot, file.filename or "image", file.content_type or "", content, caption)
        except DealNotFoundError as error:
            raise HTTPException(status_code=404, detail="Deal not found") from error
        except InvalidImageError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.delete("/api/deals/{deal_id}/images/{image_id}", status_code=204)
    def delete_image(deal_id: str, image_id: str) -> Response:
        try:
            store.delete_image(deal_id, image_id)
        except DealNotFoundError as error:
            raise HTTPException(status_code=404, detail="Deal not found") from error
        except InvalidImageError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(status_code=204)

    @application.post("/api/calculate", response_model=DealResults)
    def calculate(deal: DealAssumptions) -> DealResults:
        return calculate_deal(deal)

    @application.post("/api/report")
    def report(deal: DealAssumptions, deal_id: str | None = Query(default=None)) -> Response:
        results = calculate_deal(deal)
        try:
            image_paths = store.image_paths(deal_id) if deal_id else None
        except DealNotFoundError as error:
            raise HTTPException(status_code=404, detail="Deal not found") from error
        return Response(
            content=render_pdf_bytes(deal, results, image_paths),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="offering-memorandum.pdf"'},
        )

    return application


app = create_app()