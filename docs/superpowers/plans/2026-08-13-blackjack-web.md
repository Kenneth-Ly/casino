# Blackjack Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the CLI's Blackjack to the web app with full feature parity (splits, double down, insurance, 5-Card Charlie), reusing `games/blackjack.py`'s pure logic unmodified.

**Architecture:** New `web/blackjack_web.py` glue module bridges JSON-safe session state (cards as `[rank, suit]` pairs) and `games/blackjack.py`'s `Hand`/`Card` objects. Cards are drawn independently at random (`draw_card()`), not from a persisted shoe — statistically equivalent for a single round, and keeps the session cookie small. `web/app.py` gets 4 new routes, each re-rendering one HTMX partial (`_blackjack_table.html`), same request/response shape as Slots.

**Tech Stack:** Same as Phase 1 — Flask, HTMX, Jinja2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-13-blackjack-web-design.md`

## Global Constraints

- `games/blackjack.py`, `cards.py`, and the rest of the CLI are not modified — reused unmodified via import.
- Card drawing is independent random draws (`Card(random.choice(RANKS), random.choice(SUITS))`), not a persisted shoe.
- `session['balance']` stays the single value shared across all games (already established by Slots) — Blackjack reads/writes the same key, never a separate one.
- `session['blackjack']` holds round state only while a round is active; absent/`None` means no round in progress.
- Card faces render as realistic white/cream rectangles with true playing-card red (`#B3122A`) ink for hearts/diamonds, black for spades/clubs — not flat neon-colored text chips. Approved via visual mockup.
- Every route re-validates state server-side (phase checks, double/split eligibility) rather than trusting what the UI displayed.
- The existing 18-test suite must keep passing throughout.

---

## Task 1: Card serialization and drawing

**Files:**
- Create: `web/blackjack_web.py`
- Test: `tests/test_blackjack_web.py`

**Interfaces:**
- Produces: `draw_card() -> cards.Card`, `card_to_json(card) -> list[str, str]`, `card_from_json(pair) -> cards.Card`, `suit_symbol(suit: str) -> str`, `is_red_suit(suit: str) -> bool`, `hand_to_json(hand: games.blackjack.Hand) -> dict`, `hand_from_json(d: dict) -> games.blackjack.Hand`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_blackjack_web.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_blackjack_web.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.blackjack_web'`

- [ ] **Step 3: Write minimal implementation**

Create `web/blackjack_web.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_blackjack_web.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add web/blackjack_web.py tests/test_blackjack_web.py
git commit -m "Add card/hand serialization glue for Blackjack web"
```

---

## Task 2: Round orchestration — deal and insurance

**Files:**
- Modify: `web/blackjack_web.py`
- Modify: `tests/test_blackjack_web.py`

**Interfaces:**
- Consumes: `draw_card`, `card_to_json`, `card_from_json`, `hand_to_json`, `hand_from_json` (Task 1); `games.blackjack.Hand`, `hand_value`, `resolve_round` (existing, unmodified).
- Produces: `start_round(bet: int) -> (state: dict, winnings: int)`, `apply_insurance(state: dict, decision: str, balance: int) -> (state: dict, cost: int, winnings: int)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_blackjack_web.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_blackjack_web.py -v`
Expected: FAIL — `AttributeError: module 'web.blackjack_web' has no attribute 'start_round'`

- [ ] **Step 3: Write minimal implementation**

Append to `web/blackjack_web.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_blackjack_web.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add web/blackjack_web.py tests/test_blackjack_web.py
git commit -m "Add Blackjack deal and insurance orchestration"
```

---

## Task 3: Round orchestration — player actions and resolution

**Files:**
- Modify: `web/blackjack_web.py`
- Modify: `tests/test_blackjack_web.py`

**Interfaces:**
- Consumes: everything from Tasks 1-2, plus `games.blackjack.dealer_should_hit` (existing, unmodified).
- Produces: `apply_action(state: dict, action: str, balance: int) -> (state: dict, cost: int, winnings: int)`. `action` is one of `"hit"`, `"stand"`, `"double"`, `"split"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_blackjack_web.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_blackjack_web.py -v`
Expected: FAIL — `AttributeError: module 'web.blackjack_web' has no attribute 'apply_action'`

- [ ] **Step 3: Write minimal implementation**

Append to `web/blackjack_web.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_blackjack_web.py -v`
Expected: 22 passed

- [ ] **Step 5: Commit**

```bash
git add web/blackjack_web.py tests/test_blackjack_web.py
git commit -m "Add Blackjack player action and resolution orchestration"
```

---

## Task 4: Flask routes, templates, and CSS

**Files:**
- Modify: `web/app.py`
- Create: `web/templates/blackjack.html`
- Create: `web/templates/_blackjack_table.html`
- Modify: `web/static/style.css` (append)
- Create: `tests/test_app_blackjack.py`

**Interfaces:**
- Consumes: `blackjack_web.start_round`, `apply_insurance`, `apply_action`, `suit_symbol`, `is_red_suit`, `MAX_SPLITS` (Tasks 1-3); `web/validation.py`'s `validate_bet` (existing); `web/db.py`'s `get_global_record`/`update_global_record` (existing).
- Produces: routes `GET /blackjack` (`blackjack_page`), `POST /blackjack/deal` (`blackjack_deal`), `POST /blackjack/insurance` (`blackjack_insurance`), `POST /blackjack/action` (`blackjack_action`), `POST /blackjack/next` (`blackjack_next`).

This task also extracts the existing inline DB-record-update try/except (currently duplicated once in `lobby()` and once in `slots_spin()`) into one shared helper, since Blackjack needs the identical pattern a third time. This is a small, behavior-preserving refactor of already-reviewed code — not new scope, just removing a duplication that would otherwise triple.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_blackjack.py`:

```python
import cards as cards_mod
from web.app import app
from web import blackjack_web


def make_client(monkeypatch, record=50):
    monkeypatch.setattr("web.app.db.get_global_record", lambda: record)
    monkeypatch.setattr("web.app.db.update_global_record", lambda balance: None)
    app.config["TESTING"] = True
    return app.test_client()


def _queue(monkeypatch, card_list):
    it = iter(card_list)
    monkeypatch.setattr(blackjack_web, "draw_card", lambda: next(it))


def test_blackjack_page_shows_bet_form(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/blackjack")
    assert resp.status_code == 200
    assert b"Deal" in resp.data


def test_deal_with_invalid_bet_shows_error(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    resp = client.post("/blackjack/deal", data={"bet": "abc"})
    assert resp.status_code == 200
    assert b"Enter a whole number" in resp.data


def test_deal_player_blackjack_credits_balance(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('A', 'H'), cards_mod.Card('K', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
    ])
    resp = client.post("/blackjack/deal", data={"bet": "10"})
    assert resp.status_code == 200
    assert b"65" in resp.data  # 50 - 10 bet + 25 payout = 65


def test_deal_dealer_ace_upcard_shows_insurance_prompt(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('9', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('A', 'C'),
    ])
    resp = client.post("/blackjack/deal", data={"bet": "10"})
    assert resp.status_code == 200
    assert b"insurance" in resp.data.lower()


def test_full_hit_stand_flow_resolves_and_credits(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('5', 'H'), cards_mod.Card('4', 'S'),   # player 9
        cards_mod.Card('9', 'D'), cards_mod.Card('2', 'C'),   # dealer 11
        cards_mod.Card('K', 'H'),                              # hit -> 19
        cards_mod.Card('K', 'S'),                              # dealer draws -> 21... make dealer bust instead
    ])
    client.post("/blackjack/deal", data={"bet": "10"})
    resp = client.post("/blackjack/action", data={"action": "hit"})
    assert resp.status_code == 200
    resp = client.post("/blackjack/action", data={"action": "stand"})
    assert resp.status_code == 200
    assert b"Play Another Hand" in resp.data


def test_split_flow_creates_two_hands_in_response(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('8', 'H'), cards_mod.Card('8', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
        cards_mod.Card('3', 'H'), cards_mod.Card('4', 'S'),
    ])
    client.post("/blackjack/deal", data={"bet": "10"})
    resp = client.post("/blackjack/action", data={"action": "split"})
    assert resp.status_code == 200
    assert b"Your Hand 1/2" in resp.data
    assert b"Your Hand 2/2" in resp.data


def test_next_clears_round_back_to_bet_form(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/blackjack")
    _queue(monkeypatch, [
        cards_mod.Card('A', 'H'), cards_mod.Card('K', 'S'),
        cards_mod.Card('9', 'D'), cards_mod.Card('7', 'C'),
    ])
    client.post("/blackjack/deal", data={"bet": "10"})
    resp = client.post("/blackjack/next")
    assert resp.status_code == 200
    assert b"Deal" in resp.data


def test_action_with_no_round_in_session_does_not_crash(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/blackjack/action", data={"action": "hit"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_blackjack.py -v`
Expected: FAIL — `AttributeError: module 'web.app' has no attribute ...` (routes don't exist yet)

- [ ] **Step 3: Refactor the existing DB-record-update helper**

In `web/app.py`, find the two existing inline blocks:
```python
    try:
        record = db.get_global_record()
    except Exception as exc:
        app.logger.warning("global record read skipped: %s", type(exc).__name__)
        record = None
```
(in `lobby()`) and:
```python
    try:
        db.update_global_record(balance)
    except Exception as exc:
        app.logger.warning("global record update skipped: %s", type(exc).__name__)
```
(in `slots_spin()`). Leave `lobby()`'s block exactly as-is (it's a *read*, this refactor is only for the *write*/update pattern). Add this helper function near the top of `web/app.py`, after `get_stats()`:

```python
def _maybe_update_record(balance):
    try:
        db.update_global_record(balance)
    except Exception as exc:
        app.logger.warning("global record update skipped: %s", type(exc).__name__)
```

Replace `slots_spin()`'s inline try/except block with a call to `_maybe_update_record(balance)`.

- [ ] **Step 4: Write the routes**

Add to `web/app.py` (near the existing Slots routes), after importing `blackjack_web` alongside the existing `slots` import (`from games import slots` becomes `from games import slots` plus a new `from web import blackjack_web` import near the existing `from web import db, validation` line):

```python
def render_blackjack_table(balance, state, error=None):
    return render_template(
        "_blackjack_table.html",
        balance=balance,
        state=state,
        error=error,
        suit_symbol=blackjack_web.suit_symbol,
        is_red_suit=blackjack_web.is_red_suit,
        max_splits=blackjack_web.MAX_SPLITS,
    )


@app.route("/blackjack")
def blackjack_page():
    return render_template(
        "blackjack.html",
        balance=get_balance(),
        state=session.get("blackjack"),
        suit_symbol=blackjack_web.suit_symbol,
        is_red_suit=blackjack_web.is_red_suit,
        max_splits=blackjack_web.MAX_SPLITS,
    )


@app.route("/blackjack/deal", methods=["POST"])
def blackjack_deal():
    balance = get_balance()
    amount, error = validation.validate_bet(request.form.get("bet", ""), balance)
    if error:
        return render_blackjack_table(balance, None, error=error)

    balance -= amount
    state, winnings = blackjack_web.start_round(amount)
    balance += winnings
    session["balance"] = balance
    session["blackjack"] = state
    if winnings:
        _maybe_update_record(balance)
    return render_blackjack_table(balance, state)


@app.route("/blackjack/insurance", methods=["POST"])
def blackjack_insurance():
    balance = get_balance()
    state = session.get("blackjack")
    if not state:
        return render_blackjack_table(balance, None)

    decision = request.form.get("decision", "decline")
    state, cost, winnings = blackjack_web.apply_insurance(state, decision, balance)
    balance = balance - cost + winnings
    session["balance"] = balance
    session["blackjack"] = state
    if winnings:
        _maybe_update_record(balance)
    return render_blackjack_table(balance, state)


@app.route("/blackjack/action", methods=["POST"])
def blackjack_action():
    balance = get_balance()
    state = session.get("blackjack")
    if not state:
        return render_blackjack_table(balance, None)

    action = request.form.get("action", "")
    state, cost, winnings = blackjack_web.apply_action(state, action, balance)
    balance = balance - cost + winnings
    session["balance"] = balance
    session["blackjack"] = state
    if winnings:
        _maybe_update_record(balance)
    return render_blackjack_table(balance, state)


@app.route("/blackjack/next", methods=["POST"])
def blackjack_next():
    session.pop("blackjack", None)
    return render_blackjack_table(get_balance(), None)
```

- [ ] **Step 5: Write the templates**

Create `web/templates/blackjack.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Blackjack</h1>
<div id="game-panel">
  {% include "_blackjack_table.html" %}
</div>
{% endblock %}
```

Create `web/templates/_blackjack_table.html`:

```html
<div class="panel">
  <p class="balance">Balance: {{ balance }} pts</p>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  {% if not state %}
  <form hx-post="{{ url_for('blackjack_deal') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <label>Bet (1-{{ balance }}): <input type="text" name="bet" value="1"></label>
    <button type="submit">Deal</button>
  </form>

  {% else %}

  <div class="section-label">Dealer</div>
  <div class="hand-row">
    {% for c in state.dealer_cards %}
      {% if loop.index0 == 0 and state.phase != 'resolved' %}
        <div class="card back"></div>
      {% else %}
        <div class="card {{ 'red' if is_red_suit(c[1]) else 'black' }}">
          <div class="corner tl">{{ c[0] }}<br>{{ suit_symbol(c[1]) }}</div>
          <div class="pip">{{ suit_symbol(c[1]) }}</div>
          <div class="corner br">{{ c[0] }}<br>{{ suit_symbol(c[1]) }}</div>
        </div>
      {% endif %}
    {% endfor %}
  </div>

  {% for hand in state.hands %}
  <div class="section-label">
    Your Hand {{ loop.index }}/{{ state.hands|length }}{% if state.phase == 'player_turn' and loop.index0 == state.active_index %} <span class="active-tag">&lt;--</span>{% endif %}
  </div>
  <div class="hand-row">
    {% for c in hand.cards %}
    <div class="card {{ 'red' if is_red_suit(c[1]) else 'black' }}">
      <div class="corner tl">{{ c[0] }}<br>{{ suit_symbol(c[1]) }}</div>
      <div class="pip">{{ suit_symbol(c[1]) }}</div>
      <div class="corner br">{{ c[0] }}<br>{{ suit_symbol(c[1]) }}</div>
    </div>
    {% endfor %}
  </div>
  <div class="hand-meta">
    Bet: {{ hand.bet }}
    {% if state.phase == 'resolved' %}
      {% if hand.outcome == 'blackjack' %} | Blackjack! +{{ hand.bet * 3 // 2 }} pts
      {% elif hand.outcome == 'charlie' %} | 5-Card Charlie! +{{ hand.bet }} pts
      {% elif hand.outcome == 'bust' %} | Bust. -{{ hand.bet }} pts
      {% elif hand.outcome == 'win' %} | Win! +{{ hand.bet }} pts
      {% elif hand.outcome == 'push' %} | Push
      {% elif hand.outcome == 'lose' %} | Lose. -{{ hand.bet }} pts
      {% endif %}
    {% elif hand.busted %} | BUST
    {% endif %}
  </div>
  {% endfor %}

  {% if state.phase == 'insurance_offer' %}
  <p>Dealer shows an Ace. Buy insurance for {{ state.hands[0].bet // 2 }} pts?</p>
  <form hx-post="{{ url_for('blackjack_insurance') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <button type="submit" name="decision" value="accept">Buy Insurance</button>
    <button type="submit" name="decision" value="decline">No Thanks</button>
  </form>
  {% endif %}

  {% if state.phase == 'player_turn' %}
  {% set active = state.hands[state.active_index] %}
  <form hx-post="{{ url_for('blackjack_action') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <button type="submit" name="action" value="hit">Hit</button>
    <button type="submit" name="action" value="stand">Stand</button>
    {% if active.cards|length == 2 and balance >= active.bet %}
    <button type="submit" name="action" value="double">Double Down</button>
    {% endif %}
    {% if active.cards|length == 2 and active.cards[0][0] == active.cards[1][0] and state.split_count < max_splits and balance >= active.bet %}
    <button type="submit" name="action" value="split">Split</button>
    {% endif %}
  </form>
  {% endif %}

  {% if state.phase == 'resolved' %}
  <form hx-post="{{ url_for('blackjack_next') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <button type="submit">Play Another Hand</button>
  </form>
  {% endif %}

  {% endif %}
</div>
```

- [ ] **Step 6: Append the Blackjack CSS**

Append to the end of `web/static/style.css`:

```css

/* Blackjack */
.section-label {
  color: var(--gold);
  text-shadow: 0 0 8px rgba(255, 193, 59, 0.5);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  margin: 1.1rem 0 0.5rem;
}

.hand-row { display: flex; gap: 10px; align-items: flex-end; margin-bottom: 0.4rem; flex-wrap: wrap; }
.hand-meta { color: #E8E3F5; font-size: 0.8rem; opacity: 0.85; margin-bottom: 0.5rem; }
.active-tag { color: var(--gold); text-shadow: 0 0 6px rgba(255, 193, 59, 0.6); }

.card {
  width: 58px; height: 82px; border-radius: 7px; position: relative;
  background: linear-gradient(160deg, #FBF7EE 0%, #F1EADA 100%);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(0, 0, 0, 0.08);
  font-family: Georgia, 'Times New Roman', serif;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.card .corner { position: absolute; font-size: 13px; line-height: 1; font-weight: 700; text-align: center; }
.card .corner.tl { top: 5px; left: 6px; }
.card .corner.br { bottom: 5px; right: 6px; transform: rotate(180deg); }
.card .pip { font-size: 26px; }
.card.red { color: #B3122A; }
.card.black { color: #1a1a1a; }

.card.back {
  background: repeating-linear-gradient(45deg, var(--panel), var(--panel) 4px, #1f1440 4px, #1f1440 8px);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(51, 233, 255, 0.35), inset 0 0 0 3px var(--ink);
}
.card.back::after { content: "?"; color: var(--accent); text-shadow: 0 0 6px var(--accent); font-size: 22px; font-family: 'JetBrains Mono', monospace; }
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest -v`
Expected: 48 passed (18 from before Tasks 1-4 + 22 from `test_blackjack_web.py` + 8 from `test_app_blackjack.py`). If the actual count differs, treat it as a real signal to investigate — re-check Task 1-3's test counts rather than assuming this number is wrong.

- [ ] **Step 8: Manually verify a full round in the browser**

Run `flask --app web.app run --debug`, open `/blackjack`, play through: a normal hand to a win/loss, a hand where you double down, a hand where you split a pair, and (if you draw an Ace as the dealer's upcard) the insurance prompt. Confirm the dealer's hole card stays hidden until resolution and card faces render as white rectangles with correct red/black ink. Stop the dev server after.

- [ ] **Step 9: Commit**

```bash
git add web/app.py web/templates/blackjack.html web/templates/_blackjack_table.html web/static/style.css tests/test_app_blackjack.py
git commit -m "Add Blackjack routes, templates, and card-face styling"
```

---

## Task 5: Manual cross-scenario verification (controller-executed, no subagent)

Same right-sizing judgment as Phase 1 and the theme plan: no new code, a QA pass plus a final full-suite run.

- [ ] Run `pytest -v` — full suite passes.
- [ ] Via the dev server (curl or browser), play through and confirm: a natural blackjack win, a dealer blackjack loss, an insurance-accept-dealer-blackjack payout, a split producing two independently-resolved hands, a double-down, a 5-Card Charlie (if one comes up naturally, or trust Task 3's deterministic test coverage for this rare case), and a busted-then-"Play Another Hand" reset.
- [ ] Confirm the lobby's Blackjack tile now links to a live game instead of showing "coming soon" — this requires a small lobby template update (see below) that wasn't part of Tasks 1-4's scope.
- [ ] Update `web/templates/lobby.html`: change the Blackjack tile from `<div class="tile soon">...</div>` to `<a class="tile live" href="{{ url_for('blackjack_page') }}">` (same shape as the Slots tile), keeping Roulette and Poker as `soon`. Re-run `pytest -v` to confirm nothing broke, then commit: `git add web/templates/lobby.html && git commit -m "Link lobby's Blackjack tile to the live game"`.
- [ ] Confirm no console/template errors in the Flask dev server log during the walkthrough.
