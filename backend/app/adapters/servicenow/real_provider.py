"""Production ServiceNow Table API provider using async HTTP."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.adapters.servicenow.base import ServiceNowChangeDTO, ServiceNowProvider

logger = logging.getLogger(__name__)


class RealServiceNowProvider(ServiceNowProvider):
    """Queries live ServiceNow Change Requests, associated CIs, and assignee emails."""

    def __init__(
        self,
        instance_url: str,
        username: str,
        password: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds

    @property
    def source_name(self) -> str:
        return "live"

    async def fetch_scheduled_changes(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ServiceNowChangeDTO]:
        if not self.instance_url:
            raise ValueError("SERVICENOW_INSTANCE_URL must be configured in live mode")

        start_str = window_start.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        end_str = window_end.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        query = f"category=Network^start_date>={start_str}^start_date<={end_str}^stateIN-2,-1,0,3"

        async with httpx.AsyncClient(
            base_url=self.instance_url,
            auth=(self.username, self.password),
            timeout=self.timeout_seconds,
            headers={"Accept": "application/json"},
        ) as client:
            resp = await client.get(
                "/api/now/table/change_request",
                params={
                    "sysparm_query": query,
                    "sysparm_display_value": "all",
                    "sysparm_fields": (
                        "sys_id,number,short_description,description,start_date,end_date,state,assigned_to"
                    ),
                },
            )
            resp.raise_for_status()
            rows = resp.json().get("result", [])

            changes: list[ServiceNowChangeDTO] = []
            for row in rows:
                sys_id = _val(row.get("sys_id"))
                ci_hostnames = await self._fetch_ci_hostnames(client, sys_id)
                engineer_name, engineer_email = await self._fetch_assignee(client, row.get("assigned_to"))
                changes.append(
                    ServiceNowChangeDTO(
                        chg_number=_val(row.get("number")),
                        title=_val(row.get("short_description")) or "Network Change",
                        description=_val(row.get("description")),
                        scheduled_start=_parse_snow_datetime(_val(row.get("start_date"))),
                        scheduled_end=_parse_snow_datetime(_val(row.get("end_date")))
                        if _val(row.get("end_date"))
                        else None,
                        engineer_name=engineer_name,
                        engineer_email=engineer_email,
                        state=_map_snow_state(_display(row.get("state"))),
                        ci_hostnames=ci_hostnames,
                    )
                )
            return changes

    async def _fetch_ci_hostnames(
        self,
        client: httpx.AsyncClient,
        change_sys_id: str,
    ) -> list[str]:
        resp = await client.get(
            "/api/now/table/task_ci",
            params={
                "sysparm_query": f"task={change_sys_id}",
                "sysparm_display_value": "true",
                "sysparm_fields": "ci_item",
            },
        )
        resp.raise_for_status()
        hostnames: list[str] = []
        for item in resp.json().get("result", []):
            name = _display(item.get("ci_item"))
            if name:
                hostnames.append(name)
        return hostnames

    async def _fetch_assignee(
        self,
        client: httpx.AsyncClient,
        assigned_to_field: dict | str | None,
    ) -> tuple[str, str]:
        if isinstance(assigned_to_field, dict):
            user_sys_id = assigned_to_field.get("value", "")
            display_name = assigned_to_field.get("display_value", "Network Engineer")
        else:
            user_sys_id = str(assigned_to_field or "")
            display_name = "Network Engineer"

        if not user_sys_id:
            return display_name, "netops-oncall@example.com"

        try:
            resp = await client.get(
                f"/api/now/table/sys_user/{user_sys_id}",
                params={"sysparm_fields": "name,email"},
            )
            resp.raise_for_status()
            user = resp.json().get("result", {})
            return (
                user.get("name") or display_name,
                user.get("email") or "netops-oncall@example.com",
            )
        except Exception as exc:  # pragma: no cover - network defensive fallback
            logger.warning("Failed to resolve ServiceNow assignee %s: %s", user_sys_id, exc)
            return display_name, "netops-oncall@example.com"


def _val(field: dict | str | None) -> str:
    if isinstance(field, dict):
        return str(field.get("value") or "")
    return str(field or "")


def _display(field: dict | str | None) -> str:
    if isinstance(field, dict):
        return str(field.get("display_value") or field.get("value") or "")
    return str(field or "")


def _parse_snow_datetime(raw: str) -> datetime:
    cleaned = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _map_snow_state(state_display: str) -> str:
    lowered = state_display.lower()
    if "cancel" in lowered:
        return "cancelled"
    if "close" in lowered:
        return "closed"
    if "implement" in lowered:
        return "implement"
    return "scheduled"
