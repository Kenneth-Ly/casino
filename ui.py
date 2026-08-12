"""Colorama-based terminal UI helpers shared by every game: colors, boxed
menus, ASCII card rendering, the title screen, and simple animations."""
import os
import sys
import time

from colorama import init as colorama_init, Fore, Style

colorama_init(autoreset=True)

RESET = Style.RESET_ALL
GOLD = Fore.YELLOW + Style.BRIGHT
CYAN = Fore.CYAN
GREEN = Fore.GREEN + Style.BRIGHT
RED = Fore.RED + Style.BRIGHT
WHITE = Fore.WHITE
DIM = Style.DIM


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def pause(msg="\nPress Enter to continue..."):
    input(f"{DIM}{msg}{RESET}")


def success(text):
    print(f"{GREEN}{text}{RESET}")


def failure(text):
    print(f"{RED}{text}{RESET}")


def info(text):
    print(f"{CYAN}{text}{RESET}")


def gold(text):
    return f"{GOLD}{text}{RESET}"


def header(bankroll):
    line = f" Balance: {bankroll.balance} pts   |   High Score: {bankroll.high_score} pts "
    width = max(len(line) + 2, 40)
    print(GOLD + "=" * width)
    print(GOLD + line.center(width))
    print(GOLD + "=" * width + RESET)


def print_box(lines, color=CYAN, min_width=0):
    width = max([len(l) for l in lines] + [min_width])
    print(color + "+" + "-" * (width + 2) + "+")
    for l in lines:
        print(color + "| " + l.ljust(width) + " |")
    print(color + "+" + "-" * (width + 2) + "+" + RESET)


def title_screen():
    clear()
    banner = r"""
   ______           _
  / ____/___ ______(_)___  ____
 / /   / __ `/ ___/ / __ \/ __ \
/ /___/ /_/ (__  ) / / / / /_/ /
\____/\__,_/____/_/_/ /_/\____/
"""
    print(GOLD + banner + RESET)
    print(RED + "          * S * H * D * C *   Welcome to the table   * C * D * H * S *" + RESET)
    print()
    input(DIM + "        Press Enter to enter the casino..." + RESET)


def menu(title, options):
    """options: list of strings. Returns the 1-based selected index."""
    while True:
        print(GOLD + f"\n== {title} ==" + RESET)
        for i, opt in enumerate(options, 1):
            print(f"  {CYAN}{i}{RESET}. {opt}")
        choice = input(f"{DIM}> {RESET}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice)
        failure("Invalid choice, try again.")


def prompt_bet(balance, min_bet=1, label="bet"):
    while True:
        raw = input(f"Enter your {label} ({min_bet}-{balance} pts, or 'q' to cancel): ").strip().lower()
        if raw == 'q':
            return None
        if raw.isdigit():
            amount = int(raw)
            if min_bet <= amount <= balance:
                return amount
        failure(f"Enter a whole number between {min_bet} and {balance}.")


def prompt_yes_no(question):
    while True:
        raw = input(f"{question} (y/n): ").strip().lower()
        if raw in ('y', 'yes'):
            return True
        if raw in ('n', 'no'):
            return False
        failure("Please answer y or n.")


def card_color(card):
    return RED if card.is_red else WHITE


def card_str(card):
    return f"{card_color(card)}{card.rank}{card.suit}{RESET}"


def cards_str(cards):
    return " ".join(card_str(c) for c in cards)


def render_cards(cards, hide_first=False):
    """Prints a row of ASCII-boxed cards. hide_first hides cards[0] (e.g. dealer hole card)."""
    tops, mids, bots = [], [], []
    for i, c in enumerate(cards):
        if hide_first and i == 0:
            color = CYAN
            rank_line = "??"
        else:
            color = card_color(c)
            rank_line = f"{c.rank:<2}{c.suit}"
        tops.append(color + "+-----+")
        mids.append(color + f"|{rank_line:<5}|")
        bots.append(color + "+-----+")
    print(" ".join(tops) + RESET)
    print(" ".join(mids) + RESET)
    print(" ".join(bots) + RESET)


def spin_animation(get_frame, frames=12, delay=0.06):
    """Calls get_frame() repeatedly, overwriting the same line, to simulate spinning."""
    for _ in range(frames):
        sys.stdout.write("\r" + get_frame() + "   ")
        sys.stdout.flush()
        time.sleep(delay)
    print()
