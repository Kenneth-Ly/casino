"""Session-state glue between games/roulette.py's pure logic and the Flask web app."""
import random

from games import roulette

BET_TYPES = {bet_type for _, bet_type in roulette.BET_MENU}
BET_LABELS = {bet_type: label for label, bet_type in roulette.BET_MENU}


def fresh_state():
    return {"phase": "betting", "bets": [], "pocket": None, "color": None}


def remaining_balance(state, balance):
    return balance - sum(b["amount"] for b in state["bets"])


def _valid_straight_number(raw):
    raw = (raw or "").strip()
    if raw == "00":
        return "00"
    if raw.isdigit() and 0 <= int(raw) <= 36:
        return str(int(raw))
    return None


def add_bet(state, bet_type, number, amount):
    if bet_type not in BET_TYPES:
        return state, "Choose a valid bet type."

    value = None
    if bet_type == "straight":
        value = _valid_straight_number(number)
        if value is None:
            return state, "Enter a number 0-36 or 00 for a straight-up bet."

    state["bets"].append({
        "type": bet_type,
        "value": value,
        "amount": amount,
        "label": BET_LABELS[bet_type],
    })
    return state, None


def remove_bet(state, index):
    if 0 <= index < len(state["bets"]):
        state["bets"].pop(index)
    return state


def spin(state):
    if state["phase"] != "betting" or not state["bets"]:
        return state, 0, 0

    total_wager = sum(b["amount"] for b in state["bets"])
    pocket = random.choice(roulette.POCKETS)
    color = roulette.pocket_color(pocket)

    total_return = 0
    for b in state["bets"]:
        win = b["amount"] * roulette.evaluate_bet(b, pocket)
        b["win"] = win
        total_return += win

    state["pocket"] = pocket
    state["color"] = color
    state["phase"] = "resolved"
    return state, total_wager, total_return


def next_round():
    return fresh_state()
