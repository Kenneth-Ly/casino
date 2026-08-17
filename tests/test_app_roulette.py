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


def test_bet_after_resolved_round_does_not_crash(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    client.post("/roulette/spin")
    resp = client.post("/roulette/bet", data={"bet_type": "black", "number": "", "amount": "3"})
    assert resp.status_code == 200


def test_bet_after_resolved_round_shows_resolved_view_not_error(monkeypatch):
    # Regression for finding #2: a stale POST to /roulette/bet after the round
    # resolved must not run remaining_balance/validate_bet against settled bets
    # and produce a nonsense negative-range error over the resolved view.
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    client.post("/roulette/spin")
    resp = client.post("/roulette/bet", data={"bet_type": "black", "number": "", "amount": "3"})
    assert resp.status_code == 200
    assert b"New Round" in resp.data
    assert b"and -" not in resp.data


def test_remove_after_resolved_round_is_noop(monkeypatch):
    # Regression for finding #3: a stale POST to /roulette/remove after the
    # round resolved must not pop a line out of the resolved results readout.
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    client.post("/roulette/bet", data={"bet_type": "black", "number": "", "amount": "3"})
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    resolved_resp = client.post("/roulette/spin")
    before_count = resolved_resp.data.count(b"bet-line")
    assert before_count == 2

    resp = client.post("/roulette/remove", data={"index": "0"})
    assert resp.status_code == 200
    assert resp.data.count(b"bet-line") == before_count


def test_multi_bet_slip_built_across_several_posts(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    client.post("/roulette/bet", data={"bet_type": "black", "number": "", "amount": "5"})
    resp = client.post("/roulette/bet", data={"bet_type": "even", "number": "", "amount": "5"})
    assert resp.status_code == 200
    assert b"Red (1:1)" in resp.data
    assert b"Black (1:1)" in resp.data
    assert b"Even (1:1)" in resp.data


def test_spin_resolves_and_debits_balance_on_loss(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    # "2" is black, so a "red" bet loses outright.
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "2")
    resp = client.post("/roulette/spin")
    assert resp.status_code == 200
    assert b"45" in resp.data  # 50 - 5 wager + 0 win = 45
    assert b"New Round" in resp.data


def test_second_bet_exceeding_remaining_balance_is_rejected(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    first = client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "45"})
    assert first.status_code == 200
    assert b"Enter a whole number" not in first.data

    resp = client.post("/roulette/bet", data={"bet_type": "black", "number": "", "amount": "6"})
    assert resp.status_code == 200
    assert b"Enter a whole number between 1 and 5." in resp.data
    assert resp.data.count(b"bet-line") == 1


def test_spin_with_balance_drift_does_not_go_negative(monkeypatch):
    # Regression for finding #1: if the shared session balance shrinks below
    # the slip's total wager between adding bets and spinning (e.g. another
    # tab/game spent it), the spin route must refuse to spin rather than
    # driving balance negative.
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "10"})

    with client.session_transaction() as sess:
        sess["balance"] = 5

    resp = client.post("/roulette/spin")
    assert resp.status_code == 200
    assert b"Your balance changed" in resp.data
    assert b"New Round" not in resp.data

    with client.session_transaction() as sess:
        assert sess["balance"] == 5
        assert sess["roulette"]["phase"] == "betting"
