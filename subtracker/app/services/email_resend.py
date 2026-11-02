import html
import logging

import httpx

log = logging.getLogger("subtracker.email")


async def send_resend(api_key: str, sender: str, to: str, subject: str, body: str, link: str = "",
                      client: httpx.AsyncClient | None = None) -> None:
    content = f"<p>{html.escape(body)}</p>" + (f'<p><a href="{html.escape(link)}">Open SubTracker</a></p>' if link else "")
    payload = {"from": sender, "to": [to], "subject": subject, "html": content}
    async with client or httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.resend.com/emails", json=payload,
                         headers={"Authorization": f"Bearer {api_key}"})
        r.raise_for_status()
