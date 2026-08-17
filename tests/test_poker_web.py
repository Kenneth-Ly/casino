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


def _state_from_deal(monkeypatch, tail_cards, button_idx=0):
    _fixed_deck(monkeypatch, tail_cards)
    table = poker_web.start_table(50)
    table["button_idx"] = button_idx
    hand = poker_web.deal_new_hand(table)
    return {"table": table, "hand": hand}


def test_advance_hand_resolves_preflop_by_foldout(monkeypatch):
    tail = [cards.Card(r, 'S') for r in ['A', 'K', 'Q', 'J', '10', '9', '8', '7']]
    state = _state_from_deal(monkeypatch, tail)  # order preflop: [3, 0, 1, 2]
    monkeypatch.setattr(poker_web, "bot_decide_action", lambda p, to_call, board, pot: ("fold", 0))
    state = poker_web.advance(state)  # Cal (3) folds, then it's the human's turn
    assert state["hand"]["phase"] == "player_turn"
    assert state["hand"]["to_act"] == [0, 1, 2]
    state = poker_web.advance(state, "fold", None)
    # human folds too -- Tex (1) and Lucy (2) still to act; Tex folds, only Lucy left -> uncontested
    assert state["hand"]["phase"] == "resolved"
    # Lucy (bb, contributed 2) wins the pot: sb(1) + bb(2) = 3 total committed
    assert state["table"]["players"][2]["stack"] == 50 - 2 + 3


def test_advance_deals_next_street_when_betting_round_completes(monkeypatch):
    tail = [
        cards.Card('A', 'S'), cards.Card('K', 'S'),
        cards.Card('Q', 'S'), cards.Card('J', 'S'),
        cards.Card('10', 'S'), cards.Card('9', 'S'),
        cards.Card('8', 'S'), cards.Card('7', 'S'),
        cards.Card('6', 'S'),                          # burn
        cards.Card('5', 'S'), cards.Card('4', 'S'), cards.Card('3', 'S'),  # flop
    ]
    state = _state_from_deal(monkeypatch, tail)

    def bot_policy(p, to_call, board, pot):
        return ("call", 0) if to_call > 0 else ("check", 0)

    monkeypatch.setattr(poker_web, "bot_decide_action", bot_policy)

    guard = 0
    while state["hand"]["street"] == "preflop":
        guard += 1
        assert guard < 20, "preflop betting round never closed"
        if state["hand"]["to_act"] and state["hand"]["to_act"][0] == 0:
            to_call = state["hand"]["current_max_bet"] - state["hand"]["players"][0]["current_bet"]
            action = "call" if to_call > 0 else "check"
            state = poker_web.advance(state, action, None)
        else:
            state = poker_web.advance(state)

    assert state["hand"]["street"] == "flop"
    assert len(state["hand"]["board"]) == 3
    assert all(p["current_bet"] == 0 for p in state["hand"]["players"])


def test_advance_full_hand_to_showdown_clear_winner(monkeypatch):
    # Everyone checks/calls every street -- deterministic bot policy -- hand goes to showdown.
    tail = [
        cards.Card('A', 'S'), cards.Card('A', 'H'),   # You: pocket rockets
        cards.Card('2', 'D'), cards.Card('3', 'D'),   # Tex
        cards.Card('4', 'C'), cards.Card('5', 'C'),   # Lucy
        cards.Card('6', 'H'), cards.Card('7', 'H'),   # Cal
        cards.Card('9', 'S'),                          # burn (preflop->flop)
        cards.Card('K', 'D'), cards.Card('Q', 'D'), cards.Card('J', 'C'),  # flop
        cards.Card('8', 'S'),                          # burn
        cards.Card('10', 'S'),                         # turn -- completes You's broadway straight
        cards.Card('7', 'S'),                          # burn
        cards.Card('8', 'H'),                          # river -- doesn't pair/connect anyone else's hole cards
    ]
    state = _state_from_deal(monkeypatch, tail)

    def bot_policy(p, to_call, board, pot):
        return ("call", 0) if to_call > 0 else ("check", 0)

    monkeypatch.setattr(poker_web, "bot_decide_action", bot_policy)

    # Drive the whole hand: whenever it's the human's turn, check/call; otherwise let bots auto-play.
    guard = 0
    while state["hand"]["phase"] != "resolved":
        guard += 1
        assert guard < 50, "hand never resolved -- infinite loop"
        if state["hand"]["to_act"] and state["hand"]["to_act"][0] == 0:
            to_call = state["hand"]["current_max_bet"] - state["hand"]["players"][0]["current_bet"]
            action = "call" if to_call > 0 else "check"
            state = poker_web.advance(state, action, None)
        else:
            state = poker_web.advance(state)

    assert state["hand"]["street"] == "river"
    assert len(state["hand"]["board"]) == 5
    # Pocket aces beats everything else dealt here -- You must win the whole pot.
    assert state["table"]["players"][0]["stack"] > 50 - 2  # net winner (started as sb-ish net payer, ends up up)
    total_stacks = sum(p["stack"] for p in state["table"]["players"])
    assert total_stacks == 200  # chip-conservation: 4 * 50 buy-in, nothing created or destroyed


def test_advance_all_but_one_all_in_runs_out_board_automatically(monkeypatch):
    # Uneven stacks: You/Tex/Lucy are deep (30 each), Cal is a short stack
    # (12). When everyone shoves, contributions land at two different
    # levels (12 and 30), so build_pots() must split into a main pot (all
    # four players eligible) plus a side pot (only the three deep stacks
    # eligible -- Cal can't win chips beyond what he put in).
    #
    # Hole cards are rigged so hand strength is fully deterministic and
    # strictly ordered: Cal > You > Tex > Lucy. Board = K D, Q D, J C, 10 S,
    # 8 H (no flush possible; only Cal has a card that completes a straight).
    #   Cal:  A S, A H -> A-K-Q-J-10 straight (best hand at the table)
    #   You:  K H, Q H -> two pair, Kings and Queens (second-best)
    #   Tex:  3 C, 3 D -> pair of Threes (third)
    #   Lucy: 2 C, 2 D -> pair of Twos (worst)
    #
    # Cal, with the best hand overall, is only eligible for the main pot
    # (capped at his 12-chip contribution) -- he must NOT win any of the
    # side pot. You, the best hand among the three deep stacks, wins the
    # side pot outright. If build_pots() mis-treated this as a single pot,
    # Cal (best hand overall) would scoop the entire 102-chip pot instead.
    tail = [
        cards.Card('K', 'H'), cards.Card('Q', 'H'),   # You
        cards.Card('3', 'C'), cards.Card('3', 'D'),   # Tex
        cards.Card('2', 'C'), cards.Card('2', 'D'),   # Lucy
        cards.Card('A', 'S'), cards.Card('A', 'H'),   # Cal
        cards.Card('4', 'H'),                          # burn (preflop->flop)
        cards.Card('K', 'D'), cards.Card('Q', 'D'), cards.Card('J', 'C'),  # flop
        cards.Card('5', 'D'),                          # burn
        cards.Card('10', 'S'),                         # turn
        cards.Card('6', 'C'),                          # burn
        cards.Card('8', 'H'),                          # river
    ]
    _fixed_deck(monkeypatch, tail)
    table = poker_web.start_table(30)
    table["players"][3]["stack"] = 12  # Cal -- short stack, forces a side pot
    hand = poker_web.deal_new_hand(table)
    state = {"table": table, "hand": hand}

    def bot_policy(p, to_call, board, pot):
        return ("allin", p.current_bet + p.stack)

    monkeypatch.setattr(poker_web, "bot_decide_action", bot_policy)

    # Human calls the all-ins with their own stack (also effectively all-in via a call).
    state = poker_web.advance(state)  # Cal (order[0]) goes all-in preflop, reopening to everyone
    while state["hand"]["phase"] != "resolved" and state["hand"]["to_act"] and state["hand"]["to_act"][0] == 0:
        state = poker_web.advance(state, "allin", None)
    # Once everyone's all-in, advance() must run the board out to showdown without any further pauses.
    guard = 0
    while state["hand"]["phase"] != "resolved":
        guard += 1
        assert guard < 10
        state = poker_web.advance(state)
    assert state["hand"]["phase"] == "resolved"
    assert len(state["hand"]["board"]) == 5

    stacks = [p["stack"] for p in state["table"]["players"]]
    assert sum(stacks) == 30 + 30 + 30 + 12  # chip-conservation

    # Main pot (48 = 12 x 4, all eligible) -> Cal (best hand overall).
    # Side pot (54 = 18 x 3, You/Tex/Lucy eligible) -> You (best of that trio).
    assert stacks == [54, 0, 0, 48]
