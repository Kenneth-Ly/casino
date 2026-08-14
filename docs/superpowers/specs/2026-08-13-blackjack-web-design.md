# Blackjack Web UI — Design Spec

Date: 2026-08-13

## Overview

Second of four Phase 2 sub-projects (after the Neon Casino theme, before Roulette and Poker). Ports the CLI's Blackjack (`games/blackjack.py`) to the web app with full feature parity — splits (up to 3, 4 hands), double down, insurance, 5-Card Charlie — built on the same Flask/HTMX/session pattern Slots established, styled with the Neon Casino theme.

`games/blackjack.py`'s pure logic (`hand_value`, `Hand`, `dealer_should_hit`, `resolve_round`) is reused unmodified. The CLI itself (`main.py`, `ui.py`, terminal `play()`/`play_round()`) is untouched — same additive-only boundary as every prior web sub-project.

## Card drawing: independent random draws, not a persisted shoe

The CLI draws from a persistent 6-deck `cards.Shoe` that depletes and reshuffles at 25% remaining. The web version does not replicate this: Flask's session is a signed **cookie** (client-side, ~4KB), and storing a 312-card shoe's remaining order there every request is fragile and wasteful for no real gameplay benefit in a single-player, one-round-at-a-time session.

Instead, `web/blackjack_web.py` provides `draw_card()`, which returns `cards.Card(random.choice(cards.RANKS), random.choice(cards.SUITS))` — an independent uniform-random draw. Statistically indistinguishable from a large shoe for a single round. The session only ever needs to persist the handful of cards actually dealt in the current round (tiny, cookie-safe).

## Session state

`session['balance']` stays the single value shared across every game (Slots, Blackjack, and later Roulette/Poker), exactly matching the CLI's single shared `Bankroll`.

New key `session['blackjack']`, present only while a round is active:

```python
{
  "phase": "insurance_offer" | "player_turn" | "resolved",
  "dealer_cards": [[rank, suit], ...],
  "hands": [
    {"cards": [[rank, suit], ...], "bet": int, "doubled": bool,
     "from_split_aces": bool, "stood": bool, "busted": bool,
     "result": "blackjack" | "charlie" | None},
    ...
  ],
  "active_index": int,
  "insurance_bet": int,
  "split_count": int,
}
```

Cards are stored as `[rank, suit]` pairs (JSON-safe) and converted to/from `cards.Card` objects by `blackjack_web.py` wherever `games/blackjack.py`'s functions need real `Card`/`Hand` objects. Absent key (or `None`) means no round in progress.

## Routes

Mirrors the CLI's flow exactly, one HTMX POST per player decision, each re-rendering `_blackjack_table.html` into the same `#game-panel` target used by Slots:

- **`GET /blackjack`** — bet form if no round in progress; current table state if one is (e.g. a page refresh mid-round).
- **`POST /blackjack/deal`** — validates the bet (`web/validation.py`'s existing `validate_bet`), deducts it, deals 2 cards to the player and 2 to the dealer via `draw_card()`. If the dealer's up-card is not an Ace and neither side has natural blackjack, `phase="player_turn"`. If either side has blackjack, resolves immediately (`phase="resolved"`). If the dealer's up-card is an Ace and the player doesn't already have blackjack, `phase="insurance_offer"`.
- **`POST /blackjack/insurance`** (`decision=accept|decline`) — only valid in `insurance_offer` phase (server checks; a mismatched request re-renders the actual current state rather than raising). Deducts the insurance cost if accepted and affordable. Resolves immediately if the dealer had blackjack; otherwise moves to `player_turn` (or resolves immediately if the player has their own blackjack).
- **`POST /blackjack/action`** (`action=hit|stand|double|split`) — only valid in `player_turn` phase, applied to `hands[active_index]`. Re-validates double/split eligibility server-side (affordability, matching ranks for split, split cap of 3) even though the UI only shows eligible buttons — guards a forged request. Advances `active_index` when the active hand is done (busted, stood, doubled, 5-card Charlie, or split aces' forced single card). Once every hand is done: reveals the dealer, plays `dealer_should_hit` to completion, calls `resolve_round` (crediting/debiting `session['balance']`), updates the global high-score record exactly like Slots does (best-effort, DB failure doesn't break the response), sets `phase="resolved"`.
- **`POST /blackjack/next`** — clears `session['blackjack']`, back to the bet form.

## Card rendering

Realistic card faces, not flat colored text — approved via visual mockup. Each card: ~58×82px rounded rectangle, cream/white gradient background, rank+suit in mirrored top-left/bottom-right corners plus a large centered suit glyph, true playing-card red (`#B3122A`, not the theme's neon red-orange) for hearts/diamonds so the cards read as authentic against the dark neon table, black for spades/clubs. The dealer's hidden hole card renders as a face-down back (dark diagonal-striped pattern, cyan-glow border, a `?` glyph) until revealed. Suit letters from `cards.py` (`S/H/D/C` — an ASCII-only choice made for the CLI's Windows-console encoding safety, irrelevant in a browser) are mapped to real ♠♥♦♣ glyphs for display only, inside `blackjack_web.py` or the template — `games/blackjack.py`/`cards.py` themselves are untouched.

## Error handling

- Invalid bet: `validate_bet` re-renders the bet form with an inline error, no state mutation — identical to Slots.
- Phase mismatch (stale HTMX request from a double-click, browser back button, or a forged POST hitting the wrong route for the current `session['blackjack']` state): re-render whatever the actual current state is, never raise.
- Double/split eligibility is re-validated server-side on every `/blackjack/action` POST, not just trusted from what the UI displayed.
- Global record DB update: same best-effort pattern as Slots — wrapped, failure logs only the exception type (never the message/DSN), never breaks the response.

## Testing

- **`tests/test_blackjack_web.py`**: unit tests for card (de)serialization round-trip (`Card` <-> `[rank, suit]`) and any phase-transition helper logic in `blackjack_web.py`, using a monkeypatched `draw_card()` to feed exact, deterministic card sequences — never relying on real randomness for a specific scenario (a natural blackjack, a bust, a push, a 5-Card Charlie, a split creating a new hand, insurance paying out).
- **`tests/test_app.py`** additions (or a new `test_app_blackjack.py`): Flask test-client coverage for the full route surface — deal into player blackjack, deal into dealer blackjack, insurance accept path (dealer has blackjack), insurance decline path, a full hit/stand sequence to a win, a bust, a double-down, a split producing two hands both resolved, and a DB-unreachable lobby/record test matching Slots' existing pattern.
