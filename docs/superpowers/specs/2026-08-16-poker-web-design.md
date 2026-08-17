# Poker Web UI — Design Spec

Date: 2026-08-16

## Overview

Fourth and final Phase 2 sub-project (after the Neon Casino theme, Blackjack, and Roulette). Ports the CLI's Texas Hold'em (`games/poker.py`) to the web app — a player seated with 3 bot opponents (Tex/TAG, Lucy/LAG, Cal/Station), blinds, four betting streets, side pots, and standard showdown — built on the same Flask/HTMX/session pattern the other three sub-projects established, styled with the Neon Casino theme and reusing Blackjack's card-face CSS.

`games/poker.py`'s genuinely pure logic — hand evaluation (`evaluate_5`, `best_hand`, `HAND_NAMES`), bot decision-making (`bot_decide_action`, `estimate_strength`, `preflop_strength`, `PERSONALITIES`), betting mechanics (`apply_action`), and pot-slicing (`build_pots`) — is reused **unmodified**. `cards.new_deck()` is reused unmodified for shuffling. The CLI itself (`main.py`, `ui.py`, and the terminal-only `play()`/`play_hand()`/`betting_round()`/`human_decide_action()`/`show_state()`) is untouched — same additive-only boundary as every prior web sub-project.

Two CLI functions are deliberately **not** reused as-is: `award_pot_all_folded()` and `showdown()` both `print()` (terminal narration) and call `stats.record()` (CLI-only session stats), mixing display/tracking concerns into what's otherwise pot-distribution math — unlike `games.blackjack.resolve_round`, which is genuinely side-effect-free and was reused unmodified by the Blackjack sub-project. Web pot-resolution reimplements just the math from these two functions (assigning `build_pots()`'s pot shares to winners picked by `best_hand()`'s score, same remainder-to-first-winner tie-breaking), with no printing and no stats calls — matching the precedent Blackjack already set (`_NoOpStats`: web stats aren't tracked yet). Everything else — `play_hand`, `betting_round`, the input-reading decision functions, and now this pot-resolution orchestration — has no web equivalent to reuse and is re-implemented for the web as described below, calling only the pure primitives.

## Why poker needs a genuinely different architecture than Blackjack or Roulette

Blackjack pauses for exactly one actor (the player) at a time. Roulette has no pauses mid-round at all. Poker's CLI, between two of the human's decisions, may need several *bot* decisions first — and bots don't need a real HTTP round-trip, only the human does. So the web version is built around one resumable function, `advance()`, that does everything CLI's `play_hand()`/`betting_round()` do — deal, drain the betting-round queue calling bot logic synchronously, deal the next street, repeat — except it **returns and persists state the moment it's the human's turn**, instead of blocking on `input()`. Every route is a thin wrapper that calls `advance()` once.

An alternative — making each bot's turn its own request (a "Next →" button per bot) — was considered and rejected: it adds clicks for no benefit once there's an action log (see below), and needs the identical persisted state underneath anyway.

## Session state

`session['balance']` remains the single value shared across every game. New key `session['poker']`, present only while a table is active, split into **table** state (persists across hands at the table) and **hand** state (rebuilt each deal):

```python
{
  "table": {
    "players": [
      {"name": "You", "stack": 44, "is_bot": False, "personality": None},
      {"name": "Tex", "stack": 40, "is_bot": True, "personality": "TAG"},
      {"name": "Lucy", "stack": 38, "is_bot": True, "personality": "LAG"},
      {"name": "Cal", "stack": 50, "is_bot": True, "personality": "Station"},
    ],
    "button_idx": 0,
    "buy_in": 50,
  },
  "hand": {
    "phase": "player_turn" | "resolved",
    "street": "preflop" | "flop" | "turn" | "river",
    "deck": [["A", "S"], ["K", "D"], ...],   # remaining cards, popped from the end as dealt (same order cards.py's deck.pop() uses)
    "board": [["9", "H"], ...],              # 0-5 cards
    "players": [                              # index-aligned with table.players
      {"hole": [["A", "H"], ["K", "S"]], "current_bet": 0, "total_committed": 0,
       "folded": False, "all_in": False, "showdown_score": None},
      ...
    ],
    "order": [1, 2, 3, 0],        # fixed action order for the current street (built once, used to rebuild to_act on a raise)
    "current_max_bet": 2,
    "to_act": [2, 3, 0],          # queue of player indices still owed a decision this street
    "log": ["Tex calls.", "Lucy raises to 6.", "Cal folds."],  # play-by-play since the human's last turn
  }
}
```

`table.players[i]` and `hand.players[i]` share an index with each other and with `games.poker.Player` instances reconstructed from them — never reordered mid-hand. `human_idx` is always `0`, matching the CLI's convention (`Player("You", ...)` is always seated first).

## The `advance()` algorithm

`web/poker_web.py`'s `advance(state, action=None, amount=None)` is the one substantial new function. It:

1. Reconstructs real `games.poker.Player` objects from `table.players` + `hand.players` (stack, hole cards, folded/all-in flags, current_bet, total_committed) — the same JSON-to-object bridging pattern `blackjack_web.py` already uses for `Hand`.
2. If `action` is given (a human decision arrived via POST), applies it to `players[0]` via the **unmodified** `apply_action()`, updating `current_max_bet` and, if the action raised, resetting `to_act` to everyone else still active drawn from the stored `order` — exactly mirroring `betting_round()`'s `if raised: to_act = [j for j in active if j != i and ...]`.
3. Loops: while `to_act` is non-empty, look at `to_act[0]`.
   - If that player has since folded or gone all-in (a stale queue entry), pop and skip it — mirrors `betting_round()`'s defensive `if p.folded or p.all_in: continue`.
   - If it's a bot, pop it, call the **unmodified** `bot_decide_action()` then `apply_action()`, append a log line (`"{name} folds."` / `"checks."` / `"calls."` / `"raises to {amount}."` / `"goes all-in ({amount} pts)!"` — same phrasing `betting_round()` already prints), and if the action raised, reset `to_act` as in step 2.
   - If it's the human (`index 0`), stop looping — this is the pause point.
4. When `to_act` empties (everyone this street has acted and matched or folded/gone all-in): if only one player remains unfolded, award them the full pot (`sum(p.total_committed for p in players)`, same as `award_pot_all_folded()`'s math, minus the printing/stats) and set `phase = "resolved"`. Otherwise deal the next street from `deck` (burn + flop/turn/river, matching `play_hand()`'s exact card counts), reset every active player's `current_bet` to 0 (not `total_committed`), rebuild `order`/`to_act` from the postflop order (`(sb_idx + i) % n`, filtered to non-folded/non-all-in), and loop back to step 3. If the street just dealt was the river, instead resolve the pot at showdown: call the **unmodified** `best_hand()` for every remaining contender to get a comparable score, call the **unmodified** `build_pots()` to slice the total committed amounts into main/side pots with their eligible players, then for each pot award its share to the highest-scoring eligible player(s) (splitting evenly among ties, remainder to the first — same math `showdown()` already does), and set `phase = "resolved"`.
5. Serializes the (possibly mutated) `Player` objects and remaining deck back into `state["hand"]`, sets `state["hand"]["log"]` to everything logged during this call, and returns `state`. The loop's only exit conditions are: it's the human's turn (`to_act[0] == 0`, phase stays `"player_turn"`), or the hand is `"resolved"`.

`table.players[i]["stack"]` is written back whenever a pot is awarded (mirrors `w.stack += amt` in the CLI's `showdown`/`award_pot_all_folded`, minus the printing/stats), so it's always current after any `advance()` call.

## Routes

- **`GET /poker`** — buy-in form if `session['poker']` is absent; otherwise the current table/hand view (e.g. a page refresh mid-hand).
- **`POST /poker/buyin`** (`buy_in`) — validates the buy-in against balance (reuses `web/validation.py`'s `validate_bet`, `min_bet = BIG_BLIND * 2` matching the CLI), deducts it from `session['balance']`, builds `table.players` (You + Tex/TAG + Lucy/LAG + Cal/Station, all starting with `buy_in` chips), `button_idx = 0`, then deals the first hand and calls `advance()` with no action to run any bots acting before the human's first turn (or resolve instantly if, e.g., everyone but the human folds to a preflop bot raise — rare but possible).
- **`POST /poker/action`** (`action=fold|check|call|raise|allin`, `amount` for raise) — only valid when `phase == "player_turn"` and `to_act[0] == 0` (a mismatched/stale request re-renders current state, never raises). For `raise`, re-validates the target amount server-side against the same bounds the CLI computes (`min_target = current_bet + to_call + BIG_BLIND`, clamped down to `max_target = current_bet + stack` if that's lower) — the UI only ever offers a raise button when raising is legal, but the route never trusts that alone. Calls `advance(state, action, amount)`.
- **`POST /poker/next-hand`** — only valid when `hand.phase == "resolved"`. Any bot at `stack <= 0` gets a **house rebuy** back to `buy_in` (matching the CLI's `if p.is_bot and p.stack <= 0: p.stack = buy_in`) — the human does not get this, matching the CLI. Advances `button_idx`, deals a new hand, calls `advance()` with no action.
- **`POST /poker/cashout`** — only valid when `hand.phase == "resolved"` (matching the CLI's "you can only leave between hands"). Credits `table.players[0]["stack"]` to `session['balance']`, updates the global high-balance record if the payout was nonzero (best-effort, same pattern as the other three games), clears `session['poker']`.

## Card drawing

Unlike Blackjack's independent random draws (safe there because duplicate cards across independently-drawn hands don't matter), poker needs a real deck without replacement *within one hand* — no two players can hold the same card. `cards.new_deck()` (already used by the CLI, already returns a shuffled 52-card list) is reused unmodified at the start of every hand; the remaining cards are stored in `hand.deck` and popped from the end across `advance()` calls exactly like the CLI's `deck.pop()`. A full remaining deck is at most 52 small `[rank, suit]` pairs — comfortably inside a signed session cookie alongside the rest of the hand state.

## Template and card rendering

Reuses the existing `.card`/`.card.red`/`.card.black` CSS from the Blackjack sub-project unmodified for realistic card-face rendering. Unlike Blackjack, nothing here uses `.card.back`: the human's own hole cards are always shown face-up, and bot hole cards are simply omitted from the markup entirely while a hand is live, only appearing at showdown for whichever bots are still in the hand — matching the CLI's `showdown()`, which only ever prints contenders' hole cards once the hand is decided. New CSS is layout-only: a seat row per player (name, stack, current bet, folded/all-in tag), a board row, an action log block, and the action-buttons form (Fold / Check-or-Call / Raise-to text field / All-In, matching the CLI's `human_decide_action`'s exact option set for a given `to_call`).

The raise control is a free-form text field for the total raise-to amount (matching the CLI's `prompt_raise_amount`), not preset buttons — consistent with every other bet/amount input already in this app (Slots, Blackjack, Roulette).

## Error handling

- Invalid buy-in: `validate_bet` re-renders the buy-in form with an inline error, no state mutation — identical pattern to Slots/Blackjack/Roulette.
- Any action route hit when it isn't actually the human's turn, or the hand phase doesn't match (stale HTMX request, double-click, browser back, a forged POST): re-render whatever the actual current state is, never raise or mutate.
- Raise amount out of bounds: re-render the current (still-human's-turn) state with an inline error, no mutation — same shape as Roulette's bet-slip validation errors.
- Global record DB update on cash-out: same best-effort pattern as the other three games — wrapped, failure logs only the exception type, never breaks the response.

## Testing

- **`tests/test_poker_web.py`**: unit tests for `advance()` and its serialization helpers, using a monkeypatched `cards.new_deck()` to feed an exact, known deck order — a hand that resolves preflop by fold-out (uncontested-pot path), a hand that goes to showdown across all four streets with a clear winner, a bot raise reopening the action so a player who already acted this street must act again, and an all-in scenario producing a side pot resolved correctly by `build_pots()` plus the web module's own showdown-scoring math. Also cover the human's own actions applied via `advance(state, action, amount)`: fold, check, call, a legal raise, an out-of-range raise being rejected, and all-in.
- **`tests/test_app_poker.py`**: Flask test-client coverage for the full route surface — buy-in into a hand where the human acts first, buy-in into a hand where bots act before the human (asserting the log shows their actions), a fold, a full hand to showdown, next-hand (asserting bot house-rebuy when a bot is broke), and cash-out crediting the balance.
