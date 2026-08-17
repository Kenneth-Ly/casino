import cards
from web import poker_web
from games.poker import Player


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


def _make_players(n=4):
    return [Player(name, 50, is_bot=(i != 0), personality=(["TAG", "LAG", "Station"][i - 1] if i != 0 else None))
            for i, name in enumerate(["You", "Tex", "Lucy", "Cal"][:n])]


def _make_hand(order, current_max_bet=0):
    players = _make_players()
    return players, {
        "current_max_bet": current_max_bet,
        "order": order,
        "to_act": list(order),
        "log": [],
    }


def test_run_betting_round_bots_check_around_empties_to_act(monkeypatch):
    players, hand = _make_hand([1, 2, 3])
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("check", 0))
    poker_web._run_betting_round(players, hand, board=[])
    assert hand["to_act"] == []
    assert hand["log"] == ["Tex checks.", "Lucy checks.", "Cal checks."]
    assert hand["current_max_bet"] == 0


def test_run_betting_round_pauses_at_human_turn(monkeypatch):
    players, hand = _make_hand([1, 0, 2])
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("check", 0))
    poker_web._run_betting_round(players, hand, board=[])
    assert hand["to_act"] == [0, 2]  # Tex acted and was popped; stopped before touching the human
    assert hand["log"] == ["Tex checks."]


def test_run_betting_round_bot_raise_reopens_action(monkeypatch):
    players, hand = _make_hand([1, 2, 3])

    def decide(p, to_call, board, pot):
        if p.name == "Tex":
            return ("raise", p.current_bet + 10)
        return ("check", 0)

    monkeypatch.setattr(poker_web, "bot_decide_action", decide)
    poker_web._run_betting_round(players, hand, board=[])
    # Tex's raise must force Lucy and Cal (already "acted" this pass, but now
    # facing a new bet) back onto the queue -- and the loop keeps draining
    # until nobody owes a further decision.
    assert hand["to_act"] == []
    assert hand["current_max_bet"] == 10
    assert hand["log"] == ["Tex raises to 10.", "Lucy checks.", "Cal checks."]


def test_run_betting_round_stale_folded_entry_is_skipped(monkeypatch):
    players, hand = _make_hand([1, 2, 3])
    players[1].folded = True  # Tex already folded (e.g. from an earlier partial drain)
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("check", 0))
    poker_web._run_betting_round(players, hand, board=[])
    assert hand["to_act"] == []
    assert hand["log"] == ["Lucy checks.", "Cal checks."]


def test_run_betting_round_stops_immediately_when_only_one_player_remains(monkeypatch):
    players, hand = _make_hand([1, 2, 3])
    calls = []

    def decide(p, to_call, board, pot):
        calls.append(p.name)
        return ("fold", 0)

    monkeypatch.setattr(poker_web, "bot_decide_action", decide)
    players[0].folded = True  # human already folded before this drain started
    poker_web._run_betting_round(players, hand, board=[])
    # Tex folds -> Lucy and Cal (2) remain -- not done yet.
    # Lucy folds -> only Cal (1) remains -- must stop immediately, Cal never asked to act.
    assert hand["to_act"] == []
    assert calls == ["Tex", "Lucy"]  # Cal never got a turn
    assert players[3].folded is False  # Cal is the uncontested survivor


def test_apply_human_action_fold():
    players, hand = _make_hand([0, 1, 2])
    poker_web.apply_human_action(players, hand, "fold", None)
    assert players[0].folded is True
    assert hand["to_act"] == [1, 2]


def test_apply_human_action_check():
    players, hand = _make_hand([0, 1, 2], current_max_bet=0)
    poker_web.apply_human_action(players, hand, "check", None)
    assert players[0].folded is False
    assert players[0].current_bet == 0
    assert hand["to_act"] == [1, 2]


def test_apply_human_action_call():
    players, hand = _make_hand([0, 1, 2], current_max_bet=6)
    poker_web.apply_human_action(players, hand, "call", None)
    assert players[0].current_bet == 6
    assert players[0].stack == 44
    assert hand["to_act"] == [1, 2]


def test_apply_human_action_raise_reopens_action():
    players, hand = _make_hand([0, 1, 2], current_max_bet=2)
    poker_web.apply_human_action(players, hand, "raise", 10)
    assert players[0].current_bet == 10
    assert hand["current_max_bet"] == 10
    assert hand["to_act"] == [1, 2]  # reset from order, excluding the raiser


def test_apply_human_action_allin_computes_amount_serverside():
    players, hand = _make_hand([0, 1, 2], current_max_bet=2)
    poker_web.apply_human_action(players, hand, "allin", 999)  # client value must be ignored
    assert players[0].current_bet == 50  # their full stack, not 999
    assert players[0].stack == 0
    assert players[0].all_in is True
    assert hand["current_max_bet"] == 50
