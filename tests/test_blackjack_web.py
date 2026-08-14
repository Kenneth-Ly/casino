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
