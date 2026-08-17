from web.app import app
from web import roulette_web


def make_client(monkeypatch, record=50):
    monkeypatch.setattr("web.app.db.get_global_record", lambda: record)
    monkeypatch.setattr("web.app.db.update_global_record", lambda balance: None)
    app.config["TESTING"] = True
    return app.test_client()


def test_roulette_page_shows_bet_form(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/roulette")
    assert resp.status_code == 200
    assert b"Add Bet" in resp.data


def test_add_bet_with_invalid_amount_shows_error(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    resp = client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "abc"})
    assert resp.status_code == 200
    assert b"Enter a whole number" in resp.data


def test_add_bet_appends_to_slip(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    resp = client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    assert resp.status_code == 200
    assert b"Bet Slip" in resp.data
    assert b"Spin" in resp.data


def test_remove_bet_removes_line(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    resp = client.post("/roulette/remove", data={"index": "0"})
    assert resp.status_code == 200
    assert b"Bet Slip" not in resp.data


def test_spin_with_empty_slip_is_noop(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    resp = client.post("/roulette/spin")
    assert resp.status_code == 200
    assert b"Add Bet" in resp.data


def test_spin_resolves_and_credits_balance(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    resp = client.post("/roulette/spin")
    assert resp.status_code == 200
    assert b"55" in resp.data  # 50 - 5 wager + 10 win = 55
    assert b"New Round" in resp.data


def test_next_clears_back_to_fresh_slip(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    client.post("/roulette/spin")
    resp = client.post("/roulette/next")
    assert resp.status_code == 200
    assert b"Add Bet" in resp.data
    assert b"Bet Slip" not in resp.data


def test_remove_route_with_no_session_state_does_not_crash(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/roulette/remove", data={"index": "0"})
    assert resp.status_code == 200
