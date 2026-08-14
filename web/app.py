"""Flask web app: Slot Machine, Phase 1 of the web deployment."""
import os

from dotenv import load_dotenv
from flask import Flask, render_template, request, session

from games import slots
from web import blackjack_web, db, validation

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


def _maybe_update_record(balance):
    try:
        db.update_global_record(balance)
    except Exception as exc:
        app.logger.warning("global record update skipped: %s", type(exc).__name__)


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
    except Exception as exc:
        app.logger.warning("global record read skipped: %s", type(exc).__name__)
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

    _maybe_update_record(balance)

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


def render_blackjack_table(balance, state, error=None):
    return render_template(
        "_blackjack_table.html",
        balance=balance,
        state=state,
        error=error,
        suit_symbol=blackjack_web.suit_symbol,
        is_red_suit=blackjack_web.is_red_suit,
        max_splits=blackjack_web.MAX_SPLITS,
    )


@app.route("/blackjack")
def blackjack_page():
    return render_template(
        "blackjack.html",
        balance=get_balance(),
        state=session.get("blackjack"),
        suit_symbol=blackjack_web.suit_symbol,
        is_red_suit=blackjack_web.is_red_suit,
        max_splits=blackjack_web.MAX_SPLITS,
    )


@app.route("/blackjack/deal", methods=["POST"])
def blackjack_deal():
    balance = get_balance()
    amount, error = validation.validate_bet(request.form.get("bet", ""), balance)
    if error:
        return render_blackjack_table(balance, None, error=error)

    balance -= amount
    state, winnings = blackjack_web.start_round(amount)
    balance += winnings
    session["balance"] = balance
    session["blackjack"] = state
    if winnings:
        _maybe_update_record(balance)
    return render_blackjack_table(balance, state)


@app.route("/blackjack/insurance", methods=["POST"])
def blackjack_insurance():
    balance = get_balance()
    state = session.get("blackjack")
    if not state:
        return render_blackjack_table(balance, None)

    decision = request.form.get("decision", "decline")
    state, cost, winnings = blackjack_web.apply_insurance(state, decision, balance)
    balance = balance - cost + winnings
    session["balance"] = balance
    session["blackjack"] = state
    if winnings:
        _maybe_update_record(balance)
    return render_blackjack_table(balance, state)


@app.route("/blackjack/action", methods=["POST"])
def blackjack_action():
    balance = get_balance()
    state = session.get("blackjack")
    if not state:
        return render_blackjack_table(balance, None)

    action = request.form.get("action", "")
    state, cost, winnings = blackjack_web.apply_action(state, action, balance)
    balance = balance - cost + winnings
    session["balance"] = balance
    session["blackjack"] = state
    if winnings:
        _maybe_update_record(balance)
    return render_blackjack_table(balance, state)


@app.route("/blackjack/next", methods=["POST"])
def blackjack_next():
    session.pop("blackjack", None)
    return render_blackjack_table(get_balance(), None)
