from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlmodel import select

from app.config import Options
from app.models import InboxItem, Kind, PendingDelivery, Subscription, UserProfile
from app.services import notify as notify_mod
from app.services.email_resend import send_resend
from app.services.notify import flush_pending, notify, quiet_until
from app.services.reminders import run_reminders

NOON = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def users(session):
    session.add_all([
        UserProfile(id="alice", push_service="notify.mobile_app_alice"),
        UserProfile(id="bob", push_service="notify.mobile_app_bob", muted_categories=["streaming"]),
    ])
    session.commit()


async def test_shared_goes_to_all_unmuted(session, users, fake_ha):
    await notify(session, key="k1", title="T", body="B", category="broadband", now=NOON, ha=fake_ha)
    assert {c[1] for c in fake_ha.of("notify")} == {"notify.mobile_app_alice", "notify.mobile_app_bob"}
    assert len(fake_ha.of("persistent")) == 1
    await notify(session, key="k2", title="T", body="B", category="streaming", now=NOON, ha=fake_ha)
    assert [c[1] for c in fake_ha.of("notify")[2:]] == ["notify.mobile_app_alice"]


async def test_personal_goes_to_owner_only(session, users, fake_ha):
    await notify(session, key="k", title="T", body="B", owner_user_id="bob", category="x", now=NOON, ha=fake_ha)
    assert [c[1] for c in fake_ha.of("notify")] == ["notify.mobile_app_bob"]
    assert session.exec(select(InboxItem.user_id)).all() == ["bob"]


async def test_dedupe(session, users, fake_ha):
    assert await notify(session, key="same", title="T", body="B", now=NOON, ha=fake_ha)
    assert not await notify(session, key="same", title="T", body="B", now=NOON, ha=fake_ha)
    assert len(fake_ha.of("notify")) == 2


def test_quiet_until_crosses_midnight():
    u = UserProfile(id="u", quiet_start="22:00", quiet_end="07:30")
    late = datetime(2026, 11, 2, 23, 0, tzinfo=UTC)
    assert quiet_until(u, late) == datetime(2026, 11, 3, 7, 30, tzinfo=UTC)
    assert quiet_until(u, datetime(2026, 11, 2, 6, 0, tzinfo=UTC)) == datetime(2026, 11, 2, 7, 30, tzinfo=UTC)
    assert quiet_until(u, NOON) is None


async def test_quiet_hours_delay_then_flush(session, fake_ha):
    session.add(UserProfile(id="q", push_service="notify.mobile_app_q", quiet_start="22:00", quiet_end="07:00"))
    session.commit()
    night = datetime(2026, 11, 2, 23, 0, tzinfo=UTC)
    await notify(session, key="n", title="T", body="B", now=night, ha=fake_ha)
    assert fake_ha.of("notify") == [] and len(session.exec(select(PendingDelivery)).all()) == 1
    assert await flush_pending(session, now=night + timedelta(hours=1), ha=fake_ha) == 0
    assert await flush_pending(session, now=night + timedelta(hours=9), ha=fake_ha) == 1
    assert [c[1] for c in fake_ha.of("notify")] == ["notify.mobile_app_q"]


async def test_email_channel_uses_resend(session, fake_ha, monkeypatch):
    sent = []

    async def fake_send(key, sender, to, subject, body, link=""):
        sent.append((key, sender, to, subject))
    monkeypatch.setattr(notify_mod, "send_resend", fake_send)
    monkeypatch.setattr(notify_mod, "get_options", lambda: Options(resend_api_key="rk", resend_from="st@x.ie"))
    session.add(UserProfile(id="e", email="me@x.ie", channels={"email": True}))
    session.commit()
    await notify(session, key="e", title="Renewal", body="B", now=NOON, ha=fake_ha)
    assert sent == [("rk", "st@x.ie", "me@x.ie", "Renewal")]


async def test_send_resend_http_shape():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"], seen["url"], seen["body"] = req.headers["authorization"], str(req.url), req.content
        return httpx.Response(200, json={"id": "1"})
    await send_resend("rk", "a@x.ie", "b@x.ie", "Hi", "<b>", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert seen["auth"] == "Bearer rk" and seen["url"] == "https://api.resend.com/emails"
    assert b"&lt;b&gt;" in seen["body"]  # body is escaped


async def test_failing_channel_does_not_block_others(session, fake_ha):
    async def boom(*a, **k):
        raise RuntimeError("down")
    fake_ha.notify = boom
    session.add(UserProfile(id="a", push_service="notify.mobile_app_a"))
    session.commit()
    assert await notify(session, key="x", title="T", body="B", now=NOON, ha=fake_ha)
    assert len(fake_ha.of("persistent")) == 1


async def test_reminders_fire_on_reminder_days_once(session, users, fake_ha):
    session.add(Subscription(name="eir", category="broadband", kind=Kind.contract,
                             contract_end=date(2026, 12, 9), notice_days=30))  # notice deadline 2026-11-09
    session.commit()
    assert await run_reminders(session, today=date(2026, 11, 1), ha=fake_ha) == 0  # 8 days: not a reminder day
    assert await run_reminders(session, today=date(2026, 11, 2), ha=fake_ha) == 2  # 7 days, alice + bob
    assert await run_reminders(session, today=date(2026, 11, 2), ha=fake_ha) == 0  # dedupe
    assert {c[1] for c in fake_ha.of("persistent")} == {"subtracker_notice_deadline:1:2026-11-09:7"}


async def test_user_reminder_override_and_personal(session, fake_ha):
    session.add_all([UserProfile(id="o", reminder_days=[8]), UserProfile(id="other")])
    session.add(Subscription(name="Claude", category="software", owner_user_id="o", next_renewal=date(2026, 11, 10)))
    session.commit()
    assert await run_reminders(session, today=date(2026, 11, 2), ha=fake_ha) == 1
    assert session.exec(select(InboxItem.user_id)).all() == ["o"]


async def test_personal_with_missing_owner_never_reaches_others(session, fake_ha):
    session.add(UserProfile(id="bob", push_service="notify.mobile_app_bob"))
    session.add(Subscription(name="Antidepressant", category="medicine", owner_user_id="alice",
                             next_renewal=date(2026, 11, 9)))
    session.commit()
    await run_reminders(session, today=date(2026, 11, 2), ha=fake_ha)
    assert fake_ha.of("notify") == []
    assert session.exec(select(InboxItem.user_id)).all() == ["alice"]


async def test_personal_never_sent_to_persistent(session, fake_ha):
    session.add(UserProfile(id="alice", push_service="notify.mobile_app_alice"))
    session.add(Subscription(name="Therapy", category="health", owner_user_id="alice", next_renewal=date(2026, 11, 9)))
    session.add(Subscription(name="Bins", category="bins", next_renewal=date(2026, 11, 9)))
    session.commit()
    await run_reminders(session, today=date(2026, 11, 2), ha=fake_ha)
    assert [c[2] for c in fake_ha.of("persistent")] == ["Bins renews"]
    assert sorted(c[2] for c in fake_ha.of("notify")) == ["Bins renews", "Therapy renews"]


async def test_expired_contract_reminds_on_nag_day(session, fake_ha):
    session.add(UserProfile(id="a", push_service="notify.mobile_app_a"))
    session.add(Subscription(name="Energia", category="electricity", kind=Kind.contract, contract_end=date(2026, 10, 26)))
    session.commit()
    assert await run_reminders(session, today=date(2026, 11, 1), ha=fake_ha) == 0
    assert await run_reminders(session, today=date(2026, 11, 2), ha=fake_ha) == 1
    assert "contract ended" in fake_ha.of("notify")[0][2]
