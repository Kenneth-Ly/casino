import cards
from games.blackjack import Hand
from web import blackjack_web


def test_draw_card_returns_valid_card():
    card = blackjack_web.draw_card()
    assert card.rank in cards.RANKS
    assert card.suit in cards.SUITS


def test_card_to_json_and_back_round_trips():
    card = cards.Card('K', 'H')
    pair = blackjack_web.card_to_json(card)
    assert pair == ['K', 'H']
    restored = blackjack_web.card_from_json(pair)
    assert restored == card


def test_suit_symbol_maps_all_four_suits():
    assert blackjack_web.suit_symbol('S') == '♠'
    assert blackjack_web.suit_symbol('H') == '♥'
    assert blackjack_web.suit_symbol('D') == '♦'
    assert blackjack_web.suit_symbol('C') == '♣'


def test_is_red_suit():
    assert blackjack_web.is_red_suit('H') is True
    assert blackjack_web.is_red_suit('D') is True
    assert blackjack_web.is_red_suit('S') is False
    assert blackjack_web.is_red_suit('C') is False


def test_hand_to_json_and_back_round_trips():
    hand = Hand([cards.Card('A', 'S'), cards.Card('K', 'D')], bet=20)
    hand.doubled = True
    hand.stood = True
    d = blackjack_web.hand_to_json(hand)
    assert d == {
        "cards": [["A", "S"], ["K", "D"]],
        "bet": 20,
        "doubled": True,
        "from_split_aces": False,
        "stood": True,
        "busted": False,
        "result": None,
    }
    restored = blackjack_web.hand_from_json(d)
    assert restored.bet == 20
    assert restored.doubled is True
    assert restored.stood is True
    assert [c.rank for c in restored.cards] == ['A', 'K']


from unittest.mock import patch

import cards as cards_mod
from web import blackjack_web


def _queue(monkeypatch, card_list):
    """Monkeypatch draw_card to return cards from card_list in order."""
    it = iter(card_list)
    monkeypatch.setattr(blackjack_web, "draw_card", lambda: next(it))


def test_start_round_normal_deal_enters_player_turn(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),   # player
        cards_mod.Card('K', 'D'), cards_mod.Card('7', 'C'),   # dealer (upcard 7, not ace/10)
    ])
    state, winnings = blackjack_web.start_round(10)
    assert state["phase"] == "player_turn"
    assert winnings == 0
    assert len(state["hands"]) == 1
    assert state["hands"][0]["bet"] == 10
    assert state["active_index"] == 0


def test_start_round_player_natural_blackjack_resolves_immediately(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('A', 'H'), cards_mod.Card('K', 'S'),   # player blackjack
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),   # dealer 16, no blackjack
    ])
    state, winnings = blackjack_web.start_round(10)
    assert state["phase"] == "resolved"
    assert winnings == 25  # bet back (10) + 3:2 payout (15)
    assert state["hands"][0]["outcome"] == "blackjack"


def test_start_round_dealer_blackjack_beats_no_player_blackjack(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('9', 'H'), cards_mod.Card('7', 'S'),   # player 16
        cards_mod.Card('A', 'D'), cards_mod.Card('K', 'C'),   # dealer blackjack
    ])
    state, winnings = blackjack_web.start_round(10)
    assert state["phase"] == "resolved"
    assert winnings == 0
    assert state["hands"][0]["outcome"] == "lose"


def test_start_round_dealer_upcard_ace_offers_insurance(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),   # player 17
        cards_mod.Card('9', 'D'), cards_mod.Card('A', 'C'),   # dealer shows Ace, no blackjack (hole 9)
    ])
    state, winnings = blackjack_web.start_round(10)
    assert state["phase"] == "insurance_offer"
    assert winnings == 0


def test_apply_insurance_accept_dealer_has_blackjack_pays_out(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),   # player 17
        cards_mod.Card('K', 'D'), cards_mod.Card('A', 'C'),   # dealer blackjack, shows Ace
    ])
    state, _ = blackjack_web.start_round(10)
    assert state["phase"] == "insurance_offer"

    state, cost, winnings = blackjack_web.apply_insurance(state, "accept", balance=100)
    assert cost == 5  # bet // 2
    assert winnings == 15  # insurance 5 * 3 (stake back + 2:1), main hand loses
    assert state["phase"] == "resolved"


def test_apply_insurance_decline_dealer_has_blackjack_no_payout(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),
        cards_mod.Card('K', 'D'), cards_mod.Card('A', 'C'),
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_insurance(state, "decline", balance=100)
    assert cost == 0
    assert winnings == 0
    assert state["phase"] == "resolved"
    assert state["hands"][0]["outcome"] == "lose"


def test_apply_insurance_accept_no_dealer_blackjack_continues_to_player_turn(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('A', 'C'),   # dealer 20, no blackjack
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_insurance(state, "accept", balance=100)
    assert cost == 5
    assert winnings == 0
    assert state["phase"] == "player_turn"
    assert state["insurance_bet"] == 5


def test_apply_insurance_unaffordable_costs_nothing(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('A', 'C'),
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_insurance(state, "accept", balance=0)
    assert cost == 0
    assert state["insurance_bet"] == 0
    assert state["phase"] == "player_turn"


def test_apply_action_hit_no_bust_stays_in_player_turn(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('5', 'H'), cards_mod.Card('4', 'S'),   # player 9
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),   # dealer 16
        cards_mod.Card('2', 'H'),                              # hit card -> 11
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_action(state, "hit", balance=100)
    assert cost == 0
    assert winnings == 0
    assert state["phase"] == "player_turn"
    assert len(state["hands"][0]["cards"]) == 3


def test_apply_action_hit_bust_resolves_round(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('K', 'H'), cards_mod.Card('9', 'S'),   # player 19
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),   # dealer 16
        cards_mod.Card('K', 'D'),                              # hit -> bust (29)
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_action(state, "hit", balance=100)
    assert cost == 0
    assert winnings == 0
    assert state["phase"] == "resolved"
    assert state["hands"][0]["outcome"] == "bust"


def test_apply_action_stand_dealer_plays_and_player_wins(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('K', 'H'), cards_mod.Card('9', 'S'),   # player 19
        cards_mod.Card('9', 'D'), cards_mod.Card('2', 'C'),   # dealer 11, must hit
        cards_mod.Card('6', 'H'),                              # dealer draws -> 17, stands (17 not < 17)
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_action(state, "stand", balance=100)
    assert cost == 0
    assert state["phase"] == "resolved"
    # dealer stood at 17, player's 19 wins
    assert state["hands"][0]["outcome"] == "win"
    assert winnings == 20  # bet back (10) + even-money win (10)


def test_apply_action_double_costs_bet_and_deals_one_card(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('6', 'H'), cards_mod.Card('5', 'S'),   # player 11
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),   # dealer 16, must hit
        cards_mod.Card('K', 'H'),                              # double card -> 21
        cards_mod.Card('2', 'H'),                              # dealer's forced hit -> 18, stands
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_action(state, "double", balance=100)
    assert cost == 10  # matches original bet
    assert state["hands"][0]["bet"] == 20
    assert state["hands"][0]["doubled"] is True
    assert len(state["hands"][0]["cards"]) == 3
    assert state["phase"] == "resolved"  # doubling forces stand, dealer plays out


def test_apply_action_double_unaffordable_does_nothing(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('6', 'H'), cards_mod.Card('5', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_action(state, "double", balance=5)
    assert cost == 0
    assert state["hands"][0]["bet"] == 10
    assert state["phase"] == "player_turn"


def test_apply_action_split_creates_second_hand(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('8', 'S'),   # player pair of 8s
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),   # dealer 16
        cards_mod.Card('3', 'H'), cards_mod.Card('4', 'S'),   # split draw cards
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_action(state, "split", balance=100)
    assert cost == 10
    assert len(state["hands"]) == 2
    assert state["split_count"] == 1
    assert state["active_index"] == 0  # still playing the first (now 2-card) hand
    assert state["phase"] == "player_turn"


def test_apply_action_split_aces_auto_advances_past_both_hands(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('A', 'H'), cards_mod.Card('A', 'S'),   # player pair of aces
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),   # dealer 16, must hit
        cards_mod.Card('K', 'H'), cards_mod.Card('K', 'S'),   # one card each split-ace hand
        cards_mod.Card('K', 'D'),                              # dealer's forced hit -> 26, busts
    ])
    state, _ = blackjack_web.start_round(10)
    state, cost, winnings = blackjack_web.apply_action(state, "split", balance=100)
    assert cost == 10
    # both split-ace hands get exactly one card and are immediately done -> round resolves
    assert state["phase"] == "resolved"
    assert len(state["hands"][0]["cards"]) == 2
    assert len(state["hands"][1]["cards"]) == 2


def test_apply_action_5_card_charlie_auto_wins(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('2', 'H'), cards_mod.Card('2', 'S'),   # player 4
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),   # dealer 16
        cards_mod.Card('2', 'D'),                              # hit -> 6
        cards_mod.Card('2', 'C'),                              # hit -> 8
        cards_mod.Card('2', 'H'),                              # hit -> 10, 5 cards, Charlie
    ])
    state, _ = blackjack_web.start_round(10)
    state, _, _ = blackjack_web.apply_action(state, "hit", balance=100)
    state, _, _ = blackjack_web.apply_action(state, "hit", balance=100)
    state, cost, winnings = blackjack_web.apply_action(state, "hit", balance=100)
    assert state["phase"] == "resolved"
    assert winnings == 20  # 5-card Charlie pays the bet (bet * 2 returned)
    assert state["hands"][0]["outcome"] == "charlie"


def test_apply_action_wrong_phase_is_a_no_op(monkeypatch):
    _queue(monkeypatch, [
        cards_mod.Card('A', 'H'), cards_mod.Card('K', 'S'),   # player blackjack -> resolved immediately
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
    ])
    state, _ = blackjack_web.start_round(10)
    assert state["phase"] == "resolved"
    state2, cost, winnings = blackjack_web.apply_action(state, "hit", balance=100)
    assert cost == 0
    assert winnings == 0
    assert state2 == state
