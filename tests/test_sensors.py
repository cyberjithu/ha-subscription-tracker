from datetime import date

from app.models import Kind, SubStatus, Subscription, UserProfile
from app.services import sensors
from app.services.sensors import push_sensors

TODAY = date(2026, 11, 2)


def states(fake_ha):
    return {c[1]: (c[2], c[3]) for c in fake_ha.of("state")}


async def test_sensor_payloads(session, fake_ha):
    sensors._pushed.clear()
    session.add(UserProfile(id="alice", display_name="Alice"))
    session.add_all([
        Subscription(name="Netflix", category="streaming", price=18, next_renewal=date(2026, 11, 9)),
        Subscription(name="Netflix", category="streaming", price=6, next_renewal=date(2026, 11, 20), owner_user_id="alice"),
        Subscription(name="eir Fibre", category="broadband", kind=Kind.contract, price=60,
                     contract_end=date(2027, 1, 10), notice_days=30),
        Subscription(name="Old", category="streaming", price=99, status=SubStatus.cancelled),
    ])
    session.commit()
    await push_sensors(session, TODAY, ha=fake_ha)
    st = states(fake_ha)
    assert set(st) == {"sensor.subtracker_1", "sensor.subtracker_3",
                       "sensor.subtracker_monthly_total", "sensor.subtracker_next_deadline"}
    assert st["sensor.subtracker_1"][1]["friendly_name"] == "Netflix"
    state, attrs = st["sensor.subtracker_3"]
    assert state == 39 and attrs["next_event"] == "notice_deadline" and attrs["notice_deadline"] == "2026-12-11"
    total, tattrs = st["sensor.subtracker_monthly_total"]
    assert tattrs["panel_url"].startswith("/hassio/ingress/")
    assert total == 84 and tattrs["by_category"] == {"streaming": 24, "broadband": 60} and tattrs["unit_of_measurement"] == "EUR"
    nd, nattrs = st["sensor.subtracker_next_deadline"]
    assert nd == "2026-11-09" and nattrs["subscription"] == "Netflix" and nattrs["days"] == 7
    assert [u["name"] for u in nattrs["upcoming"]] == ["Netflix", "eir Fibre", "eir Fibre"]  # personal one absent


async def test_removed_subscription_state_deleted(session, fake_ha):
    sensors._pushed.clear()
    sub = Subscription(name="Disney", category="streaming", price=10, next_renewal=date(2026, 11, 5))
    session.add(sub)
    session.commit()
    await push_sensors(session, TODAY, ha=fake_ha)
    sub_id = sub.id
    session.delete(sub)
    session.commit()
    await push_sensors(session, TODAY, ha=fake_ha)
    assert fake_ha.of("delete") == [("delete", f"sensor.subtracker_{sub_id}")]
