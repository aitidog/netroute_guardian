"""Repository for user-managed pre-specified ImportantRoute entries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.models.entities import ImportantRoute


class ImportantRouteRepository:
    """Encapsulates all database access for ``important_routes``."""

    def __init__(self, db: Session) -> None:
        self._db = db

    async def list_all(self) -> list[ImportantRoute]:
        return list(self._db.scalars(select(ImportantRoute).order_by(ImportantRoute.created_at.asc())).all())

    async def list_enabled_prefixes(self) -> list[str]:
        return list(
            self._db.scalars(select(ImportantRoute.prefix).where(ImportantRoute.enabled.is_(True))).all()
        )

    async def get_by_id(self, route_id: int) -> ImportantRoute | None:
        return self._db.get(ImportantRoute, route_id)

    async def get_by_prefix(self, prefix: str) -> ImportantRoute | None:
        return self._db.scalar(select(ImportantRoute).where(ImportantRoute.prefix == prefix))

    async def create(
        self,
        *,
        prefix: str,
        description: str = "",
        enabled: bool = True,
        commit: bool = True,
    ) -> ImportantRoute:
        rec = ImportantRoute(prefix=prefix, description=description, enabled=enabled)
        self._db.add(rec)
        try:
            if commit:
                self._db.commit()
                self._db.refresh(rec)
            else:
                self._db.flush()
        except IntegrityError as exc:
            self._db.rollback()
            raise ConflictError(f"Important route '{prefix}' already exists") from exc
        return rec

    async def update(
        self,
        route_id: int,
        *,
        prefix: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> ImportantRoute:
        rec = self._db.get(ImportantRoute, route_id)
        if rec is None:
            raise ResourceNotFoundError("Important route not found")

        if prefix is not None:
            rec.prefix = prefix
        if description is not None:
            rec.description = description
        if enabled is not None:
            rec.enabled = enabled

        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise ConflictError(f"Important route '{prefix}' already exists") from exc
        self._db.refresh(rec)
        return rec

    async def delete(self, route_id: int) -> None:
        rec = self._db.get(ImportantRoute, route_id)
        if rec is None:
            raise ResourceNotFoundError("Important route not found")
        self._db.delete(rec)
        self._db.commit()
