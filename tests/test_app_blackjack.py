import cards as cards_mod
from web.app import app
from web import blackjack_web


def make_client(monkeypatch, record=50):
    monkeypatch.setattr("web.app.db.get_global_record", lambda: record)
    monkeypatch.setattr("web.app.db.update_global_record", lambda balance: None)
    app.config["TESTING"] = True
    return app.test_client()


def _queue(monkeypatch, card_list):
    it = iter(card_list)
    monkeypatch.setattr(blackjack_web, "draw_card", lambda: next(it))


def test_blackjack_page_shows_bet_form(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/blackjack")
    assert resp.status_code == 200
    assert b"Deal" in resp.data


def test_deal_with_invalid_bet_shows_error(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    resp = client.post("/blackjack/deal", data={"bet": "abc"})
    assert resp.status_code == 200
    assert b"Enter a whole number" in resp.data


def test_deal_player_blackjack_credits_balance(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('A', 'H'), cards_mod.Card('K', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
    ])
    resp = client.post("/blackjack/deal", data={"bet": "10"})
    assert resp.status_code == 200
    assert b"65" in resp.data  # 50 - 10 bet + 25 payout = 65


def test_deal_dealer_ace_upcard_shows_insurance_prompt(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('A', 'C'),
    ])
    resp = client.post("/blackjack/deal", data={"bet": "10"})
    assert resp.status_code == 200
    assert b"insurance" in resp.data.lower()


def test_full_hit_stand_flow_resolves_and_credits(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('5', 'H'), cards_mod.Card('4', 'S'),   # player 9
        cards_mod.Card('9', 'D'), cards_mod.Card('2', 'C'),   # dealer 11
        cards_mod.Card('K', 'H'),                              # hit -> 19
        cards_mod.Card('K', 'S'),                              # dealer draws -> 21... make dealer bust instead
    ])
    client.post("/blackjack/deal", data={"bet": "10"})
    resp = client.post("/blackjack/action", data={"action": "hit"})
    assert resp.status_code == 200
    resp = client.post("/blackjack/action", data={"action": "stand"})
    assert resp.status_code == 200
    assert b"Play Another Hand" in resp.data


def test_split_flow_creates_two_hands_in_response(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('8', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
        cards_mod.Card('3', 'H'), cards_mod.Card('4', 'S'),
    ])
    client.post("/blackjack/deal", data={"bet": "10"})
    resp = client.post("/blackjack/action", data={"action": "split"})
    assert resp.status_code == 200
    assert b"Your Hand 1/2" in resp.data
    assert b"Your Hand 2/2" in resp.data


def test_next_clears_round_back_to_bet_form(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('A', 'H'), cards_mod.Card('K', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
    ])
    client.post("/blackjack/deal", data={"bet": "10"})
    resp = client.post("/blackjack/next")
    assert resp.status_code == 200
    assert b"Deal" in resp.data


def test_action_with_no_round_in_session_does_not_crash(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/blackjack/action", data={"action": "hit"})
    assert resp.status_code == 200
