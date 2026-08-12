"""Classic 3-reel, single-payline slot machine with a fixed jackpot multiplier."""
import random

import ui

# (name, weight, payout multiplier for 3-of-a-kind -- total return, stake included)
SYMBOLS = [
    {'name': 'Cherry', 'weight': 35, 'payout': 2},
    {'name': 'Lemon', 'weight': 25, 'payout': 3},
    {'name': 'Orange', 'weight': 18, 'payout': 5},
    {'name': 'Bell', 'weight': 12, 'payout': 10},
    {'name': 'Bar', 'weight': 7, 'payout': 20},
    {'name': '7', 'weight': 3, 'payout': 100},
]
JACKPOT_SYMBOL = '7'


def spin_reel():
    names = [s['name'] for s in SYMBOLS]
    weights = [s['weight'] for s in SYMBOLS]
    return random.choices(names, weights=weights, k=1)[0]


def spin_reels():
    return [spin_reel() for _ in range(3)]


def payout_for(symbol):
    for s in SYMBOLS:
        if s['name'] == symbol:
            return s['payout']
    return 0


def evaluate_spin(reels):
    """Returns (return_multiplier, is_jackpot). Only exact 3-of-a-kind pays."""
    if reels[0] == reels[1] == reels[2]:
        symbol = reels[0]
        return payout_for(symbol), symbol == JACKPOT_SYMBOL
    return 0, False


def render_reels(symbols):
    width = 9
    border = "+" + ("-" * width + "+") * 3
    row = "|" + "|".join(f"{s:^{width}}" for s in symbols) + "|"
    print(ui.GOLD + border)
    print(ui.GOLD + row)
    print(ui.GOLD + border + ui.RESET)


def animate_spin():
    names = [s['name'] for s in SYMBOLS]

    def frame():
        return "[ " + " | ".join(random.choice(names) for _ in range(3)) + " ]"

    ui.spin_animation(frame, frames=14, delay=0.06)


def print_paytable():
    print(ui.gold("Paytable (3 matching symbols):"))
    lines = []
    for s in SYMBOLS:
        tag = "  <-- JACKPOT" if s['name'] == JACKPOT_SYMBOL else ""
        lines.append(f"{s['name']:<8} x3  ->  {s['payout']}x bet{tag}")
    ui.print_box(lines, color=ui.CYAN)


def play_round(bankroll, stats):
    ui.clear()
    ui.header(bankroll)
    print_paytable()
    bet = ui.prompt_bet(bankroll.balance, min_bet=1, label="slot bet")
    if bet is None:
        return False

    bankroll.withdraw(bet)
    print()
    animate_spin()
    reels = spin_reels()
    render_reels(reels)

    mult, jackpot = evaluate_spin(reels)
    win_amt = bet * mult
    if win_amt:
        bankroll.deposit(win_amt)
    stats.record('slots', wagered=bet, won=win_amt, jackpot=jackpot)

    if jackpot:
        print(ui.gold("\n*** JACKPOT!!! ***"))
        ui.success(f"You won {win_amt} pts! (x{mult})")
    elif win_amt:
        ui.success(f"\nYou won {win_amt} pts! (x{mult})")
    else:
        ui.failure("\nNo match. Better luck next spin!")

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
