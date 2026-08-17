"""Session-state glue between games/poker.py's pure logic and the Flask web app."""
import cards
from games.poker import Player, SMALL_BLIND, BIG_BLIND, apply_action, bot_decide_action

SEATS = [
    {"name": "You", "is_bot": False, "personality": None},
    {"name": "Tex", "is_bot": True, "personality": "TAG"},
    {"name": "Lucy", "is_bot": True, "personality": "LAG"},
    {"name": "Cal", "is_bot": True, "personality": "Station"},
]


def card_to_json(card):
    return [card.rank, card.suit]


def card_from_json(pair):
    return cards.Card(pair[0], pair[1])


SUIT_SYMBOLS = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
RED_SUITS = {'H', 'D'}


def suit_symbol(suit):
    return SUIT_SYMBOLS[suit]


def is_red_suit(suit):
    return suit in RED_SUITS


def start_table(buy_in):
    return {
        "players": [
            {"name": seat["name"], "stack": buy_in, "is_bot": seat["is_bot"], "personality": seat["personality"]}
            for seat in SEATS
        ],
        "button_idx": 0,
        "buy_in": buy_in,
    }


def rebuy_broke_bots(table):
    for p in table["players"]:
        if p["is_bot"] and p["stack"] <= 0:
            p["stack"] = table["buy_in"]
    return table


def _players_from_table(table):
    return [
        Player(p["name"], p["stack"], is_bot=p["is_bot"], personality=p["personality"])
        for p in table["players"]
    ]


def _player_hand_to_json(p):
    return {
        "hole": [card_to_json(c) for c in p.hole],
        "current_bet": p.current_bet,
        "total_committed": p.total_committed,
        "folded": p.folded,
        "all_in": p.all_in,
        "showdown_score": None,
    }


def _to_act_from_order(order, players):
    """Betting only happens with 2+ players who can still act -- matches
    games/poker.py's betting_round(), which returns immediately whenever
    len(active) <= 1 (nobody left who can respond to a bet)."""
    active = [i for i in order if not players[i].folded and not players[i].all_in]
    return active if len(active) > 1 else []


def deal_new_hand(table):
    players = _players_from_table(table)
    n = len(players)
    deck = cards.new_deck()
    for p in players:
        p.hole = [deck.pop(), deck.pop()]

    button_idx = table["button_idx"]
    sb_idx = (button_idx + 1) % n
    bb_idx = (button_idx + 2) % n
    for idx, amt in ((sb_idx, SMALL_BLIND), (bb_idx, BIG_BLIND)):
        pay = min(amt, players[idx].stack)
        players[idx].stack -= pay
        players[idx].current_bet += pay
        players[idx].total_committed += pay
        if players[idx].stack == 0:
            players[idx].all_in = True

    for i, p in enumerate(players):
        table["players"][i]["stack"] = p.stack

    first_to_act = (bb_idx + 1) % n
    order = [(first_to_act + i) % n for i in range(n)]
    current_max_bet = max((players[i].current_bet for i in range(n) if not players[i].folded), default=0)

    return {
        "phase": "player_turn",
        "street": "preflop",
        "sb_idx": sb_idx,
        "deck": [card_to_json(c) for c in deck],
        "board": [],
        "players": [_player_hand_to_json(p) for p in players],
        "order": order,
        "current_max_bet": current_max_bet,
        "to_act": _to_act_from_order(order, players),
        "log": [],
    }


def _log_bot_action(hand, name, action, amount):
    if action == "fold":
        hand["log"].append(f"{name} folds.")
    elif action == "check":
        hand["log"].append(f"{name} checks.")
    elif action == "call":
        hand["log"].append(f"{name} calls.")
    elif action == "raise":
        hand["log"].append(f"{name} raises to {amount}.")
    elif action == "allin":
        hand["log"].append(f"{name} goes all-in ({amount} pts)!")


def _reset_to_act_after_raise(hand, players, actor_idx):
    hand["to_act"] = [
        j for j in hand["order"]
        if j != actor_idx and not players[j].folded and not players[j].all_in
    ]


def _run_betting_round(players, hand, board):
    while hand["to_act"]:
        # Matches games/poker.py's betting_round(), which breaks out of its
        # queue immediately once at most one player still has agency --
        # nobody left who can respond to a bet. Checked before popping the
        # next entry so a bot (or the human) is never asked to act on a hand
        # that's already effectively over.
        if sum(1 for p in players if not p.folded) <= 1:
            hand["to_act"] = []
            return

        i = hand["to_act"][0]
        p = players[i]

        if p.folded or p.all_in:
            hand["to_act"].pop(0)
            continue

        if i == 0:
            return  # pause here -- it's the human's turn

        hand["to_act"].pop(0)
        to_call = hand["current_max_bet"] - p.current_bet
        pot = sum(pl.total_committed for pl in players)
        action, amount = bot_decide_action(p, to_call, board, pot)
        new_max, raised = apply_action(p, action, amount, hand["current_max_bet"])
        hand["current_max_bet"] = new_max
        _log_bot_action(hand, p.name, action, amount)
        if raised:
            _reset_to_act_after_raise(hand, players, i)


def apply_human_action(players, hand, action, amount):
    """Applies players[0]'s decision. Caller guarantees it's actually their turn."""
    p = players[0]
    if action == "allin":
        amount = p.current_bet + p.stack
    elif action in ("fold", "check", "call"):
        amount = 0
    # action == "raise": amount is the caller-validated target, used as-is

    hand["to_act"].pop(0)
    new_max, raised = apply_action(p, action, amount, hand["current_max_bet"])
    hand["current_max_bet"] = new_max
    if raised:
        _reset_to_act_after_raise(hand, players, 0)
