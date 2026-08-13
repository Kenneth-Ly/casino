# Web Deployment, Phase 1 (Slots) — Design Spec

Date: 2026-08-13

## Overview

Deploy Cmd Prompt Casino as a live web app for a course rubric requiring: a
public HTTPS URL that loads, hosted on a real platform (not a default host
page), the app itself (not someone else's template), and a connected
database.

The CLI (`main.py`, `games/*.py`, `ui.py`) is terminal-only and stays exactly
as it is — this is a new, separate web frontend built alongside it, reusing
the pure game-logic functions where possible.

This spec covers **Phase 1 only**: standing up the full pipeline (web app +
session-based play + database + hosting) for a single game, **Slot
Machine**, chosen because its logic (`games/slots.py`) has no dealer AI or
multi-street betting and is already pure functions with no terminal I/O
mixed in. Phase 2 (a separate spec) ports Blackjack, Roulette, and Poker
onto this same pipeline once it's proven live.

## Scope decisions

- **No user accounts / login.** Each browser gets its own play session via a
  signed cookie (Flask `session`), matching the CLI's single-player feel.
  Balance resets to 50 if cookies are cleared or a different browser is
  used — acceptable, since nothing valuable is tied to an account.
- **Database holds exactly one thing:** the highest point balance ever
  reached by any visitor, as a single global record (not per-visitor). This
  is what satisfies the "connected database" rubric item without inventing
  accounts that weren't asked for.
- **One Supabase Postgres instance**, used for both local dev and
  production via a `DATABASE_URL` env var — no separate local DB setup.

## Architecture

```
Browser --HTMX--> Flask routes --> games/slots.py (pure logic, reused as-is)
                       |
                       +-- Flask session (per-browser balance/stats, cookie-based)
                       +-- Postgres (Supabase): single "global_record" row
```

- **Hosting:** Render (free web service tier), running the Flask app via
  gunicorn.
- **Database:** Supabase Postgres (free tier), connected via `DATABASE_URL`.
- **Frontend interactivity:** HTMX (via CDN `<script>` tag) so Spin updates
  just the game panel instead of a full page reload, without writing custom
  JavaScript or adding a JS build step.

## Components

```
web/
  app.py                 # Flask app + routes
  db.py                  # Supabase/Postgres wrapper
  templates/
    base.html
    lobby.html            # shows global record, links to games
    slots.html             # full page wrapper for the Slots game
    _slots_panel.html       # HTMX-swapped partial: paytable, reels, bet form, balance
  static/
    style.css
```

- `web/app.py` is new and separate from `main.py` — the CLI entry point is
  untouched.
- `web/db.py` exposes `get_global_record()` and
  `update_global_record(balance)` (upsert-if-higher, single row table).
- `games/slots.py` is reused unmodified: `spin_reels()`, `evaluate_spin()`,
  `payout_for()`, `SYMBOLS`, `JACKPOT_SYMBOL` are already pure functions.
  The web route calls these directly; it does not call `play_round()` /
  `play()`, which are CLI-loop-and-`print()`-specific and stay CLI-only.
- Session shape (`flask.session`): `balance` (int, default 50),
  `stats['slots']` (`plays`, `wagered`, `won`, `jackpots` — same shape as
  today's `stats.py`).

## Data flow

**Lobby (`GET /`):** reads the global record from `db.get_global_record()`
and renders it alongside a "Play Slots" link.

**Spin (`POST /slots/spin`, HTMX):**
1. Read bet from the submitted form.
2. Validate against `session['balance']` (whole number, `1 <= bet <=
   balance`); on failure, re-render the panel with an inline error (no
   session mutation).
3. Deduct the bet, call `slots.spin_reels()` and `slots.evaluate_spin()`,
   credit any winnings.
4. Update `session['stats']['slots']`.
5. If the new balance beats the DB's global record, call
   `db.update_global_record(balance)`.
6. Render `_slots_panel.html` with the updated reels/balance/message; HTMX
   swaps it into the page in place.

**Busted (`balance <= 0`):** panel shows a "you're out of points" state with
a reset button (`POST /slots/reset`) that sets `session['balance']` back to
50 — mirrors `Bankroll.reset_after_bust()` in the CLI.

## Error handling

- Invalid bet input re-renders the form with an inline error string instead
  of raising — same validation rule as `ui.prompt_bet`, adapted from a
  blocking `input()` loop to a single request/response.
- Session balance lives in a signed cookie, so client-side tampering is
  rejected by Flask's signature check. Not a real security boundary, but
  sufficient — there's no real money involved.
- If the database is unreachable when reading or writing the global record,
  the app degrades gracefully: the lobby shows "record unavailable" instead
  of a 500, and a spin still completes normally (the record update is
  skipped for that request, not retried).
- A missing `DATABASE_URL` at startup is a hard failure with a clear error
  message — it's required configuration, not optional.

## Testing

- `pytest` (added to `requirements.txt`) covers:
  - `db.py`'s upsert-if-higher logic.
  - Bet-validation helper (invalid/negative/over-balance inputs).
- `games/slots.py`'s existing pure functions are unchanged and need no new
  tests.
- Manual verification: run the Flask dev server locally end-to-end (spin,
  win, bust-and-reset, global record updates on a new high), then
  smoke-test the same flow on the deployed Render URL.

## Deployment sequence

1. Create Supabase project, create the single-row `global_record` table,
   get `DATABASE_URL`.
2. Build `web/` locally against that same Supabase instance, verify end to
   end with the Flask dev server.
3. Create Render web service from this repo, set `DATABASE_URL` (and
   `SECRET_KEY` for session signing) as env vars, deploy.
4. Smoke-test the live URL: lobby loads, spin works, global record persists
   across requests and beats itself correctly.

## Out of scope (Phase 2+)

- Blackjack, Roulette, and Poker web UIs — separate spec, built on this same
  pipeline once Phase 1 is live.
- Per-game stats display on the web lobby (Phase 1 only tracks Slots
  stats in-session; the CLI's full Stats screen isn't ported yet).
