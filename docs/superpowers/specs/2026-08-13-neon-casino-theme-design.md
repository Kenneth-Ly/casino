# Neon Casino Visual Redesign — Design Spec

Date: 2026-08-13

## Overview

Restyle the deployed web app (currently "Cmd Prompt Casino," lobby + Slot
Machine only) with a "Vegas Strip at night" neon theme, and rename its web
display name to **Neon Casino**. This is a pure visual/branding change —
no new routes, no new game logic, no database changes. It's the first of
four sub-projects that make up Phase 2 (the other three — Blackjack,
Roulette, Poker web UIs — each get their own later spec, built on top of
this theme once it's live).

**Scope boundary:** this only touches the *web* layer
(`web/templates/`, `web/static/style.css`). The CLI (`main.py`, `ui.py`,
`README.md`, the terminal title screen) keeps saying "Cmd Prompt Casino"
and is not touched — same additive-only boundary Phase 1 established.

## Visual direction: Vegas Strip Marquee

Approved via visual mockups (browser-based brainstorming companion).

**Palette** (named tokens, hex):

| Token | Hex | Role |
|---|---|---|
| `--ink` | `#0B0817` | Page background — deep indigo-black night sky |
| `--panel` | `#170F2E` | Card/panel surface (paytable, bet form, tiles) |
| `--marquee` | `#FF4D1C` | Neon red-orange — logo glow, headings, bust/error state |
| `--accent` | `#33E9FF` | Cyan — panel borders, secondary dividers |
| `--gold` | `#FFC13B` | Balance, winnings, jackpot — carried over from the CLI's gold identity |
| `--win` | `#39FF6A` | Win messages |
| `--button` | `#2E7CFF` | Electric blue — buttons only (not used for text/logo) |

**Typography:**
- Display (`Monoton`, Google Fonts): the "NEON CASINO" marquee logo only,
  rendered with a multi-layer `text-shadow` glow (`--marquee` color).
  Used sparingly — logo/wordmark only, never body text or long strings
  (Monoton is unreadable at paragraph scale by design).
- Body/UI (`JetBrains Mono`, Google Fonts): everything else — labels,
  balance figures, paytable, buttons, messages. Keeps the "Cmd Prompt"
  terminal DNA even though the CMD PROMPT name itself is dropped.
- Both loaded via Google Fonts CDN `<link>`/`@import` in `base.html`,
  same pattern as the existing HTMX CDN `<script>` tag from Phase 1.

**Signature element:** the neon-tube marquee wordmark ("NEON CASINO" in
Monoton with a red-orange glow) is the one loud, memorable element.
Everything else — panels, borders, buttons — stays visually quieter so
the marquee reads as the room's centerpiece, not one glowing thing among
many.

## Lobby layout

2-column grid of "cabinet" tiles (1 column on narrow viewports, ~480px
breakpoint, matching the existing responsive pattern from Phase 1's CSS).

- **Live tile (Slots):** solid `--panel` background, solid `--gold`
  border with a soft glow (`box-shadow`), clickable, gold text.
- **Coming-soon tiles (Blackjack, Roulette, Poker):** dashed `--accent`
  border at low opacity, `--panel`-derived darker background, muted
  text color, "Coming soon" label, not clickable (no `<a href>`, or a
  disabled-looking `<div>` — implementer's call, whichever is simpler
  given no JS framework is in play).
- Global record ("ALL-TIME RECORD: N PTS") stays above the grid, styled
  in gold, same content as today — only the styling changes.

## Slots page

Same structural layout as Phase 1 (balance, paytable, reels/message,
bet form, busted/reset state) — this spec changes *only* the visual
treatment, not the markup structure or the Flask routes/logic:
- Panel background/border restyled with `--panel` / `--accent`.
- Balance figure in `--gold` with a soft glow.
- Win messages in `--win`; the busted/"out of points" message and the
  spin's "no match" message in `--marquee` (repurposing the marquee
  red-orange as the app's general alert/negative-state color, alongside
  its logo role).
- Buttons (Spin, Reset) restyled to `--button` (electric blue) with a
  glow, replacing the current plain gold button styling.
- Jackpot row in the paytable keeps its distinct treatment (currently
  gold/bold) — restyle colors to match the new palette but keep the
  "this row is special" visual distinction.

## Accessibility & responsiveness

- Keep the existing ~480px single-column breakpoint; extend it to the
  new lobby grid.
- Visible keyboard focus state on all interactive elements (buttons,
  the live lobby tile) — a clear outline or glow on `:focus-visible`,
  not removed via `outline: none` without a replacement.
- Respect `prefers-reduced-motion`: if any glow/flicker animation is
  added (e.g. a one-time "power on" flicker on the marquee), gate it
  behind `@media (prefers-reduced-motion: no-preference)` so it's
  skipped entirely for users who've opted out. Static glow (box-shadow/
  text-shadow, no animation) needs no such gate.

## Testing

No new automated tests — this is a template/CSS-only change with no new
logic. The existing 18-test suite (`pytest -v`) must still pass
unchanged (none of the current tests assert on specific copy like "Cmd
Prompt Casino" or on color values — they check numbers and error
strings, which this spec doesn't touch). Verification is manual/visual:
run the Flask dev server, check the lobby and Slots page render
correctly at desktop and narrow-mobile widths, confirm the coming-soon
tiles are visually distinct from the live tile, confirm keyboard focus
is visible on buttons and the Slots tile.
