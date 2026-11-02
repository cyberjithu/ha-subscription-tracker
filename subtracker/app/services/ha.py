"""Home Assistant Core API via the Supervisor proxy. Without SUPERVISOR_TOKEN (local dev) calls are logged only."""
import logging
import os
from typing import Any

import httpx

log = logging.getLogger("subtracker.ha")


class HAClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
        self.base_url = base_url or os.environ.get("SUBTRACKER_HA_URL", "http://supervisor/core/api")

    @property
    def live(self) -> bool:
        return bool(self.token)

    async def _post(self, path: str, json: dict, params: dict | None = None) -> Any:
        if not self.live:
            log.info("HA (dry run) POST %s %s", path, json)
            return None
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{self.base_url}{path}", json=json, params=params,
                headers={"Authorization": f"Bearer {self.token}"},
            )
            r.raise_for_status()
            return r.json() if r.content else None

    async def set_state(self, entity_id: str, state: Any, attributes: dict) -> None:
        await self._post(f"/states/{entity_id}", {"state": state, "attributes": attributes})

    async def delete_state(self, entity_id: str) -> None:
        if not self.live:
            log.info("HA (dry run) DELETE /states/%s", entity_id)
            return
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(f"{self.base_url}/states/{entity_id}",
                                    headers={"Authorization": f"Bearer {self.token}"})
            if r.status_code != 404:
                r.raise_for_status()

    async def call_service(self, service: str, data: dict, return_response: bool = False) -> Any:
        domain, name = service.split(".", 1)
        params = {"return_response": "true"} if return_response else None
        return await self._post(f"/services/{domain}/{name}", data, params)

    async def notify(self, service: str, title: str, message: str, url: str = "") -> None:
        data: dict = {"title": title, "message": message}
        if url and service.startswith("notify.mobile_app_"):
            data["data"] = {"url": url, "clickAction": url, "actions": [{"action": "URI", "title": "Open", "uri": url}]}
        await self.call_service(service, data)

    async def persistent(self, title: str, message: str, notification_id: str) -> None:
        await self.call_service("persistent_notification.create",
                                {"title": title, "message": message, "notification_id": notification_id})


ha = HAClient()
