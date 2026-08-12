# Cmd Prompt Casino — Design Spec

Date: 2026-08-12

## Overview

A Python command-line casino with four games — Blackjack, Texas Hold'em Poker
(vs. 3 bots), Roulette, and a Slot Machine — all wagering a single persistent
point balance. Player starts at 50 points; goal is to maximize points over
time. Balance and stats persist across runs via a local JSON save file.

## Architecture

```
casino/
  main.py              # entry point: title screen, lobby menu, load/save
  bankroll.py           # Bankroll class: balance, high_score, buy/pay, save/load JSON
  stats.py               # per-game stats tracking (hands/spins played, wagered, won, biggest win)
  save_data.json         # persisted state, created on first run
  ui.py                   # colorama helpers: colored text, boxed menus, ASCII card art, title screen, animation pauses
  cards.py                # Card, Deck (multi-deck shoe) — shared by blackjack & poker
  games/
    blackjack.py
    poker.py
    roulette.py
    slots.py
```

**Flow:** `main.py` loads save data into a `Bankroll` object, shows an ASCII
art title screen ("Press Enter to enter the casino"), then a lobby menu
(Blackjack / Poker / Roulette / Slots / Stats / Quit). Each game module
exposes a `play(bankroll, stats)` loop; control returns to the lobby when the
player leaves a game. Save-to-disk happens after every resolved
bet/hand/spin, not just on exit, so progress isn't lost on a crash.

**Going broke:** `Bankroll.high_score` is updated continuously to track the
maximum balance ever reached (not just at bust time). When `balance` hits 0,
the player is told they're broke, shown their high score, and prompted to
reset balance to 50 to keep playing. Stats and high score persist through
resets.

**Persistence format (`save_data.json`):**
```json
{
  "balance": 50,
  "high_score": 50,
  "stats": {
    "blackjack": {"hands": 0, "wagered": 0, "won": 0, "biggest_win": 0},
    "poker":     {"hands": 0, "wagered": 0, "won": 0, "biggest_win": 0},
    "roulette":  {"spins": 0, "wagered": 0, "won": 0, "biggest_win": 0},
    "slots":     {"spins": 0, "wagered": 0, "won": 0, "biggest_win": 0, "jackpots": 0}
  }
}
```

## Blackjack

- 6-deck shoe, reshuffled when ~75% depleted.
- Bet prompted before each deal (min 1, max = current balance).
- Player gets 2 cards up; dealer gets 1 up + 1 down (hole card).
- Natural blackjack (player's first 2 cards = 21) resolves immediately at
  3:2, after peeking dealer's hole card if dealer shows a possible blackjack.
- Insurance offered when dealer shows an Ace (half original bet, pays 2:1 if
  dealer has blackjack).
- Player actions: Hit / Stand / Double Down (any first two cards) / Split on
  pairs, up to 3 times (4 hands total); re-splitting aces allowed, but split
  aces receive exactly one card each and cannot act further.
- **5-Card Charlie ("shoot for the moon"):** if the player draws a 5th card
  on a hand without busting, that hand automatically wins (1:1, or 2x if it
  was doubled), regardless of dealer's hand. Checked immediately after each
  hit, before dealer plays.
- Dealer reveals hole card and hits until 17+, standing on all 17s
  (including soft 17).
- Resolution: each active player hand compared to dealer; 1:1 payout
  (3:2 for natural blackjack), push returns the bet, bust forfeits the bet.

## Poker (Texas Hold'em vs. 3 bots)

- **Buy-in model:** entering the poker room prompts a buy-in amount deducted
  from the player's point balance, becoming their chip stack at the table.
  Each of the 3 bots buys in with its own house-funded stack (not tied to
  the player's economy), refreshed every session.
- **Table:** player + 3 bots, rotating dealer button, small/big blind posted
  each hand, 2 hole cards per player, community cards dealt across
  flop/turn/river, betting rounds with fold/check/call/raise/all-in, side
  pots supported for short all-ins.
- **Showdown:** standard poker hand ranking, best 5 of 7 cards
  (high card → royal flush).
- **Bots:** each has a fixed personality (Tight-Aggressive, Loose-Aggressive,
  Calling Station) driving a heuristic decision function — pre-flop hand
  quality estimate (pairs, suited connectors, high cards), post-flop
  made-hand/draw strength estimate, rough pot-odds comparison, and a small
  randomized bluff frequency — to choose fold/check/call/raise/all-in.
- **Cashing out:** player may leave the table between hands (or is
  auto-cashed-out on busting to 0 chips); remaining chip stack converts back
  to point balance 1:1.
- Stats tracked: hands played, total wagered/won, biggest pot won.

## Roulette

- American wheel: 38 pockets — 0 and 00 (green), 1-36 (red/black per
  standard layout).
- Bet types: Red, Black, Even, Odd, Dozens (1-12 / 13-24 / 25-36), and
  straight-up on any single number including 0 and 00 individually (no
  combined "green" bet — standard table rules only).
- Multiple bets may be placed per spin.
- Payouts: straight-up 35:1, dozens 2:1, red/black/even/odd 1:1.
- Spin has a brief animated "spinning" delay before the result is revealed.
- Stats tracked: spins played, wagered, won, biggest win.

## Slot Machine

- 3 reels, 1 payline, brief spin animation (cycling symbols before landing).
- Symbols, low to high value: Cherry, Lemon, Orange, Bell, Bar, 7️⃣ (jackpot).
- Only 3-of-a-kind pays (no partial-match payouts):
  - 3× Cherry → 2x bet
  - 3× Lemon → 3x bet
  - 3× Orange → 5x bet
  - 3× Bell → 10x bet
  - 3× Bar → 20x bet
  - 3× 7️⃣ → **Jackpot**, fixed 100x bet (not a progressive/shared pool)
- Stats tracked: spins played, wagered, won, biggest win, jackpots hit.

## UI

- **Title screen:** ASCII art "CASINO" banner, colored (gold/red), suit
  flourish (♠♥♦♣), "Press Enter to enter the casino" prompt.
- **Colors (via colorama):** red suits in red, black suits in default/white,
  wins in green, losses in red, balance in yellow/gold, menu borders in
  cyan.
- **Card art:** simple boxed ASCII cards, e.g.:
  ```
  ┌─────┐
  │ A ♠ │
  │     │
  └─────┘
  ```
- **Menus:** numbered lists in boxed borders; every screen shows a
  consistent "Balance: X | High Score: Y" header.
- **Stats screen:** accessible from the lobby, shows per-game stats plus
  overall balance/high score.

## Out of scope (YAGNI)

- No multiplayer/networking.
- No side games beyond the 4 listed.
- No real-money integration of any kind — points only.
- No progressive/shared jackpot pool across games (slots jackpot is a fixed
  multiplier).
