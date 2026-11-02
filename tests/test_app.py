from app import main
from app.services import jobs


def test_spa_serves_files_and_falls_back(client, tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/some/client/route").text == "<html>app</html>"  # SPA fallback
    assert client.get("/..%2Fsecret.txt").text == "<html>app</html>"  # no escape from the static dir
    assert client.get("/api/missing").status_code == 404  # API typos are not masked by the SPA


def test_frontend_missing_is_503(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)
    assert client.get("/").status_code == 503


async def test_scheduler_registers_jobs():
    jobs.start()
    try:
        assert {j.id for j in jobs.scheduler.get_jobs()} == {"reminders", "sensors", "flush"}
    finally:
        jobs.scheduler.remove_all_jobs()  # don't let the immediate runs hit the test data dir
        jobs.stop()


def test_addon_options_match_app_options():
    import yaml

    from app.config import APP_DIR, Options
    cfg = yaml.safe_load((APP_DIR.parent / "config.yaml").read_text())
    assert set(cfg["options"]) == set(cfg["schema"]) == set(Options.model_fields)
    assert Options(**cfg["options"]) == Options()  # add-on defaults equal app defaults


def test_frontend_api_types_cover_every_endpoint():
    """Fails when the API changes without `npm run gen:api` in subtracker/frontend."""
    from app.config import APP_DIR
    from app.main import app
    types = (APP_DIR.parent / "frontend" / "src" / "lib" / "api-types.ts").read_text()
    for path, methods in app.openapi()["paths"].items():
        start = types.index(f'"{path}": {{')  # ValueError = path missing from generated types
        block = types[start:types.index("\n    };", start)]
        for method in methods:
            assert f"{method}: operations[" in block, (path, method)
