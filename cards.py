"""Shared playing card primitives used by blackjack and poker."""
import random

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
# ASCII suit letters (not unicode symbols) -- Windows cmd's default codepage
# can't encode the unicode suit glyphs once colorama wraps stdout, so this
# keeps output crash-proof everywhere.
SUITS = ['S', 'H', 'D', 'C']  # Spades, Hearts, Diamonds, Clubs
SUIT_NAMES = {'S': 'Spades', 'H': 'Hearts', 'D': 'Diamonds', 'C': 'Clubs'}
RED_SUITS = {'H', 'D'}

RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS[:-1])}
RANK_VALUE['A'] = 14  # poker high-card value; blackjack handles aces separately

BLACKJACK_VALUE = {r: 10 for r in ['10', 'J', 'Q', 'K']}
BLACKJACK_VALUE.update({str(n): n for n in range(2, 10)})
BLACKJACK_VALUE['A'] = 11  # soft value; hand totals adjust for busts


class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit

    @property
    def is_red(self):
        return self.suit in RED_SUITS

    @property
    def rank_value(self):
        return RANK_VALUE[self.rank]

    @property
    def blackjack_value(self):
        return BLACKJACK_VALUE[self.rank]

    def __str__(self):
        return f"{self.rank}{self.suit}"

    def __repr__(self):
        return f"Card({self.rank!r}, {self.suit!r})"

    def __eq__(self, other):
        return isinstance(other, Card) and self.rank == other.rank and self.suit == other.suit


class Shoe:
    """A shuffled multi-deck shoe that reshuffles itself once depleted past a threshold."""

    def __init__(self, num_decks=6, reshuffle_threshold=0.25):
        self.num_decks = num_decks
        self.reshuffle_threshold = reshuffle_threshold
        self.cards = []
        self._build_and_shuffle()

    def _build_and_shuffle(self):
        self.cards = [Card(r, s) for _ in range(self.num_decks) for s in SUITS for r in RANKS]
        random.shuffle(self.cards)

    @property
    def total_cards(self):
        return self.num_decks * 52

    def needs_reshuffle(self):
        return len(self.cards) / self.total_cards < self.reshuffle_threshold

    def deal(self, n=1):
        if self.needs_reshuffle():
            self._build_and_shuffle()
        dealt = self.cards[:n]
        self.cards = self.cards[n:]
        return dealt[0] if n == 1 else dealt


def new_deck():
    """A single unshuffled-then-shuffled 52-card deck, for poker."""
    deck = [Card(r, s) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck
