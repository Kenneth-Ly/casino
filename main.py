"""Cmd Prompt Casino -- entry point: title screen, lobby, and save/load wiring."""
import bankroll as bankroll_mod
import stats as stats_mod
import ui
from games import blackjack, poker, roulette, slots

GAMES = [
    ("Blackjack", blackjack),
    ("Poker (Texas Hold'em)", poker),
    ("Roulette", roulette),
    ("Slot Machine", slots),
]


def show_broke_screen(bankroll):
    ui.clear()
    ui.header(bankroll)
    ui.failure(f"\nYou're completely out of points! All-time high score: {bankroll.high_score} pts")
    if ui.prompt_yes_no("Reset your balance to 50 points and keep playing?"):
        bankroll.reset_after_bust(bankroll_mod.STARTING_BALANCE)
        return True
    return False


def show_stats(bankroll, stats):
    ui.clear()
    ui.header(bankroll)
    print(ui.gold("\n== Stats =="))
    labels = {'blackjack': 'Blackjack', 'poker': 'Poker', 'roulette': 'Roulette', 'slots': 'Slot Machine'}
    for game, title in labels.items():
        d = stats.data[game]
        play_label = stats_mod.PLAY_LABEL[game]
        lines = [
            f"{play_label} played: {d['plays']}",
            f"Total wagered: {d['wagered']} pts",
            f"Total won: {d['won']} pts",
            f"Biggest win: {d['biggest_win']} pts",
        ]
        if game == 'slots':
            lines.append(f"Jackpots hit: {d.get('jackpots', 0)}")
        print(ui.gold(f"\n-- {title} --"))
        ui.print_box(lines)
    ui.pause()


def main():
    bankroll, saved_stats = bankroll_mod.load_state()
    stats = stats_mod.Stats(saved_stats)

    def save():
        bankroll_mod.save_state(bankroll, stats)

    ui.title_screen()

    while True:
        if bankroll.is_broke():
            if show_broke_screen(bankroll):
                save()
                continue
            break

        ui.clear()
        ui.header(bankroll)
        options = [name for name, _ in GAMES] + ["Stats", "Quit"]
        choice = ui.menu("Casino Lobby", options)

        if choice <= len(GAMES):
            _, module = GAMES[choice - 1]
            module.play(bankroll, stats, save)
        elif options[choice - 1] == "Stats":
            show_stats(bankroll, stats)
        else:
            break
        save()

    ui.clear()
    print(ui.gold(f"\nThanks for playing! Final balance: {bankroll.balance} pts | High score: {bankroll.high_score} pts"))
    save()


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print(ui.RESET + "\n\nGoodbye!")
