def test_health_and_envelope(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["success"] is True

    r = client.get("/api/events/999999")
    assert r.status_code == 404
    assert r.json() == {"success": False, "error": {"code": "EVENT_NOT_FOUND", "message": "Event not found"}}


def test_list_endpoints(client):
    for path in ("/api/events?range=7d", "/api/opportunities", "/api/actions", "/api/dashboard/summary", "/api/dashboard/trends", "/api/dashboard/map",
                 "/api/sources", "/api/venues", "/api/cities", "/api/categories", "/api/changes", "/api/reports/daily", "/api/health/detailed", "/api/settings", "/api/pipeline/runs"):
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.json()
        assert body["success"] is True
    ev = client.get("/api/events?range=30d").json()
    assert "meta" in ev and {"page", "page_size", "total"} <= set(ev["meta"])


def test_action_lifecycle(client):
    acts = client.get("/api/actions?days=30").json()["data"]
    if not acts:
        return
    aid = acts[0]["id"]
    assert client.post(f"/api/actions/{aid}/complete").json()["data"]["status"] == "DONE"
    assert client.post(f"/api/actions/{aid}/dismiss").json()["data"]["status"] == "DISMISSED"


def test_settings_hide_secrets(client):
    body = client.get("/api/settings").json()["data"]
    assert isinstance(body["integrations"]["telegram"], bool)
    assert "token" not in str(body).lower()


def test_telegram_commands(db_session):
    from app.notifications.telegram import handle_command
    assert "UK-ETDI" in handle_command(db_session, "/start")
    assert handle_command(db_session, "/week").startswith("📅")
    assert "run" in handle_command(db_session, "/status").lower()
