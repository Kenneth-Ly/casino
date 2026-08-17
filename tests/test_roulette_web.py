from web import roulette_web


def test_fresh_state_shape():
    state = roulette_web.fresh_state()
    assert state == {"phase": "betting", "bets": [], "pocket": None, "color": None}


def test_remaining_balance_subtracts_committed_bets():
    state = roulette_web.fresh_state()
    state["bets"] = [{"amount": 5}, {"amount": 3}]
    assert roulette_web.remaining_balance(state, 50) == 42


def test_add_bet_valid_outside_bet():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "red", "", 5)
    assert error is None
    assert state["bets"] == [{"type": "red", "value": None, "amount": 5, "label": "Red (1:1)"}]


def test_add_bet_valid_straight_bet():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "17", 2)
    assert error is None
    assert state["bets"][0]["value"] == "17"
    assert state["bets"][0]["label"] == "Straight-up number (35:1)"


def test_add_bet_straight_00():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "00", 2)
    assert error is None
    assert state["bets"][0]["value"] == "00"


def test_add_bet_invalid_bet_type():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "bogus", "", 5)
    assert error == "Choose a valid bet type."
    assert state["bets"] == []


def test_add_bet_straight_missing_number():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "", 5)
    assert error == "Enter a number 0-36 or 00 for a straight-up bet."
    assert state["bets"] == []


def test_add_bet_straight_invalid_number():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "37", 5)
    assert error == "Enter a number 0-36 or 00 for a straight-up bet."
    assert state["bets"] == []


def test_remove_bet_valid_index():
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    roulette_web.add_bet(state, "black", "", 3)
    state = roulette_web.remove_bet(state, 0)
    assert len(state["bets"]) == 1
    assert state["bets"][0]["type"] == "black"


def test_remove_bet_out_of_range_index_no_op():
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    state = roulette_web.remove_bet(state, 9)
    assert len(state["bets"]) == 1


def test_spin_empty_slip_is_no_op():
    state = roulette_web.fresh_state()
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 0
    assert total_return == 0
    assert state["phase"] == "betting"


def test_spin_wrong_phase_is_no_op(monkeypatch):
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    state, _, _ = roulette_web.spin(state)
    assert state["phase"] == "resolved"
    state2, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 0
    assert total_return == 0
    assert state2 == state


def test_spin_red_bet_wins(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 5
    assert total_return == 10
    assert state["pocket"] == "18"
    assert state["color"] == "red"
    assert state["bets"][0]["win"] == 10
    assert state["phase"] == "resolved"


def test_spin_red_bet_loses(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "17")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 5
    assert total_return == 0
    assert state["color"] == "black"
    assert state["bets"][0]["win"] == 0


def test_spin_straight_bet_wins(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "17")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "straight", "17", 2)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 2
    assert total_return == 72  # 2 * 36
    assert state["bets"][0]["win"] == 72


def test_spin_multiple_bets_mixed_outcome(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")  # red
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)         # wins: 10
    roulette_web.add_bet(state, "straight", "17", 2)  # loses: 0
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 7
    assert total_return == 10
    assert state["bets"][0]["win"] == 10
    assert state["bets"][1]["win"] == 0


def test_spin_zero_pocket_outside_bets_lose(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "0")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    roulette_web.add_bet(state, "straight", "0", 2)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 7
    assert total_return == 72  # only the straight-up 0 bet wins
    assert state["color"] == "green"
    assert state["bets"][0]["win"] == 0
    assert state["bets"][1]["win"] == 72


def test_next_round_returns_fresh_state():
    assert roulette_web.next_round() == roulette_web.fresh_state()
