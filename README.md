# Cmd Prompt Casino

A command-line casino written in Python: Blackjack, Texas Hold'em poker
against 3 bots, Roulette, and a Slot Machine, all wagering a single
persistent point balance. You start with 50 points — the goal is to build
that up as high as you can.

## Setup

```
pip install -r requirements.txt
python main.py
```

Requires Python 3.9+ and [colorama](https://pypi.org/project/colorama/) for
colored terminal output.

## How it works

- You start with **50 points**. Every game wagers points from the same
  balance, shown at the top of every screen alongside your **all-time high
  score**.
- Progress is saved automatically to `save_data.json` after every hand,
  spin, or round — close the casino anytime and pick up where you left off.
- If your balance hits 0, the game records your high score and offers to
  reset you to 50 points so you can keep playing.
- A **Stats** screen (from the lobby) tracks hands/spins played, total
  wagered, total won, and biggest win for each game.

## Games

### Blackjack
6-deck shoe, dealer stands on all 17s (including soft 17), blackjack pays
3:2, double down on any first two cards, split up to 3 times (4 hands),
insurance when the dealer shows an Ace, and a **5-Card Charlie** rule — draw
5 cards without busting and you win automatically.

### Poker — Texas Hold'em
You + 3 bots (Tex the Tight-Aggressive, Lucy the Loose-Aggressive, and Cal
the Calling Station) at one table. Buy in with points to get a chip stack;
standard blinds, hole cards, community cards, betting rounds, and side pots
for short all-ins. Cash out between hands to convert your remaining chips
back to points.

### Roulette
Standard American wheel (0, 00, 1-36). Bet red, black, even, odd, a dozen
(1-12 / 13-24 / 25-36), or straight-up on any single number — including 0
and 00 individually. Standard payouts (straight-up 35:1, dozens 2:1,
red/black/even/odd 1:1). Place multiple bets before each spin.

### Slot Machine
Classic 3-reel, single payline. Only exact 3-of-a-kind pays, topped off by
a 100x jackpot on triple 7s.

| Symbols (3x) | Payout |
|---|---|
| Cherry | 2x |
| Lemon | 3x |
| Orange | 5x |
| Bell | 10x |
| Bar | 20x |
| 7️⃣ | **100x (Jackpot)** |

## Project layout

```
main.py              # entry point: title screen, lobby, save/load
bankroll.py           # balance, high score, persistence
stats.py               # per-game play statistics
ui.py                   # colored terminal UI helpers, ASCII card art
cards.py                # Card/Shoe/Deck shared by blackjack & poker
games/
  blackjack.py
  poker.py
  roulette.py
  slots.py
```

Design notes live in `docs/superpowers/specs/`.
