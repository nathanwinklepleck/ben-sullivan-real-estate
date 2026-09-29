from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cre_model.inputs import DealAssumptions


IMAGE_SLOTS = {
    "cover",
    "sponsor",
    "market",
    "location",
    "site",
    "property_exterior",
    "property_living_room",
    "property_kitchen",
    "property_amenity",
    "track_record_exterior",
    "track_record_context",
}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class DealNotFoundError(LookupError):
    pass


class InvalidImageError(ValueError):
    pass


class DealRepository:
    def __init__(self, database_path: str | Path = "data/deals.sqlite3") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.image_directory = self.database_path.parent / f"{self.database_path.stem}-images"
        self.image_directory.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS deals (
                    id TEXT PRIMARY KEY,
                    property_name TEXT NOT NULL,
                    assumptions_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS deal_images (
                    id TEXT PRIMARY KEY,
                    deal_id TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    caption TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(deal_id, slot)
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def list(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, property_name, updated_at FROM deals ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, deal_id: str) -> DealAssumptions:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT assumptions_json FROM deals WHERE id = ?", (deal_id,)
            ).fetchone()
        if row is None:
            raise DealNotFoundError(deal_id)
        return DealAssumptions.model_validate_json(row["assumptions_json"])

    def save(self, deal: DealAssumptions, deal_id: str | None = None) -> str:
        selected_id = deal_id or str(uuid4())
        updated_at = datetime.now(timezone.utc).isoformat()
        assumptions_json = json.dumps(deal.model_dump(mode="json"))
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO deals (id, property_name, assumptions_json, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     property_name = excluded.property_name,
                     assumptions_json = excluded.assumptions_json,
                     updated_at = excluded.updated_at""",
                (selected_id, deal.property_name, assumptions_json, updated_at),
            )
        return selected_id

    def delete(self, deal_id: str) -> None:
        with self._connect() as connection:
            image_rows = connection.execute(
                "SELECT stored_name FROM deal_images WHERE deal_id = ?", (deal_id,)
            ).fetchall()
            result = connection.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
            connection.execute("DELETE FROM deal_images WHERE deal_id = ?", (deal_id,))
        if result.rowcount == 0:
            raise DealNotFoundError(deal_id)
        for row in image_rows:
            (self.image_directory / row["stored_name"]).unlink(missing_ok=True)

    def list_images(self, deal_id: str) -> list[dict[str, str]]:
        self._ensure_deal(deal_id)
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, slot, original_name, content_type, caption, created_at
                   FROM deal_images WHERE deal_id = ? ORDER BY slot""",
                (deal_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_image(
        self,
        deal_id: str,
        slot: str,
        original_name: str,
        content_type: str,
        content: bytes,
        caption: str = "",
    ) -> dict[str, str]:
        self._ensure_deal(deal_id)
        if slot not in IMAGE_SLOTS:
            raise InvalidImageError("Unknown report image slot")
        if content_type not in IMAGE_TYPES:
            raise InvalidImageError("Only JPEG, PNG, and WebP images are supported")
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise InvalidImageError("Images must be between 1 byte and 10 MB")

        image_id = str(uuid4())
        extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
        stored_name = f"{image_id}{extension}"
        target = self.image_directory / stored_name
        with self._connect() as connection:
            previous = connection.execute(
                "SELECT stored_name FROM deal_images WHERE deal_id = ? AND slot = ?",
                (deal_id, slot),
            ).fetchone()
            connection.execute(
                """INSERT INTO deal_images
                   (id, deal_id, slot, stored_name, original_name, content_type, caption, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?) 
                   ON CONFLICT(deal_id, slot) DO UPDATE SET
                     id = excluded.id, stored_name = excluded.stored_name,
                     original_name = excluded.original_name, content_type = excluded.content_type,
                     caption = excluded.caption, created_at = excluded.created_at""",
                (image_id, deal_id, slot, stored_name, Path(original_name).name, content_type, caption.strip(), datetime.now(timezone.utc).isoformat()),
            )
        target.write_bytes(content)
        if previous:
            (self.image_directory / previous["stored_name"]).unlink(missing_ok=True)
        return {"id": image_id, "slot": slot, "original_name": Path(original_name).name, "content_type": content_type, "caption": caption.strip()}

    def delete_image(self, deal_id: str, image_id: str) -> None:
        self._ensure_deal(deal_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT stored_name FROM deal_images WHERE id = ? AND deal_id = ?",
                (image_id, deal_id),
            ).fetchone()
            if row is None:
                raise InvalidImageError("Image not found")
            connection.execute("DELETE FROM deal_images WHERE id = ?", (image_id,))
        (self.image_directory / row["stored_name"]).unlink(missing_ok=True)

    def image_paths(self, deal_id: str) -> dict[str, Path]:
        self._ensure_deal(deal_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT slot, stored_name FROM deal_images WHERE deal_id = ?", (deal_id,)
            ).fetchall()
        return {row["slot"]: self.image_directory / row["stored_name"] for row in rows}

    def _ensure_deal(self, deal_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM deals WHERE id = ?", (deal_id,)).fetchone()
        if row is None:
            raise DealNotFoundError(deal_id)