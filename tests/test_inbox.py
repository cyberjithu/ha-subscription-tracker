from sqlmodel import select

from app.models import InboxItem

from .conftest import as_user


def test_inbox_scoped_and_mark_read(client, session):
    session.add_all([InboxItem(user_id="a", key="1", title="mine"), InboxItem(user_id=None, key="2", title="all"),
                     InboxItem(user_id="b", key="3", title="theirs")])
    session.commit()
    r = client.get("/api/inbox", headers=as_user("a")).json()
    assert r["unread"] == 2 and {i["title"] for i in r["items"]} == {"mine", "all"}
    theirs = session.exec(select(InboxItem).where(InboxItem.title == "theirs")).one().id
    assert client.post(f"/api/inbox/{theirs}/read", headers=as_user("a")).status_code == 404
    mine = next(i["id"] for i in r["items"] if i["title"] == "mine")
    assert client.post(f"/api/inbox/{mine}/read", headers=as_user("a")).status_code == 204
    assert client.get("/api/inbox", headers=as_user("a")).json()["unread"] == 1
    client.post("/api/inbox/read-all", headers=as_user("a"))
    assert client.get("/api/inbox", headers=as_user("a")).json()["unread"] == 0
    assert client.get("/api/inbox", headers=as_user("b")).json()["unread"] == 1
