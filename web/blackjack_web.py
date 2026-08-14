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


from games.blackjack import hand_value, resolve_round


class _BankrollAdapter:
    """Duck-types games.blackjack.resolve_round's bankroll parameter."""

    def __init__(self):
        self.balance = 0

    def deposit(self, amount):
        self.balance += amount


class _NoOpStats:
    """Duck-types resolve_round's stats parameter -- web stats aren't tracked yet."""

    def record(self, game, wagered=0, won=0, jackpot=False):
        pass


def _hand_outcome(hand, dealer_value, dealer_had_blackjack):
    if hand.is_natural_blackjack and not dealer_had_blackjack:
        return "blackjack"
    if hand.result == "charlie":
        return "charlie"
    if hand.busted:
        return "bust"
    dealer_busted = dealer_value > 21
    if dealer_busted or hand.value > dealer_value:
        return "win"
    if hand.value == dealer_value:
        return "push"
    return "lose"


def _resolve(state, dealer_had_blackjack):
    hands = [hand_from_json(h) for h in state["hands"]]
    dealer_cards = [card_from_json(c) for c in state["dealer_cards"]]

    bankroll = _BankrollAdapter()
    resolve_round(bankroll, _NoOpStats(), hands, dealer_cards, state["insurance_bet"], dealer_had_blackjack)

    dealer_value, _ = hand_value(dealer_cards)
    hand_dicts = []
    for h in hands:
        d = hand_to_json(h)
        d["outcome"] = _hand_outcome(h, dealer_value, dealer_had_blackjack)
        hand_dicts.append(d)

    state["hands"] = hand_dicts
    state["phase"] = "resolved"
    return state, bankroll.balance


def start_round(bet):
    player_cards = [draw_card(), draw_card()]
    dealer_cards = [draw_card(), draw_card()]
    hand = Hand(player_cards, bet)

    state = {
        "dealer_cards": [card_to_json(c) for c in dealer_cards],
        "hands": [hand_to_json(hand)],
        "active_index": 0,
        "insurance_bet": 0,
        "split_count": 0,
        "phase": "player_turn",
    }

    # Insurance is offered purely on the up-card being an Ace, decided BEFORE
    # anything looks at the hole card -- matching real Blackjack and the CLI's
    # own play_round(), which calls offer_insurance() unconditionally on an
    # Ace up-card, ahead of ever computing dealer_had_blackjack. Do not
    # reorder this: checking dealer_had_blackjack first would skip the
    # insurance step whenever the dealer happens to actually have blackjack,
    # which is exactly the case insurance exists for.
    upcard = dealer_cards[1]
    if upcard.rank == 'A':
        state["phase"] = "insurance_offer"
        return state, 0

    dealer_had_blackjack = upcard.blackjack_value == 10 and hand_value(dealer_cards)[0] == 21
    if dealer_had_blackjack or hand.is_natural_blackjack:
        return _resolve(state, dealer_had_blackjack)
    return state, 0


def apply_insurance(state, decision, balance):
    if state["phase"] != "insurance_offer":
        return state, 0, 0

    hands = [hand_from_json(h) for h in state["hands"]]
    dealer_cards = [card_from_json(c) for c in state["dealer_cards"]]
    dealer_had_blackjack = hand_value(dealer_cards)[0] == 21

    cost = 0
    if decision == "accept":
        candidate = hands[0].bet // 2
        if 0 < candidate <= balance:
            cost = candidate
            state["insurance_bet"] = cost

    if dealer_had_blackjack:
        resolved_state, winnings = _resolve(state, True)
        return resolved_state, cost, winnings
    if hands[0].is_natural_blackjack:
        resolved_state, winnings = _resolve(state, False)
        return resolved_state, cost, winnings

    state["phase"] = "player_turn"
    return state, cost, 0


from games.blackjack import MAX_SPLITS, dealer_should_hit


def _hand_done(hand):
    return hand.busted or hand.stood or hand.result == "charlie" or hand.from_split_aces


def apply_action(state, action, balance):
    if state["phase"] != "player_turn":
        return state, 0, 0

    hands = [hand_from_json(h) for h in state["hands"]]
    dealer_cards = [card_from_json(c) for c in state["dealer_cards"]]
    i = state["active_index"]
    hand = hands[i]
    cost = 0

    if action == "hit":
        hand.cards.append(draw_card())
        value, _ = hand_value(hand.cards)
        if value > 21:
            hand.busted = True
        elif len(hand.cards) >= 5:
            hand.result = "charlie"
            hand.stood = True
    elif action == "stand":
        hand.stood = True
    elif action == "double":
        if len(hand.cards) == 2 and balance >= hand.bet:
            cost = hand.bet
            hand.bet *= 2
            hand.doubled = True
            hand.cards.append(draw_card())
            hand.stood = True
            value, _ = hand_value(hand.cards)
            if value > 21:
                hand.busted = True
    elif action == "split":
        can_split = (
            len(hand.cards) == 2
            and hand.cards[0].rank == hand.cards[1].rank
            and state["split_count"] < MAX_SPLITS
            and balance >= hand.bet
        )
        if can_split:
            cost = hand.bet
            state["split_count"] += 1
            is_ace_split = hand.cards[0].rank == 'A'
            first_card, second_card = hand.cards[0], hand.cards[1]
            hand.cards = [first_card, draw_card()]
            hand.from_split_aces = is_ace_split
            new_hand = Hand([second_card, draw_card()], hand.bet, from_split_aces=is_ace_split)
            hands.insert(i + 1, new_hand)

    while i < len(hands) and _hand_done(hands[i]):
        i += 1

    state["active_index"] = i
    state["hands"] = [hand_to_json(h) for h in hands]
    state["dealer_cards"] = [card_to_json(c) for c in dealer_cards]

    if i >= len(hands):
        any_live = any(not h.busted and h.result != "charlie" for h in hands)
        if any_live:
            while dealer_should_hit(dealer_cards):
                dealer_cards.append(draw_card())
            state["dealer_cards"] = [card_to_json(c) for c in dealer_cards]
        resolved_state, winnings = _resolve(state, False)
        return resolved_state, cost, winnings

    return state, cost, 0
