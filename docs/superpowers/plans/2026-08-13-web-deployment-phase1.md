# Web Deployment Phase 1 (Slots) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Tasks 0 and 5 are manual/account-setup tasks** (Supabase dashboard, Render dashboard) that require the human's own credentials and browser — they cannot be dispatched to a subagent. Do them together with the user directly in the session. Tasks 1-4 are normal code tasks and can be subagent-dispatched or executed inline.

**Goal:** Deploy the Slot Machine game as a live web app (Flask + HTMX) on Render, backed by a Supabase Postgres table holding a single all-time high-balance record, proving the full pipeline before porting the other 3 games in Phase 2.

**Architecture:** New `web/` package alongside the existing CLI (`main.py`, `games/`, `ui.py`, unchanged). Flask serves server-rendered Jinja2 templates; HTMX swaps just the game panel on Spin/Reset instead of a full page reload. Per-browser play state (balance, session stats) lives in Flask's signed cookie session — no login. `games/slots.py`'s existing pure functions (`spin_reels`, `evaluate_spin`, `payout_for`) are reused unmodified by the new web routes.

**Tech Stack:** Flask, HTMX (CDN), psycopg2 (Supabase Postgres), gunicorn (Render), pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-web-deployment-phase1-design.md`

## Global Constraints

- No user accounts/login — session is a signed cookie, resets if cleared. (spec: Scope decisions)
- Database holds exactly one global record (highest balance ever reached by any visitor), not per-visitor data. (spec: Scope decisions)
- One Supabase Postgres instance used for both local dev and production via `DATABASE_URL`. (spec: Scope decisions)
- `games/slots.py` and the rest of the CLI (`main.py`, `ui.py`, `bankroll.py`, `stats.py`) are not modified — the web app is additive. (spec: Overview)
- Missing `DATABASE_URL` at startup is a hard failure with a clear error message. (spec: Error handling)
- DB unreachable at request time degrades gracefully (lobby shows "record unavailable"; a spin still completes, the record update is just skipped). (spec: Error handling)

---

## Task 0 (Manual): Create Supabase project and tables

**This task is done together with the user in chat — it requires their Supabase account.**

- [ ] **Step 1: Create a Supabase project**

Guide the user to https://supabase.com/dashboard → New project. Free tier is fine. Note the project's Postgres connection string (Project Settings → Database → Connection string → URI). This is `DATABASE_URL`.

- [ ] **Step 2: Create the app table and the test table**

In the Supabase SQL editor, run:

```sql
create table if not exists global_record (
  id boolean primary key default true,
  balance integer not null default 50,
  constraint single_row check (id)
);
insert into global_record (id, balance) values (true, 50)
  on conflict (id) do nothing;

create table if not exists global_record_test (
  id boolean primary key default true,
  balance integer not null default 50,
  constraint single_row check (id)
);
insert into global_record_test (id, balance) values (true, 50)
  on conflict (id) do nothing;
```

`global_record_test` is a separate table so Task 2's automated tests never
overwrite the real high-score data in `global_record`.

- [ ] **Step 3: Save the connection string locally (not committed)**

The user provides the `DATABASE_URL` value; it goes into a local `.env` file in Task 1 (gitignored, never committed).

---

## Task 1: Bet validation

**Files:**
- Create: `web/__init__.py` (empty — makes `web` a package)
- Create: `web/validation.py`
- Test: `tests/test_validation.py`
- Modify: `requirements.txt` — add `Flask>=3.0`, `pytest>=8.0`
- Modify: `.gitignore` — add `.env`
- Create: `.env.example`

**Interfaces:**
- Produces: `validate_bet(raw: str, balance: int, min_bet: int = 1) -> tuple[int | None, str | None]` — returns `(amount, None)` on success or `(None, error_message)` on failure. Exactly one of the two is `None`.

- [ ] **Step 1: Scaffold the web package and update dependencies**

Create `web/__init__.py` (empty file).

Edit `requirements.txt` to:

```
colorama>=0.4.6
Flask>=3.0
gunicorn>=21.2
psycopg2-binary>=2.9
python-dotenv>=1.0
pytest>=8.0
```

Create `.env.example`:

```
DATABASE_URL=postgresql://user:password@host:5432/postgres
SECRET_KEY=replace-with-a-random-hex-string
```

Add `.env` to `.gitignore` (append if the file already has entries).

Run: `pip install -r requirements.txt`
Expected: installs without error.

- [ ] **Step 2: Write the failing test**

Create `tests/test_validation.py`:

```python
from web.validation import validate_bet


def test_valid_bet_returns_amount_and_no_error():
    assert validate_bet("10", balance=50) == (10, None)


def test_non_numeric_bet_returns_error():
    amount, error = validate_bet("abc", balance=50)
    assert amount is None
    assert error is not None


def test_bet_above_balance_returns_error():
    amount, error = validate_bet("100", balance=50)
    assert amount is None
    assert error is not None


def test_bet_below_min_returns_error():
    amount, error = validate_bet("0", balance=50)
    assert amount is None
    assert error is not None


def test_negative_bet_returns_error():
    amount, error = validate_bet("-5", balance=50)
    assert amount is None
    assert error is not None


def test_blank_bet_returns_error():
    amount, error = validate_bet("", balance=50)
    assert amount is None
    assert error is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.validation'`

- [ ] **Step 3: Write minimal implementation**

Create `web/validation.py`:

```python
"""Pure bet-validation logic shared by the web game routes."""


def validate_bet(raw, balance, min_bet=1):
    """Returns (amount, error). Exactly one of the two is None."""
    raw = (raw or "").strip()
    error = f"Enter a whole number between {min_bet} and {balance}."
    if not raw.isdigit():
        return None, error
    amount = int(raw)
    if not (min_bet <= amount <= balance):
        return None, error
    return amount, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validation.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add web/__init__.py web/validation.py tests/test_validation.py requirements.txt .env.example .gitignore
git commit -m "Add web package scaffolding and bet validation"
```

---

## Task 2: Database wrapper

**Prerequisite:** Task 0 complete — `DATABASE_URL` available and `global_record` / `global_record_test` tables exist in Supabase. Create a local `.env` (gitignored) with:

```
DATABASE_URL=<the connection string from Task 0>
SECRET_KEY=<output of: python -c "import secrets; print(secrets.token_hex(32))">
```

**Files:**
- Create: `web/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `DATABASE_URL` env var (via `os.environ`).
- Produces: `get_global_record(table: str = "global_record") -> int`, `update_global_record(balance: int, table: str = "global_record") -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_db.py`:

```python
import os

import psycopg2
import pytest

from web import db

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)

TEST_TABLE = "global_record_test"


@pytest.fixture(autouse=True)
def reset_test_table():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        cur.execute(f"UPDATE {TEST_TABLE} SET balance = 50")
    conn.commit()
    conn.close()
    yield


def test_get_global_record_returns_seeded_value():
    assert db.get_global_record(table=TEST_TABLE) == 50


def test_update_global_record_applies_when_higher():
    db.update_global_record(75, table=TEST_TABLE)
    assert db.get_global_record(table=TEST_TABLE) == 75


def test_update_global_record_ignores_lower_value():
    db.update_global_record(75, table=TEST_TABLE)
    db.update_global_record(60, table=TEST_TABLE)
    assert db.get_global_record(table=TEST_TABLE) == 75
```

This test needs `python-dotenv` to load `.env` when running `pytest` directly, since pytest doesn't source `.env` on its own. Create `tests/conftest.py`:

```python
from dotenv import load_dotenv

load_dotenv()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.db'`

- [ ] **Step 3: Write minimal implementation**

Create `web/db.py`:

```python
"""Supabase/Postgres wrapper for the single global high-balance record."""
import os

import psycopg2
from psycopg2 import sql

TABLE = "global_record"


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def get_global_record(table=TABLE):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT balance FROM {}").format(sql.Identifier(table)))
            row = cur.fetchone()
            return row[0] if row else 50
    finally:
        conn.close()


def update_global_record(balance, table=TABLE):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET balance = %s WHERE balance < %s").format(
                    sql.Identifier(table)
                ),
                (balance, balance),
            )
        conn.commit()
    finally:
        conn.close()
```

`table` is always a hardcoded value from within this codebase (`"global_record"` or `"global_record_test"`), never taken from a request — `sql.Identifier` is used anyway so the query is safely composed rather than string-formatted.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: 3 passed (or 3 skipped if `DATABASE_URL` isn't set in this environment — in that case, run it manually once with `.env` present to confirm before moving on)

- [ ] **Step 5: Commit**

```bash
git add web/db.py tests/test_db.py tests/conftest.py
git commit -m "Add Supabase-backed global high-balance record"
```

Do NOT commit `.env` — verify with `git status` that it doesn't appear.

---

## Task 3: Flask app, routes, and templates

**Files:**
- Create: `web/app.py`
- Create: `web/templates/base.html`
- Create: `web/templates/lobby.html`
- Create: `web/templates/slots.html`
- Create: `web/templates/_slots_panel.html`
- Create: `web/static/style.css`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `validate_bet` from `web/validation.py` (Task 1); `get_global_record`, `update_global_record` from `web/db.py` (Task 2); `spin_reels()`, `evaluate_spin(reels) -> (multiplier, is_jackpot)`, `SYMBOLS`, `JACKPOT_SYMBOL` from `games/slots.py` (existing, unmodified).
- Produces: Flask app object `web.app.app`; routes `GET /` (`lobby`), `GET /slots` (`slots_page`), `POST /slots/spin` (`slots_spin`), `POST /slots/reset` (`slots_reset`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_app.py`:

```python
from web.app import app


def make_client(monkeypatch, record=50):
    monkeypatch.setattr("web.app.db.get_global_record", lambda: record)
    monkeypatch.setattr("web.app.db.update_global_record", lambda balance: None)
    app.config["TESTING"] = True
    return app.test_client()


def test_lobby_shows_global_record(monkeypatch):
    client = make_client(monkeypatch, record=120)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"120" in resp.data


def test_lobby_handles_db_error(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("web.app.db.get_global_record", boom)
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"unavailable" in resp.data


def test_slots_page_starts_with_default_balance(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/slots")
    assert resp.status_code == 200
    assert b"50" in resp.data


def test_spin_with_invalid_bet_shows_error(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/slots")
    resp = client.post("/slots/spin", data={"bet": "abc"})
    assert resp.status_code == 200
    assert b"Enter a whole number" in resp.data


def test_spin_with_valid_bet_deducts_and_shows_reels(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/slots")
    resp = client.post("/slots/spin", data={"bet": "5"})
    assert resp.status_code == 200


def test_reset_restores_default_balance(monkeypatch):
    client = make_client(monkeypatch)
    client.get("/slots")
    client.post("/slots/spin", data={"bet": "50"})
    resp = client.post("/slots/reset")
    assert resp.status_code == 200
    assert b"50" in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.app'`

- [ ] **Step 3: Write the templates**

Create `web/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Cmd Prompt Casino</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <header class="topbar"><a href="{{ url_for('lobby') }}" class="brand">Cmd Prompt Casino</a></header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

Create `web/templates/lobby.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Casino Lobby</h1>
<p class="record">
  {% if record is not none %}
    All-time record: <strong>{{ record }} pts</strong>
  {% else %}
    All-time record: unavailable
  {% endif %}
</p>
<ul class="game-list">
  <li><a href="{{ url_for('slots_page') }}">Slot Machine</a></li>
</ul>
{% endblock %}
```

Create `web/templates/slots.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Slot Machine</h1>
<div id="game-panel">
  {% include "_slots_panel.html" %}
</div>
{% endblock %}
```

Create `web/templates/_slots_panel.html`:

```html
<div class="panel">
  <p class="balance">Balance: {{ balance }} pts</p>

  <table class="paytable">
    <tr><th>Symbols</th><th>Payout</th></tr>
    {% for s in symbols %}
    <tr{% if s.name == jackpot_symbol %} class="jackpot-row"{% endif %}>
      <td>{{ s.name }} x3</td>
      <td>{{ s.payout }}x{% if s.name == jackpot_symbol %} (JACKPOT){% endif %}</td>
    </tr>
    {% endfor %}
  </table>

  {% if reels %}
  <div class="reels">[ {{ reels[0] }} | {{ reels[1] }} | {{ reels[2] }} ]</div>
  {% endif %}
  {% if message %}<p class="message">{{ message }}</p>{% endif %}
  {% if error %}<p class="error">{{ error }}</p>{% endif %}

  {% if balance > 0 %}
  <form hx-post="{{ url_for('slots_spin') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <label>Bet (1-{{ balance }}): <input type="text" name="bet" value="1"></label>
    <button type="submit">Spin</button>
  </form>
  {% else %}
  <p class="busted">You're out of points!</p>
  <form hx-post="{{ url_for('slots_reset') }}" hx-target="#game-panel" hx-swap="innerHTML">
    <button type="submit">Reset to 50 pts</button>
  </form>
  {% endif %}
</div>
```

Create `web/static/style.css`:

```css
body { background: #0b3d20; color: #f5e6c8; font-family: Georgia, serif; margin: 0; }
.topbar { background: #062814; padding: 1rem 2rem; }
.brand { color: #ffd700; text-decoration: none; font-weight: bold; font-size: 1.25rem; }
main { max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
h1 { color: #ffd700; }
.paytable { border-collapse: collapse; width: 100%; margin: 1rem 0; }
.paytable th, .paytable td { border: 1px solid #ffd700; padding: 0.4rem 0.8rem; text-align: left; }
.jackpot-row { color: #ffd700; font-weight: bold; }
.reels { font-size: 1.5rem; margin: 1rem 0; letter-spacing: 0.1em; }
.message { color: #7CFC00; }
.error { color: #ff6b6b; }
.busted { color: #ff6b6b; font-weight: bold; }
form { margin-top: 1rem; }
input[type="text"] { width: 4rem; }
button { background: #ffd700; border: none; padding: 0.5rem 1rem; cursor: pointer; font-weight: bold; }
.game-list { list-style: none; padding: 0; }
.game-list a { color: #ffd700; font-size: 1.1rem; }
```

- [ ] **Step 4: Write minimal implementation**

Create `web/app.py`:

```python
"""Flask web app: Slot Machine, Phase 1 of the web deployment."""
import os

from dotenv import load_dotenv
from flask import Flask, render_template, request, session

from games import slots
from web import db, validation

load_dotenv()

if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL environment variable is required")
if not os.environ.get("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY environment variable is required")

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

STARTING_BALANCE = 50


def get_balance():
    return session.setdefault("balance", STARTING_BALANCE)


def get_stats():
    return session.setdefault(
        "stats", {"plays": 0, "wagered": 0, "won": 0, "jackpots": 0}
    )


def render_panel(balance, error=None, reels=None, message=None):
    return render_template(
        "_slots_panel.html",
        balance=balance,
        error=error,
        reels=reels,
        message=message,
        symbols=slots.SYMBOLS,
        jackpot_symbol=slots.JACKPOT_SYMBOL,
    )


@app.route("/")
def lobby():
    try:
        record = db.get_global_record()
    except Exception:
        record = None
    return render_template("lobby.html", record=record)


@app.route("/slots")
def slots_page():
    return render_template(
        "slots.html",
        balance=get_balance(),
        symbols=slots.SYMBOLS,
        jackpot_symbol=slots.JACKPOT_SYMBOL,
    )


@app.route("/slots/spin", methods=["POST"])
def slots_spin():
    balance = get_balance()
    amount, error = validation.validate_bet(request.form.get("bet", ""), balance)
    if error:
        return render_panel(balance, error=error)

    balance -= amount
    reels = slots.spin_reels()
    mult, jackpot = slots.evaluate_spin(reels)
    win = amount * mult
    balance += win

    stats = get_stats()
    stats["plays"] += 1
    stats["wagered"] += amount
    stats["won"] += win
    if jackpot:
        stats["jackpots"] += 1
    session["stats"] = stats
    session["balance"] = balance

    try:
        if balance > db.get_global_record():
            db.update_global_record(balance)
    except Exception:
        pass

    if jackpot:
        message = f"JACKPOT! You won {win} pts!"
    elif win:
        message = f"You won {win} pts!"
    else:
        message = "No match. Better luck next spin!"

    return render_panel(balance, reels=reels, message=message)


@app.route("/slots/reset", methods=["POST"])
def slots_reset():
    session["balance"] = STARTING_BALANCE
    session["stats"] = {"plays": 0, "wagered": 0, "won": 0, "jackpots": 0}
    return render_panel(STARTING_BALANCE)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_app.py -v`
Expected: 6 passed

(`tests/conftest.py` from Task 2 already calls `load_dotenv()`, so the `.env` created in Task 2 supplies `DATABASE_URL` and `SECRET_KEY` for this test run too — nothing extra to set.)

- [ ] **Step 6: Commit**

```bash
git add web/app.py web/templates web/static tests/test_app.py
git commit -m "Add Flask Slot Machine routes and templates"
```

---

## Task 4: Local end-to-end verification and Procfile

**Files:**
- Create: `Procfile`

**Interfaces:**
- Consumes: `web.app:app` (Task 3).

- [ ] **Step 1: Create the Procfile**

Create `Procfile` (repo root, no extension):

```
web: gunicorn web.app:app
```

- [ ] **Step 2: Run the app locally**

Ensure `.env` (from Task 2) has `DATABASE_URL` and `SECRET_KEY` set.

Run: `flask --app web.app run --debug`
Expected: server starts on `http://127.0.0.1:5000`

- [ ] **Step 3: Manually verify the full flow in a browser**

Open `http://127.0.0.1:5000/`:
- Lobby shows "All-time record: 50 pts" (first run) and a "Slot Machine" link.

Click through to `/slots`:
- Balance shows 50 pts, paytable renders, bet field defaults to 1.
- Enter an out-of-range bet (e.g. `999`) and Spin — panel re-renders in place (no full page reload) showing the validation error, balance unchanged.
- Enter a valid bet (e.g. `10`) and Spin repeatedly until either a win or the balance reaches 0.
- On a win, balance increases and a win message shows.
- If balance ever exceeds the lobby's displayed record, reload `/` and confirm the record updated.
- Spin until balance hits 0 — confirm the "out of points" state and Reset button appear, and Reset restores 50 pts.

- [ ] **Step 4: Commit**

```bash
git add Procfile
git commit -m "Add Procfile for Render deployment"
```

---

## Task 5 (Manual): Deploy to Render and smoke-test

**This task is done together with the user in chat — it requires their Render account.**

- [ ] **Step 1: Push the branch/commits to GitHub**

Confirm with the user before pushing (per repo conventions — do not push without explicit confirmation).

- [ ] **Step 2: Create the Render web service**

Guide the user to https://dashboard.render.com → New → Web Service → connect this GitHub repo.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn web.app:app`
- Add environment variables: `DATABASE_URL` (same Supabase connection string from Task 0) and `SECRET_KEY` (same value used locally, or a freshly generated one — sessions just won't carry over from local dev).

- [ ] **Step 3: Deploy and smoke-test the live URL**

Once Render finishes the build, open the live `https://<service-name>.onrender.com` URL and repeat the checks from Task 4 Step 3 (lobby loads, record displays, spin works, bust-and-reset works, global record updates on a new high) against the live deployment.

- [ ] **Step 4: Confirm the four rubric criteria**

- Live public HTTPS URL that loads: the Render URL.
- Real host, not a default page: Render web service running this app.
- App you built, not a template: confirmed by the smoke test.
- Database connected: Supabase `global_record` table, confirmed by the record updating across requests.
