"""Session-state glue between games/blackjack.py's pure logic and the Flask web app."""
import random

import cards
from games.blackjack import Hand

SUIT_SYMBOLS = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
RED_SUITS = {'H', 'D'}


def draw_card():
    """Independent random draw, not a persisted shoe -- see design spec."""
    return cards.Card(random.choice(cards.RANKS), random.choice(cards.SUITS))


def card_to_json(card):
    return [card.rank, card.suit]


def card_from_json(pair):
    return cards.Card(pair[0], pair[1])


def suit_symbol(suit):
    return SUIT_SYMBOLS[suit]


def is_red_suit(suit):
    return suit in RED_SUITS


def hand_to_json(hand):
    return {
        "cards": [card_to_json(c) for c in hand.cards],
        "bet": hand.bet,
        "doubled": hand.doubled,
        "from_split_aces": hand.from_split_aces,
        "stood": hand.stood,
        "busted": hand.busted,
        "result": hand.result,
    }


def hand_from_json(d):
    hand = Hand(
        [card_from_json(c) for c in d["cards"]],
        d["bet"],
        from_split_aces=d["from_split_aces"],
    )
    hand.doubled = d["doubled"]
    hand.stood = d["stood"]
    hand.busted = d["busted"]
    hand.result = d["result"]
    return hand
