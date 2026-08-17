import cards
from web import poker_web


def test_start_table_creates_four_players_with_correct_seats():
    table = poker_web.start_table(50)
    assert table["button_idx"] == 0
    assert table["buy_in"] == 50
    names = [p["name"] for p in table["players"]]
    assert names == ["You", "Tex", "Lucy", "Cal"]
    assert [p["stack"] for p in table["players"]] == [50, 50, 50, 50]
    assert table["players"][0]["is_bot"] is False
    assert table["players"][0]["personality"] is None
    assert table["players"][1]["is_bot"] is True
    assert table["players"][1]["personality"] == "TAG"
    assert table["players"][2]["personality"] == "LAG"
    assert table["players"][3]["personality"] == "Station"


def test_rebuy_broke_bots_only_rebuys_broke_bots():
    table = poker_web.start_table(50)
    table["players"][0]["stack"] = 0    # human, broke -- must NOT be rebought
    table["players"][1]["stack"] = 0    # bot, broke -- must be rebought
    table["players"][2]["stack"] = 30   # bot, not broke -- untouched
    poker_web.rebuy_broke_bots(table)
    assert table["players"][0]["stack"] == 0
    assert table["players"][1]["stack"] == 50
    assert table["players"][2]["stack"] == 30


def test_card_to_json_and_back_round_trips():
    card = cards.Card('K', 'H')
    pair = poker_web.card_to_json(card)
    assert pair == ['K', 'H']
    restored = poker_web.card_from_json(pair)
    assert restored == card


def test_suit_symbol_maps_all_four_suits():
    assert poker_web.suit_symbol('S') == '♠'
    assert poker_web.suit_symbol('H') == '♥'
    assert poker_web.suit_symbol('D') == '♦'
    assert poker_web.suit_symbol('C') == '♣'


def test_is_red_suit():
    assert poker_web.is_red_suit('H') is True
    assert poker_web.is_red_suit('D') is True
    assert poker_web.is_red_suit('S') is False
    assert poker_web.is_red_suit('C') is False


def _fixed_deck(monkeypatch, tail_cards):
    """Monkeypatch cards.new_deck() so deck.pop() yields tail_cards in order
    (tail_cards[0] popped first). The rest of the 52-card deck fills the front,
    all distinct from tail_cards."""
    used = set((c.rank, c.suit) for c in tail_cards)
    filler = [
        cards.Card(r, s)
        for s in cards.SUITS for r in cards.RANKS
        if (r, s) not in used
    ]
    full_deck = filler + list(reversed(tail_cards))
    monkeypatch.setattr(poker_web.cards, "new_deck", lambda: full_deck)


def test_deal_new_hand_deals_two_distinct_hole_cards_per_player(monkeypatch):
    tail = [
        cards.Card('A', 'S'), cards.Card('K', 'S'),
        cards.Card('Q', 'S'), cards.Card('J', 'S'),
        cards.Card('10', 'S'), cards.Card('9', 'S'),
        cards.Card('8', 'S'), cards.Card('7', 'S'),
    ]
    _fixed_deck(monkeypatch, tail)
    table = poker_web.start_table(50)
    hand = poker_web.deal_new_hand(table)
    holes = hand["players"]
    assert holes[0]["hole"] == [['A', 'S'], ['K', 'S']]
    assert holes[1]["hole"] == [['Q', 'S'], ['J', 'S']]
    assert holes[2]["hole"] == [['10', 'S'], ['9', 'S']]
    assert holes[3]["hole"] == [['8', 'S'], ['7', 'S']]
    all_cards = [tuple(c) for h in holes for c in h["hole"]]
    assert len(set(all_cards)) == 8  # all distinct


def test_deal_new_hand_posts_blinds_correctly(monkeypatch):
    tail = [cards.Card(r, 'S') for r in ['A', 'K', 'Q', 'J', '10', '9', '8', '7']]
    _fixed_deck(monkeypatch, tail)
    table = poker_web.start_table(50)  # button_idx 0 -> sb=1 (Tex), bb=2 (Lucy)
    hand = poker_web.deal_new_hand(table)
    assert hand["players"][1]["current_bet"] == 1   # SMALL_BLIND
    assert hand["players"][1]["total_committed"] == 1
    assert hand["players"][2]["current_bet"] == 2   # BIG_BLIND
    assert hand["players"][2]["total_committed"] == 2
    assert table["players"][1]["stack"] == 49
    assert table["players"][2]["stack"] == 48
    assert hand["current_max_bet"] == 2


def test_deal_new_hand_short_stack_blind_goes_all_in(monkeypatch):
    tail = [cards.Card(r, 'S') for r in ['A', 'K', 'Q', 'J', '10', '9', '8', '7']]
    _fixed_deck(monkeypatch, tail)
    table = poker_web.start_table(50)
    table["players"][2]["stack"] = 1  # bb seat can't cover the full BIG_BLIND (2)
    hand = poker_web.deal_new_hand(table)
    assert hand["players"][2]["current_bet"] == 1
    assert hand["players"][2]["all_in"] is True
    assert table["players"][2]["stack"] == 0
    assert 2 not in hand["to_act"]  # all-in player never gets a betting turn


def test_deal_new_hand_builds_correct_preflop_order_and_to_act(monkeypatch):
    tail = [cards.Card(r, 'S') for r in ['A', 'K', 'Q', 'J', '10', '9', '8', '7']]
    _fixed_deck(monkeypatch, tail)
    table = poker_web.start_table(50)  # button 0, sb 1, bb 2 -> first to act is 3
    hand = poker_web.deal_new_hand(table)
    assert hand["order"] == [3, 0, 1, 2]
    assert hand["to_act"] == [3, 0, 1, 2]
    assert hand["street"] == "preflop"
    assert hand["phase"] == "player_turn"
    assert hand["board"] == []
    assert hand["log"] == []


def test_deal_new_hand_writes_back_stacks_to_table(monkeypatch):
    tail = [cards.Card(r, 'S') for r in ['A', 'K', 'Q', 'J', '10', '9', '8', '7']]
    _fixed_deck(monkeypatch, tail)
    table = poker_web.start_table(50)
    poker_web.deal_new_hand(table)
    assert table["players"][0]["stack"] == 50  # untouched -- not a blind seat
    assert table["players"][1]["stack"] == 49
    assert table["players"][2]["stack"] == 48
    assert table["players"][3]["stack"] == 50
