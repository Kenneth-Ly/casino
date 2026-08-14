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
