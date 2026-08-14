from web.app import app


def make_client(monkeypatch, record=50):
    monkeypatch.setattr("web.app.db.get_global_record", lambda: record)
    monkeypatch.setattr("web.app.db.update_global_record", lambda balance: None)
    app.config["TESTING"] = True
    return app.test_client()


def test_lobby_shows_global_record(monkeypatch):
    client = make_client(monkeypatch, record=120)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"120" in resp.data


def test_lobby_handles_db_error(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("web.app.db.get_global_record", boom)
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"unavailable" in resp.data


def test_slots_page_starts_with_default_balance(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/slots")
    assert resp.status_code == 200
    assert b"50" in resp.data


def test_spin_with_invalid_bet_shows_error(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/slots")
    resp = client.post("/slots/spin", data={"bet": "abc"})
    assert resp.status_code == 200
    assert b"Enter a whole number" in resp.data


def test_spin_with_valid_bet_deducts_and_shows_reels(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/slots")
    resp = client.post("/slots/spin", data={"bet": "5"})
    assert resp.status_code == 200


def test_reset_restores_default_balance(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/slots")
    client.post("/slots/spin", data={"bet": "50"})
    resp = client.post("/slots/reset")
    assert resp.status_code == 200
    assert b"50" in resp.data
