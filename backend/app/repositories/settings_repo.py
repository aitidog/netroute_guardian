"""Repository for persisted runtime key-value AppSetting records."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import AppSetting


class SettingsRepository:
    """Encapsulates all database access for ``app_settings``."""

    def __init__(self, db: Session) -> None:
        self._db = db

    async def get_int(self, key: str, default: int) -> int:
        rec = self._db.get(AppSetting, key)
        if rec is None:
            return default
        try:
            return int(rec.value)
        except ValueError:
            return default

    async def ensure_default(
        self,
        *,
        key: str,
        value: str,
        description: str = "",
    ) -> None:
        if self._db.get(AppSetting, key) is None:
            self._db.add(AppSetting(key=key, value=value, description=description))

    async def upsert_many(self, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            rec = self._db.get(AppSetting, key)
            if rec is None:
                self._db.add(AppSetting(key=key, value=value))
            else:
                rec.value = value
        self._db.commit()
