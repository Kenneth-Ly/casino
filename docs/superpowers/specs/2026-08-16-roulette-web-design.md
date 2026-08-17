# Roulette Web UI — Design Spec

Date: 2026-08-16

## Overview

Third of four Phase 2 sub-projects (after the Neon Casino theme and Blackjack, before Poker). Ports the CLI's Roulette (`games/roulette.py`) to the web app, built on the same Flask/HTMX/session pattern established by Slots and Blackjack, styled with the Neon Casino theme.

`games/roulette.py`'s pure logic (`BET_MENU`, `pocket_color`, `evaluate_bet`, `describe_bet`, `POCKETS`) is reused unmodified. The CLI itself (`main.py`, `ui.py`, terminal `play()`/`play_round()`/`collect_bets()`) is untouched — same additive-only boundary as every prior web sub-project.

## Betting model: multi-bet slip

The CLI's `collect_bets()` lets a player stack several bets (e.g. Red *and* a straight-up number) before spinning. The web version keeps that: a session-held "slip" of pending bets is built up across several `POST /roulette/bet` requests, then resolved all at once by `POST /roulette/spin`. This is a deliberate step up from Slots' fully stateless one-shot pattern, closer to Blackjack's phased session state.

## Session state

`session['balance']` remains the single value shared across every game. New key `session['roulette']`, present only while a slip is being built or has just been resolved:

```python
{
  "phase": "betting" | "resolved",
  "bets": [
    {"type": "red" | "black" | "even" | "odd" | "dozen1" | "dozen2" | "dozen3" | "straight",
     "value": str | None,     # pocket string, e.g. "17" or "00" -- only for "straight"
     "amount": int,
     "label": str,            # menu label, for display
     "win": int}              # only present once phase == "resolved"
  ],
  "pocket": str | None,       # e.g. "17", "00" -- only once resolved
  "color": "red" | "black" | "green" | None,
}
```

Absent key (or `None`) means a fresh, empty slip should be shown. `web/roulette_web.py` owns building/consuming this dict; `web/app.py` routes stay thin, matching `blackjack_web.py`'s division of responsibility.

## Routes

One HTMX POST per slip edit or spin, each re-rendering `_roulette_table.html` into the same `#game-panel` target Slots and Blackjack use:

- **`GET /roulette`** — renders the table with the current slip (empty if none in progress, or a lingering resolved slip if the page was refreshed).
- **`POST /roulette/bet`** (`bet_type`, `number`, `amount`) — validates `bet_type` is a known key from `BET_MENU`; if `bet_type == "straight"`, validates `number` is `"00"` or an integer string `0`-`36`; validates `amount` against the *remaining* balance (`balance` minus the sum already committed in the slip) via the existing `web/validation.py:validate_bet`. On success, appends the bet to `state["bets"]`. Only valid while `phase == "betting"` (or no slip yet); a mismatched request re-renders current state.
- **`POST /roulette/remove`** (`index`) — drops one line item from the pending slip by its position. Silently no-ops on an out-of-range index (stale re-submit) rather than raising.
- **`POST /roulette/spin`** — requires a non-empty slip; a mismatched or empty request re-renders current state without spinning. Withdraws the total wager from `session['balance']`, draws one random pocket from `POCKETS`, evaluates every bet with `evaluate_bet`, sums the returns, credits `session['balance']`, updates the global high-balance record exactly like Slots/Blackjack do (best-effort, DB failure doesn't break the response), sets `phase="resolved"` with `pocket`/`color` and a per-bet `"win"` amount attached for display.
- **`POST /roulette/next`** — clears `session['roulette']` back to a fresh empty slip.

## Template

- **Add-a-bet form**: a `<select>` populated from `BET_MENU` labels, a text input for the straight-up pocket number (always rendered, consulted server-side only when "Straight-up number" is selected — matching the no-client-JS, server-validated convention already used throughout the app), and an amount field. Submits to `/roulette/bet`.
- **Pending slip**: each line shows `describe_bet(bet)` plus a small "Remove" button (a form posting `index` to `/roulette/remove`).
- **Spin button**: only rendered when the slip is non-empty; posts to `/roulette/spin`.
- **Resolved view**: shows the landed pocket and its color, then each bet's line re-rendered with a win/lose readout (`+N pts` or `-amount pts`), then a "New Round" button posting to `/roulette/next`.
- Card-free — no card-face styling needed here, just the pocket/color readout and bet-slip list, styled with the existing neon panel/button/table conventions from `style.css`.

## Error handling

- Invalid bet-add (bad type, bad straight number, bad amount): re-render the current slip with an inline error, no state mutation — identical in shape to Slots' bet validation.
- Phase mismatch or an out-of-range remove index (stale HTMX request, double-click, browser back): re-render whatever the actual current state is, never raise.
- Spin with an empty slip: no-op re-render, never raise.
- Global record DB update: same best-effort pattern as Slots/Blackjack — wrapped, failure logs only the exception type, never breaks the response.

## Testing

- **`tests/test_roulette_web.py`**: unit tests for `roulette_web.py`'s slip-building and resolution helpers — adding valid/invalid bets, removing by index (including out-of-range), spinning with a monkeypatched pocket draw to cover a win, a loss, a push-free full house of bet types (red win + straight-up loss in the same spin), and the 0/00 case where every outside bet loses.
- **`tests/test_app_roulette.py`**: Flask test-client coverage for the full route surface — building a multi-bet slip across several `/roulette/bet` calls, removing a line, spinning into a win and a loss, spinning with an empty slip (no-op), and a DB-unreachable record-update test matching the existing Slots/Blackjack pattern.
