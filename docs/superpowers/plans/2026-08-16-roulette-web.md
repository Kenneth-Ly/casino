# Roulette Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the CLI's Roulette to the web app with a multi-bet slip (stack several bets, then spin them all at once), reusing `games/roulette.py`'s pure logic unmodified.

**Architecture:** New `web/roulette_web.py` glue module owns building/consuming a JSON-safe session-held bet slip (`session['roulette']`). Bets accumulate across several `POST /roulette/bet` requests; `POST /roulette/spin` resolves the whole slip at once against one random pocket draw. `web/app.py` gets 5 new routes, each re-rendering one HTMX partial (`_roulette_table.html`), same request/response shape as Slots and Blackjack.

**Tech Stack:** Same as Phase 1/2 — Flask, HTMX, Jinja2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-16-roulette-web-design.md`

## Global Constraints

- `games/roulette.py` (`BET_MENU`, `pocket_color`, `evaluate_bet`, `POCKETS`) and the rest of the CLI are not modified — reused unmodified via import.
- `session['balance']` stays the single value shared across all games — Roulette reads/writes the same key, never a separate one.
- `session['roulette']` holds the bet slip. Unlike Blackjack's `None`-means-no-round convention, an absent/`None` `session['roulette']` means "show a fresh, empty slip" — every route normalizes this with `session.get("roulette") or roulette_web.fresh_state()`, so the template always receives a real state dict, never `None`.
- Bets accumulate in the slip across multiple `/roulette/bet` requests; nothing is wagered or resolved until `/roulette/spin`.
- The straight-up number field is always rendered in the add-bet form and is validated/consulted server-side only when `bet_type == "straight"` — no client-side JS toggle, matching the rest of the app.
- Bet-amount validation reuses the existing `web/validation.py:validate_bet`, checked against the *remaining* balance (balance minus everything already committed in the slip), not the raw account balance.
- Every route re-validates state server-side (bet type, straight-number range, phase, index bounds) rather than trusting what the UI displayed; malformed/stale requests re-render current state and never raise.
- The existing 48-test suite must keep passing throughout.

---

## Task 1: Bet slip — build and edit

**Files:**
- Create: `web/roulette_web.py`
- Test: `tests/test_roulette_web.py`

**Interfaces:**
- Produces: `fresh_state() -> dict`, `remaining_balance(state: dict, balance: int) -> int`, `add_bet(state: dict, bet_type: str, number: str, amount: int) -> (state: dict, error: str | None)`, `remove_bet(state: dict, index: int) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_roulette_web.py`:

```python
from web import roulette_web


def test_fresh_state_shape():
    state = roulette_web.fresh_state()
    assert state == {"phase": "betting", "bets": [], "pocket": None, "color": None}


def test_remaining_balance_subtracts_committed_bets():
    state = roulette_web.fresh_state()
    state["bets"] = [{"amount": 5}, {"amount": 3}]
    assert roulette_web.remaining_balance(state, 50) == 42


def test_add_bet_valid_outside_bet():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "red", "", 5)
    assert error is None
    assert state["bets"] == [{"type": "red", "value": None, "amount": 5, "label": "Red (1:1)"}]


def test_add_bet_valid_straight_bet():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "17", 2)
    assert error is None
    assert state["bets"][0]["value"] == "17"
    assert state["bets"][0]["label"] == "Straight-up number (35:1)"


def test_add_bet_straight_00():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "00", 2)
    assert error is None
    assert state["bets"][0]["value"] == "00"


def test_add_bet_invalid_bet_type():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "bogus", "", 5)
    assert error == "Choose a valid bet type."
    assert state["bets"] == []


def test_add_bet_straight_missing_number():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "", 5)
    assert error == "Enter a number 0-36 or 00 for a straight-up bet."
    assert state["bets"] == []


def test_add_bet_straight_invalid_number():
    state = roulette_web.fresh_state()
    state, error = roulette_web.add_bet(state, "straight", "37", 5)
    assert error == "Enter a number 0-36 or 00 for a straight-up bet."
    assert state["bets"] == []


def test_remove_bet_valid_index():
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    roulette_web.add_bet(state, "black", "", 3)
    state = roulette_web.remove_bet(state, 0)
    assert len(state["bets"]) == 1
    assert state["bets"][0]["type"] == "black"


def test_remove_bet_out_of_range_index_no_op():
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    state = roulette_web.remove_bet(state, 9)
    assert len(state["bets"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_roulette_web.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.roulette_web'`

- [ ] **Step 3: Write minimal implementation**

Create `web/roulette_web.py`:

```python
"""Session-state glue between games/roulette.py's pure logic and the Flask web app."""
import random

from games import roulette

BET_TYPES = {bet_type for _, bet_type in roulette.BET_MENU}
BET_LABELS = {bet_type: label for label, bet_type in roulette.BET_MENU}


def fresh_state():
    return {"phase": "betting", "bets": [], "pocket": None, "color": None}


def remaining_balance(state, balance):
    return balance - sum(b["amount"] for b in state["bets"])


def _valid_straight_number(raw):
    raw = (raw or "").strip()
    if raw == "00":
        return "00"
    if raw.isdigit() and 0 <= int(raw) <= 36:
        return str(int(raw))
    return None


def add_bet(state, bet_type, number, amount):
    if bet_type not in BET_TYPES:
        return state, "Choose a valid bet type."

    value = None
    if bet_type == "straight":
        value = _valid_straight_number(number)
        if value is None:
            return state, "Enter a number 0-36 or 00 for a straight-up bet."

    state["bets"].append({
        "type": bet_type,
        "value": value,
        "amount": amount,
        "label": BET_LABELS[bet_type],
    })
    return state, None


def remove_bet(state, index):
    if 0 <= index < len(state["bets"]):
        state["bets"].pop(index)
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_roulette_web.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add web/roulette_web.py tests/test_roulette_web.py
git commit -m "Add Roulette bet-slip build and edit logic"
```

---

## Task 2: Spin resolution

**Files:**
- Modify: `web/roulette_web.py`
- Modify: `tests/test_roulette_web.py`

**Interfaces:**
- Consumes: `fresh_state`, `add_bet` (Task 1); `games.roulette.POCKETS`, `pocket_color`, `evaluate_bet` (existing, unmodified).
- Produces: `spin(state: dict) -> (state: dict, total_wager: int, total_return: int)`, `next_round() -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_roulette_web.py`:

```python
def test_spin_empty_slip_is_no_op():
    state = roulette_web.fresh_state()
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 0
    assert total_return == 0
    assert state["phase"] == "betting"


def test_spin_wrong_phase_is_no_op(monkeypatch):
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    state, _, _ = roulette_web.spin(state)
    assert state["phase"] == "resolved"
    state2, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 0
    assert total_return == 0
    assert state2 == state


def test_spin_red_bet_wins(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 5
    assert total_return == 10
    assert state["pocket"] == "18"
    assert state["color"] == "red"
    assert state["bets"][0]["win"] == 10
    assert state["phase"] == "resolved"


def test_spin_red_bet_loses(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "17")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 5
    assert total_return == 0
    assert state["color"] == "black"
    assert state["bets"][0]["win"] == 0


def test_spin_straight_bet_wins(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "17")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "straight", "17", 2)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 2
    assert total_return == 72  # 2 * 36
    assert state["bets"][0]["win"] == 72


def test_spin_multiple_bets_mixed_outcome(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")  # red
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)         # wins: 10
    roulette_web.add_bet(state, "straight", "17", 2)  # loses: 0
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 7
    assert total_return == 10
    assert state["bets"][0]["win"] == 10
    assert state["bets"][1]["win"] == 0


def test_spin_zero_pocket_outside_bets_lose(monkeypatch):
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "0")
    state = roulette_web.fresh_state()
    roulette_web.add_bet(state, "red", "", 5)
    roulette_web.add_bet(state, "straight", "0", 2)
    state, total_wager, total_return = roulette_web.spin(state)
    assert total_wager == 7
    assert total_return == 72  # only the straight-up 0 bet wins
    assert state["color"] == "green"
    assert state["bets"][0]["win"] == 0
    assert state["bets"][1]["win"] == 72


def test_next_round_returns_fresh_state():
    assert roulette_web.next_round() == roulette_web.fresh_state()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_roulette_web.py -v`
Expected: FAIL — `AttributeError: module 'web.roulette_web' has no attribute 'spin'`

- [ ] **Step 3: Write minimal implementation**

Append to `web/roulette_web.py`:

```python
def spin(state):
    if state["phase"] != "betting" or not state["bets"]:
        return state, 0, 0

    total_wager = sum(b["amount"] for b in state["bets"])
    pocket = random.choice(roulette.POCKETS)
    color = roulette.pocket_color(pocket)

    total_return = 0
    for b in state["bets"]:
        win = b["amount"] * roulette.evaluate_bet(b, pocket)
        b["win"] = win
        total_return += win

    state["pocket"] = pocket
    state["color"] = color
    state["phase"] = "resolved"
    return state, total_wager, total_return


def next_round():
    return fresh_state()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_roulette_web.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add web/roulette_web.py tests/test_roulette_web.py
git commit -m "Add Roulette spin resolution"
```

---

## Task 3: Flask routes, templates, and CSS

**Files:**
- Modify: `web/app.py`
- Create: `web/templates/roulette.html`
- Create: `web/templates/_roulette_table.html`
- Modify: `web/static/style.css` (append)
- Create: `tests/test_app_roulette.py`

**Interfaces:**
- Consumes: `roulette_web.fresh_state`, `remaining_balance`, `add_bet`, `remove_bet`, `spin`, `next_round` (Tasks 1-2); `games.roulette.BET_MENU` (existing); `web/validation.py`'s `validate_bet` (existing); the existing `_maybe_update_record` helper in `web/app.py` (already extracted during the Blackjack web task).
- Produces: routes `GET /roulette` (`roulette_page`), `POST /roulette/bet` (`roulette_bet`), `POST /roulette/remove` (`roulette_remove`), `POST /roulette/spin` (`roulette_spin`), `POST /roulette/next` (`roulette_next`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_roulette.py`:

```python
from web.app import app
from web import roulette_web


def make_client(monkeypatch, record=50):
    monkeypatch.setattr("web.app.db.get_global_record", lambda: record)
    monkeypatch.setattr("web.app.db.update_global_record", lambda balance: None)
    app.config["TESTING"] = True
    return app.test_client()


def test_roulette_page_shows_bet_form(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/roulette")
    assert resp.status_code == 200
    assert b"Add Bet" in resp.data


def test_add_bet_with_invalid_amount_shows_error(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    resp = client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "abc"})
    assert resp.status_code == 200
    assert b"Enter a whole number" in resp.data


def test_add_bet_appends_to_slip(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    resp = client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    assert resp.status_code == 200
    assert b"Bet Slip" in resp.data
    assert b"Spin" in resp.data


def test_remove_bet_removes_line(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    resp = client.post("/roulette/remove", data={"index": "0"})
    assert resp.status_code == 200
    assert b"Bet Slip" not in resp.data


def test_spin_with_empty_slip_is_noop(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    resp = client.post("/roulette/spin")
    assert resp.status_code == 200
    assert b"Add Bet" in resp.data


def test_spin_resolves_and_credits_balance(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    resp = client.post("/roulette/spin")
    assert resp.status_code == 200
    assert b"55" in resp.data  # 50 - 5 wager + 10 win = 55
    assert b"New Round" in resp.data


def test_next_clears_back_to_fresh_slip(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/roulette")
    client.post("/roulette/bet", data={"bet_type": "red", "number": "", "amount": "5"})
    monkeypatch.setattr(roulette_web.random, "choice", lambda seq: "18")
    client.post("/roulette/spin")
    resp = client.post("/roulette/next")
    assert resp.status_code == 200
    assert b"Add Bet" in resp.data
    assert b"Bet Slip" not in resp.data


def test_remove_route_with_no_session_state_does_not_crash(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/roulette/remove", data={"index": "0"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_roulette.py -v`
Expected: FAIL — `werkzeug.routing.exceptions.BuildError` (routes don't exist yet)

- [ ] **Step 3: Write the routes**

In `web/app.py`, add `from games import roulette` next to the existing `from games import slots` import, and `from web import roulette_web` next to the existing `from web import blackjack_web, db, validation` import. Then add, near the existing Blackjack routes:

```python
def render_roulette_table(balance, state, error=None):
    return render_template(
        "_roulette_table.html",
        balance=balance,
        state=state,
        error=error,
        bet_menu=roulette.BET_MENU,
    )


@app.route("/roulette")
def roulette_page():
    return render_template(
        "roulette.html",
        balance=get_balance(),
        state=session.get("roulette") or roulette_web.fresh_state(),
        bet_menu=roulette.BET_MENU,
    )


@app.route("/roulette/bet", methods=["POST"])
def roulette_bet():
    balance = get_balance()
    state = session.get("roulette") or roulette_web.fresh_state()

    remaining = roulette_web.remaining_balance(state, balance)
    amount, error = validation.validate_bet(request.form.get("amount", ""), remaining)
    if error:
        return render_roulette_table(balance, state, error=error)

    bet_type = request.form.get("bet_type", "")
    number = request.form.get("number", "")
    state, error = roulette_web.add_bet(state, bet_type, number, amount)
    session["roulette"] = state
    return render_roulette_table(balance, state, error=error)


@app.route("/roulette/remove", methods=["POST"])
def roulette_remove():
    balance = get_balance()
    state = session.get("roulette") or roulette_web.fresh_state()

    try:
        index = int(request.form.get("index", ""))
    except ValueError:
        index = -1
    state = roulette_web.remove_bet(state, index)
    session["roulette"] = state
    return render_roulette_table(balance, state)


@app.route("/roulette/spin", methods=["POST"])
def roulette_spin():
    balance = get_balance()
    state = session.get("roulette") or roulette_web.fresh_state()

    state, total_wager, total_return = roulette_web.spin(state)
    balance = balance - total_wager + total_return
    session["balance"] = balance
    session["roulette"] = state
    if total_return:
        _maybe_update_record(balance)
    return render_roulette_table(balance, state)


@app.route("/roulette/next", methods=["POST"])
def roulette_next():
    session["roulette"] = roulette_web.next_round()
    return render_roulette_table(get_balance(), session["roulette"])
```

- [ ] **Step 4: Write the templates**

Create `web/templates/roulette.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Roulette</h1>
<div id="game-panel">
  {% include "_roulette_table.html" %}
</div>
{% endblock %}
```

Create `web/templates/_roulette_table.html`:

```html
<div class="panel">
  <p class="balance">Balance: {{ balance }} pts</p>

  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  {% if state.phase == 'resolved' %}
  <p class="result">Ball lands on {{ state.pocket }} ({{ state.color|upper }})</p>
  {% endif %}

  {% if state.bets %}
  <div class="section-label">Bet Slip</div>
  {% for bet in state.bets %}
  <div class="bet-line">
    <span>{{ bet.label }}{% if bet.value %} ({{ bet.value }}){% endif %} - {{ bet.amount }} pts</span>
    {% if state.phase == 'resolved' %}
      {% if bet.win > 0 %}<span class="bet-win">+{{ bet.win }} pts</span>{% else %}<span class="bet-lose">-{{ bet.amount }} pts</span>{% endif %}
    {% else %}
    <form hx-post="{{ url_for('roulette_remove') }}" hx-target="#game-panel" hx-swap="innerHTML">
      <input type="hidden" name="index" value="{{ loop.index0 }}">
      <button type="submit">Remove</button>
    </form>
    {% endif %}
  </div>
  {% endfor %}
  {% endif %}

  {% if state.phase == 'betting' %}
  <form hx-post="{{ url_for('roulette_bet') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <label>Bet type:
      <select name="bet_type">
        {% for label, type in bet_menu %}
        <option value="{{ type }}">{{ label }}</option>
        {% endfor %}
      </select>
    </label>
    <label>Straight number (0-36 or 00): <input type="text" name="number"></label>
    <label>Amount: <input type="text" name="amount" value="1"></label>
    <button type="submit">Add Bet</button>
  </form>

  {% if state.bets %}
  <form hx-post="{{ url_for('roulette_spin') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <button type="submit">Spin</button>
  </form>
  {% endif %}
  {% endif %}

  {% if state.phase == 'resolved' %}
  <form hx-post="{{ url_for('roulette_next') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <button type="submit">New Round</button>
  </form>
  {% endif %}
</div>
```

- [ ] **Step 5: Append the Roulette CSS**

Append to the end of `web/static/style.css`:

```css

/* Roulette */
.bet-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
  padding: 0.3rem 0;
  border-bottom: 1px solid rgba(51, 233, 255, 0.15);
}
.bet-line form { margin: 0; }
.bet-win { color: var(--win); text-shadow: 0 0 6px rgba(57, 255, 106, 0.5); }
.bet-lose { color: var(--marquee); text-shadow: 0 0 6px rgba(255, 77, 28, 0.5); }
.result {
  color: var(--accent);
  text-shadow: 0 0 8px rgba(51, 233, 255, 0.5);
  font-size: 1rem;
  margin-bottom: 0.6rem;
}

select {
  font-family: 'JetBrains Mono', monospace;
  background: var(--ink);
  color: #E8E3F5;
  border: 1px solid rgba(51, 233, 255, 0.35);
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest -v`
Expected: 74 passed (48 from before Tasks 1-3 + 18 from `test_roulette_web.py` + 8 from `test_app_roulette.py`). If the actual count differs, treat it as a real signal to investigate — re-check Tasks 1-2's test counts rather than assuming this number is wrong.

- [ ] **Step 7: Manually verify a full round in the browser**

Run `flask --app web.app run --debug`, open `/roulette`, play through: add two or three different bet types to the slip (including a straight-up number and a straight-up "00"), remove one before spinning, spin and confirm the win/lose breakdown per bet line is correct and the balance updates, then start a new round. Confirm an invalid amount and an out-of-range straight number both show inline errors without losing the rest of the slip. Stop the dev server after.

- [ ] **Step 8: Commit**

```bash
git add web/app.py web/templates/roulette.html web/templates/_roulette_table.html web/static/style.css tests/test_app_roulette.py
git commit -m "Add Roulette routes, templates, and bet-slip styling"
```

---

## Task 4: Manual cross-scenario verification and lobby tile

Same right-sizing judgment as the Blackjack web plan's final task: no new game logic, a QA pass plus flipping the lobby tile live.

- [ ] Run `pytest -v` — full suite passes.
- [ ] Via the dev server (curl or browser), play through and confirm: a multi-bet slip spanning outside bets and a straight-up number resolves each line independently, a 0/00 spin loses every outside bet but pays a matching straight-up bet, removing a bet before spinning actually excludes it from the wager, and spinning with an empty slip is a no-op (no balance change).
- [ ] Update `web/templates/lobby.html`: change the Roulette tile from `<div class="tile soon">...</div>` to `<a class="tile live" href="{{ url_for('roulette_page') }}">` (same shape as the Slots/Blackjack tiles), keeping Poker as `soon`. Re-run `pytest -v` to confirm nothing broke, then commit: `git add web/templates/lobby.html && git commit -m "Link lobby's Roulette tile to the live game"`.
- [ ] Confirm no console/template errors in the Flask dev server log during the walkthrough.
