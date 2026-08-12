"""American roulette: 38 pockets (0, 00, 1-36), standard bets and payouts."""
import random

import ui

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
POCKETS = ['0', '00'] + [str(n) for n in range(1, 37)]

BET_MENU = [
    ("Red (1:1)", 'red'),
    ("Black (1:1)", 'black'),
    ("Even (1:1)", 'even'),
    ("Odd (1:1)", 'odd'),
    ("1st Dozen 1-12 (2:1)", 'dozen1'),
    ("2nd Dozen 13-24 (2:1)", 'dozen2'),
    ("3rd Dozen 25-36 (2:1)", 'dozen3'),
    ("Straight-up number (35:1)", 'straight'),
]


def pocket_color(pocket):
    if pocket in ('0', '00'):
        return 'green'
    return 'red' if int(pocket) in RED_NUMBERS else 'black'


def evaluate_bet(bet, pocket):
    """Returns the total return multiplier (stake included), or 0 on a loss."""
    bet_type = bet['type']
    if bet_type == 'straight':
        return 36 if bet['value'] == pocket else 0
    if pocket in ('0', '00'):
        return 0  # outside bets always lose on 0/00
    n = int(pocket)
    color = pocket_color(pocket)
    if bet_type == 'red':
        return 2 if color == 'red' else 0
    if bet_type == 'black':
        return 2 if color == 'black' else 0
    if bet_type == 'even':
        return 2 if n % 2 == 0 else 0
    if bet_type == 'odd':
        return 2 if n % 2 == 1 else 0
    if bet_type == 'dozen1':
        return 3 if 1 <= n <= 12 else 0
    if bet_type == 'dozen2':
        return 3 if 13 <= n <= 24 else 0
    if bet_type == 'dozen3':
        return 3 if 25 <= n <= 36 else 0
    return 0


def describe_bet(bet):
    if bet['type'] == 'straight':
        return f"Straight-up {bet['value']} (35:1) - {bet['amount']} pts"
    return f"{bet['label']} - {bet['amount']} pts"


def prompt_straight_number():
    while True:
        raw = input("Enter number to bet on (0-36, or 00, or 'q' to cancel): ").strip()
        if raw.lower() == 'q':
            return None
        if raw == '00':
            return '00'
        if raw.isdigit() and 0 <= int(raw) <= 36:
            return str(int(raw))
        ui.failure("Enter a number 0-36 or 00.")


def collect_bets(bankroll):
    bets = []
    committed = 0
    while True:
        remaining = bankroll.balance - committed
        ui.clear()
        ui.header(bankroll)
        print(ui.gold(f"\nCommitted so far: {committed} pts   |   Remaining: {remaining} pts"))
        for b in bets:
            print("  - " + describe_bet(b))

        options = [label for label, _ in BET_MENU]
        if bets:
            options.append("Spin the wheel!")
        options.append("Cancel and clear all bets")

        choice = ui.menu("Place a bet", options)
        label = options[choice - 1]

        if label == "Spin the wheel!":
            return bets
        if label == "Cancel and clear all bets":
            return None

        bet_type = dict(BET_MENU)[label]
        if remaining <= 0:
            ui.failure("No more balance available to bet with.")
            continue

        value = None
        if bet_type == 'straight':
            value = prompt_straight_number()
            if value is None:
                continue

        amount = ui.prompt_bet(remaining, min_bet=1, label=f"amount for {label}")
        if amount is None:
            continue
        bets.append({'type': bet_type, 'value': value, 'amount': amount, 'label': label})
        committed += amount


def animate_spin(final_pocket):
    def frame():
        return "Spinning... " + random.choice(POCKETS)

    ui.spin_animation(frame, frames=15, delay=0.05)
    color = pocket_color(final_pocket)
    color_code = {'red': ui.RED, 'black': ui.WHITE, 'green': ui.GREEN}[color]
    print(f"{color_code}Ball lands on: {final_pocket} ({color.upper()}){ui.RESET}")


def play_round(bankroll, stats):
    bets = collect_bets(bankroll)
    if not bets:
        return False

    total_wager = sum(b['amount'] for b in bets)
    bankroll.withdraw(total_wager)

    ui.clear()
    ui.header(bankroll)
    pocket = random.choice(POCKETS)
    animate_spin(pocket)

    total_return = 0
    print()
    for b in bets:
        mult = evaluate_bet(b, pocket)
        win_amt = b['amount'] * mult
        total_return += win_amt
        if win_amt > 0:
            ui.success(f"{describe_bet(b)} -> WIN, +{win_amt} pts")
        else:
            ui.failure(f"{describe_bet(b)} -> lose, -{b['amount']} pts")

    if total_return:
        bankroll.deposit(total_return)
    stats.record('roulette', wagered=total_wager, won=total_return)

    ui.header(bankroll)
    return True


def play(bankroll, stats, save_callback):
    while True:
        if bankroll.is_broke():
            ui.failure("You're out of points!")
            return
        played = play_round(bankroll, stats)
        save_callback()
        if not played:
            return
        if bankroll.is_broke():
            ui.failure("You've busted out of points!")
            ui.pause()
            return
        if not ui.prompt_yes_no("\nSpin again?"):
            return
