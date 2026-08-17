import cards
from web.app import app
from web import poker_web


def make_client(monkeypatch, record=50):
    monkeypatch.setattr("web.app.db.get_global_record", lambda: record)
    monkeypatch.setattr("web.app.db.update_global_record", lambda balance: None)
    app.config["TESTING"] = True
    return app.test_client()


def _fixed_deck(monkeypatch, tail_cards):
    used = set((c.rank, c.suit) for c in tail_cards)
    filler = [cards.Card(r, s) for s in cards.SUITS for r in cards.RANKS if (r, s) not in used]
    full_deck = filler + list(reversed(tail_cards))
    monkeypatch.setattr(poker_web.cards, "new_deck", lambda: full_deck)


TAIL = [cards.Card(r, 'S') for r in ['A', 'K', 'Q', 'J', '10', '9', '8', '7']]


def test_poker_page_shows_buyin_form(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/poker")
    assert resp.status_code == 200
    assert b"Buy In" in resp.data or b"buy" in resp.data.lower()


def test_buyin_with_invalid_amount_shows_error(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    resp = client.post("/poker/buyin", data={"buy_in": "abc"})
    assert resp.status_code == 200
    assert b"Enter a whole number" in resp.data


def test_buyin_deals_first_hand(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("call", 0))
    _fixed_deck(monkeypatch, TAIL)
    resp = client.post("/poker/buyin", data={"buy_in": "50"})
    assert resp.status_code == 200
    assert b"Fold" in resp.data or b"Check" in resp.data or b"Call" in resp.data


def test_buyin_when_bots_act_before_human_shows_log(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("fold", 0))
    _fixed_deck(monkeypatch, TAIL)
    resp = client.post("/poker/buyin", data={"buy_in": "50"})
    assert resp.status_code == 200
    assert b"folds" in resp.data.lower()


def test_buyin_while_table_active_is_a_no_op(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("call", 0))
    _fixed_deck(monkeypatch, TAIL)
    client.post("/poker/buyin", data={"buy_in": "50"})

    with client.session_transaction() as sess:
        assert "poker" in sess
        balance_before = sess["balance"]
        stack_before = sess["poker"]["table"]["players"][0]["stack"]

    # Stale tab / double-click / back-button resubmit: a second buy-in POST
    # while a table is already active must be a complete no-op -- it must
    # not touch the balance or overwrite the existing table/stack.
    resp = client.post("/poker/buyin", data={"buy_in": "50"})
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert sess["balance"] == balance_before
        assert sess["poker"]["table"]["players"][0]["stack"] == stack_before


def test_action_fold(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("fold", 0))
    _fixed_deck(monkeypatch, TAIL)
    client.post("/poker/buyin", data={"buy_in": "50"})
    resp = client.post("/poker/action", data={"action": "fold"})
    assert resp.status_code == 200


def test_action_check_when_to_call_positive_is_rejected(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("call", 0))
    _fixed_deck(monkeypatch, TAIL)
    client.post("/poker/buyin", data={"buy_in": "50"})
    # Preflop, human owes the big blind -- "check" must be rejected, not silently accepted.
    resp = client.post("/poker/action", data={"action": "check"})
    assert resp.status_code == 200
    assert b"call or fold" in resp.data.lower() or b"must call" in resp.data.lower()


def test_action_raise_out_of_bounds_amount_is_rejected(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("call", 0))
    _fixed_deck(monkeypatch, TAIL)
    client.post("/poker/buyin", data={"buy_in": "50"})
    # Preflop, human (seat 0, not SB/BB in hand 1) owes the big blind with a
    # full 50-pt stack and current_bet 0:
    #   min_target = current_bet(0) + to_call(2) + BIG_BLIND(2) = 4
    #   max_target = current_bet(0) + stack(50)                = 50
    # 3 is one below the legal minimum -- the server must reject it, not
    # silently clamp or accept a forged out-of-range raise.
    resp = client.post("/poker/action", data={"action": "raise", "amount": "3"})
    assert resp.status_code == 200
    assert b"Enter a whole number between 4 and 50." in resp.data

    with client.session_transaction() as sess:
        state = sess["poker"]
        assert state["hand"]["phase"] == "player_turn"
        assert state["hand"]["to_act"][0] == 0
        assert state["hand"]["players"][0]["current_bet"] == 0
        assert state["table"]["players"][0]["stack"] == 50


def test_full_hand_to_showdown_via_routes(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    # NOTE: this tail is deliberately NOT the "pocket aces" deck used in
    # test_advance_full_hand_to_showdown_clear_winner (test_poker_web.py) --
    # that deck's original turn/river cards (2S/3S) gave Tex an unnoticed
    # two-pair that beats the human's pair of aces; it was corrected there
    # to 10S/8H (an ace-high straight for the human) after Task 3's
    # implementer caught the bug by hand-tracing evaluate_5's scoring. This
    # test doesn't assert on the winner, so any valid 16-card tail works --
    # reuse the corrected deck here too, for consistency rather than
    # necessity.
    tail = [
        cards.Card('A', 'S'), cards.Card('A', 'H'),
        cards.Card('2', 'D'), cards.Card('3', 'D'),
        cards.Card('4', 'C'), cards.Card('5', 'C'),
        cards.Card('6', 'H'), cards.Card('7', 'H'),
        cards.Card('9', 'S'),
        cards.Card('K', 'D'), cards.Card('Q', 'D'), cards.Card('J', 'C'),
        cards.Card('8', 'S'),
        cards.Card('10', 'S'),
        cards.Card('7', 'S'),
        cards.Card('8', 'H'),
    ]
    _fixed_deck(monkeypatch, tail)

    def bot_policy(p, to_call, board, pot):
        return ("call", 0) if to_call > 0 else ("check", 0)

    monkeypatch.setattr(poker_web, "bot_decide_action", bot_policy)

    resp = client.post("/poker/buyin", data={"buy_in": "50"})
    guard = 0
    while b"Next Hand" not in resp.data and b"Cash Out" not in resp.data:
        guard += 1
        assert guard < 20, "hand never reached resolution via routes"
        if b'name="action" value="check"' in resp.data:
            resp = client.post("/poker/action", data={"action": "check"})
        elif b'name="action" value="call"' in resp.data:
            resp = client.post("/poker/action", data={"action": "call"})
        else:
            break
    assert resp.status_code == 200


def test_next_hand_rebuys_broke_bot(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("fold", 0))
    _fixed_deck(monkeypatch, TAIL)
    client.post("/poker/buyin", data={"buy_in": "50"})
    client.post("/poker/action", data={"action": "fold"})
    with client.session_transaction() as sess:
        state = sess["poker"]
        assert state["hand"]["phase"] == "resolved"
        state["table"]["players"][1]["stack"] = 0  # force Tex broke
        sess["poker"] = state
    _fixed_deck(monkeypatch, TAIL)
    resp = client.post("/poker/next-hand")
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert sess["poker"]["table"]["players"][1]["stack"] > 0
        # Button started at 0 (table.button_idx default from start_table);
        # one call to /poker/next-hand should advance it by exactly one seat.
        assert sess["poker"]["table"]["button_idx"] == 1


def test_cashout_credits_balance(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/poker")
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("fold", 0))
    _fixed_deck(monkeypatch, TAIL)
    client.post("/poker/buyin", data={"buy_in": "50"})
    client.post("/poker/action", data={"action": "fold"})
    resp = client.post("/poker/cashout")
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert "poker" not in sess
        assert sess["balance"] != 0
