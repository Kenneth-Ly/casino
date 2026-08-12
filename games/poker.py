"""Texas Hold'em poker: player + 3 heuristic bots, blinds, betting rounds,
side pots, and standard hand-ranking showdown."""
import random
from itertools import combinations

import cards
import ui

SMALL_BLIND = 1
BIG_BLIND = 2

HAND_NAMES = {
    8: 'Straight Flush', 7: 'Four of a Kind', 6: 'Full House', 5: 'Flush',
    4: 'Straight', 3: 'Three of a Kind', 2: 'Two Pair', 1: 'One Pair', 0: 'High Card',
}

PERSONALITIES = {
    'TAG': {'fold': 0.35, 'raise': 0.65, 'bluff': 0.05},       # Tight-Aggressive
    'LAG': {'fold': 0.20, 'raise': 0.45, 'bluff': 0.20},       # Loose-Aggressive
    'Station': {'fold': 0.08, 'raise': 0.85, 'bluff': 0.02},   # Calling Station
}


# ---------- Hand evaluation ----------

def evaluate_5(five_cards):
    """Returns a comparable tuple; bigger tuple = better hand."""
    ranks = sorted((c.rank_value for c in five_cards), reverse=True)
    suits = [c.suit for c in five_cards]
    is_flush = len(set(suits)) == 1

    unique_ranks = sorted(set(ranks), reverse=True)
    is_straight = False
    straight_high = None
    if len(unique_ranks) == 5:
        if unique_ranks[0] - unique_ranks[4] == 4:
            is_straight = True
            straight_high = unique_ranks[0]
        elif set(unique_ranks) == {14, 5, 4, 3, 2}:
            is_straight = True
            straight_high = 5  # wheel: A-2-3-4-5

    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    by_count = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))

    if is_straight and is_flush:
        return (8, straight_high)
    if by_count[0][1] == 4:
        four_rank = by_count[0][0]
        kicker = max(r for r in ranks if r != four_rank)
        return (7, four_rank, kicker)
    if by_count[0][1] == 3 and by_count[1][1] == 2:
        return (6, by_count[0][0], by_count[1][0])
    if is_flush:
        return (5,) + tuple(ranks)
    if is_straight:
        return (4, straight_high)
    if by_count[0][1] == 3:
        three_rank = by_count[0][0]
        kickers = sorted((r for r in ranks if r != three_rank), reverse=True)
        return (3, three_rank) + tuple(kickers)
    if by_count[0][1] == 2 and by_count[1][1] == 2:
        pair_ranks = sorted([by_count[0][0], by_count[1][0]], reverse=True)
        kicker = max(r for r in ranks if r not in pair_ranks)
        return (2,) + tuple(pair_ranks) + (kicker,)
    if by_count[0][1] == 2:
        pair_rank = by_count[0][0]
        kickers = sorted((r for r in ranks if r != pair_rank), reverse=True)
        return (1, pair_rank) + tuple(kickers)
    return (0,) + tuple(ranks)


def best_hand(seven_or_fewer_cards):
    """Returns (best_score_tuple, best_5_card_combo) from 5-7 cards."""
    best_score = None
    best_combo = None
    for combo in combinations(seven_or_fewer_cards, 5):
        score = evaluate_5(list(combo))
        if best_score is None or score > best_score:
            best_score = score
            best_combo = combo
    return best_score, best_combo


def preflop_strength(hole):
    r1, r2 = sorted((c.rank_value for c in hole), reverse=True)
    suited = hole[0].suit == hole[1].suit
    pair = r1 == r2
    score = r1 + r2
    if pair:
        score += 10 + r1
    if suited:
        score += 3
    gap = r1 - r2
    if not pair:
        if gap == 1:
            score += 2
        elif gap == 2:
            score += 1
        elif gap >= 5:
            score -= 3
    return score


def estimate_strength(hole, board):
    if not board:
        return min(1.0, max(0.0, preflop_strength(hole) / 40.0))
    score, _ = best_hand(hole + board)
    return score[0] / 8.0


# ---------- Player ----------

class Player:
    def __init__(self, name, stack, is_bot=False, personality=None):
        self.name = name
        self.stack = stack
        self.is_bot = is_bot
        self.personality = personality
        self.hole = []
        self.folded = False
        self.all_in = False
        self.current_bet = 0
        self.total_committed = 0
        self.showdown_score = None

    def reset_for_hand(self):
        self.hole = []
        self.folded = False
        self.all_in = False
        self.current_bet = 0
        self.total_committed = 0
        self.showdown_score = None


# ---------- Betting round ----------

def apply_action(player, action, amount, current_max_bet):
    if action == 'fold':
        player.folded = True
        return current_max_bet, False
    if action == 'check':
        return current_max_bet, False
    if action == 'call':
        pay = min(current_max_bet - player.current_bet, player.stack)
        player.stack -= pay
        player.current_bet += pay
        player.total_committed += pay
        if player.stack == 0:
            player.all_in = True
        return current_max_bet, False
    # 'raise' or 'allin': amount is the total target current_bet for this player
    target = amount
    pay = min(target - player.current_bet, player.stack)
    player.stack -= pay
    player.current_bet += pay
    player.total_committed += pay
    if player.stack == 0:
        player.all_in = True
    raised = player.current_bet > current_max_bet
    return max(current_max_bet, player.current_bet), raised


def prompt_raise_amount(min_target, max_target):
    while True:
        raw = input(f"Raise TO how many total points ({min_target}-{max_target}, or 'q' to cancel): ").strip().lower()
        if raw == 'q':
            return None
        if raw.isdigit():
            value = int(raw)
            if min_target <= value <= max_target:
                return value
        ui.failure(f"Enter a number between {min_target} and {max_target}.")


def human_decide_action(p, to_call):
    if to_call <= 0:
        options = ["Check", "Bet", f"All-In ({p.stack} pts)"]
    else:
        call_amt = min(to_call, p.stack)
        options = ["Fold", f"Call ({call_amt} pts)", "Raise", f"All-In ({p.stack} pts)"]
    choice = ui.menu("Your move", options)
    label = options[choice - 1]

    if label == "Check":
        return ('check', 0)
    if label == "Fold":
        return ('fold', 0)
    if label.startswith("Call"):
        return ('call', 0)
    if label in ("Bet", "Raise"):
        min_target = p.current_bet + to_call + BIG_BLIND
        max_target = p.current_bet + p.stack
        if min_target > max_target:
            min_target = max_target
        amount = prompt_raise_amount(min_target, max_target)
        if amount is None:
            return ('call', 0) if to_call > 0 else ('check', 0)
        return ('raise', amount)
    return ('allin', p.current_bet + p.stack)


def bot_decide_action(p, to_call, board, pot):
    strength = estimate_strength(p.hole, board)
    thresholds = PERSONALITIES[p.personality]
    bluffing = random.random() < thresholds['bluff']
    effective = 1.0 if bluffing else strength
    current_max_bet = p.current_bet + to_call

    if to_call <= 0:
        if effective >= thresholds['raise']:
            bet_size = max(BIG_BLIND, int(pot * random.uniform(0.5, 1.0)))
            target = min(p.current_bet + p.stack, p.current_bet + bet_size)
            if target > p.current_bet:
                return ('raise', target)
        return ('check', 0)

    pot_odds = to_call / (pot + to_call)
    if effective < thresholds['fold'] and effective < pot_odds:
        return ('fold', 0)
    if effective >= thresholds['raise']:
        raise_size = max(BIG_BLIND, int(pot * random.uniform(0.5, 1.0)))
        target = min(p.current_bet + p.stack, current_max_bet + raise_size)
        if target > current_max_bet:
            return ('raise', target)
    return ('call', 0)


def render_board(board):
    if not board:
        print(ui.DIM + "(no community cards yet)" + ui.RESET)
    else:
        ui.render_cards(board)


def show_state(players, board, human_idx=0, highlight_idx=None, to_call=None):
    ui.clear()
    pot = sum(p.total_committed for p in players)
    print(ui.gold(f"\n=== POT: {pot} pts ==="))
    print(ui.gold("Board:"))
    render_board(board)
    for i, p in enumerate(players):
        tag = " (you)" if i == human_idx else ""
        if p.folded:
            state = "FOLDED"
        elif p.all_in:
            state = "ALL-IN"
        else:
            state = f"bet {p.current_bet}"
        marker = " <--" if highlight_idx == i else ""
        print(f"{p.name}{tag}: stack {p.stack}, {state}{marker}")
    print(ui.gold("\nYour hole cards:"))
    ui.render_cards(players[human_idx].hole)
    if to_call:
        print(f"To call: {to_call} pts")


def betting_round(players, order, board, human_idx=0):
    active = [i for i in order if not players[i].folded and not players[i].all_in]
    if len(active) <= 1:
        return
    current_max_bet = max((players[i].current_bet for i in range(len(players)) if not players[i].folded), default=0)
    to_act = list(active)

    while to_act:
        i = to_act.pop(0)
        p = players[i]
        if p.folded or p.all_in:
            continue
        to_call = current_max_bet - p.current_bet
        pot = sum(pl.total_committed for pl in players)

        if not p.is_bot:
            show_state(players, board, human_idx=human_idx, highlight_idx=i, to_call=to_call)
            action, amount = human_decide_action(p, to_call)
        else:
            action, amount = bot_decide_action(p, to_call, board, pot)

        current_max_bet, raised = apply_action(p, action, amount, current_max_bet)

        if p.is_bot:
            if action == 'fold':
                print(f"{p.name} folds.")
            elif action == 'check':
                print(f"{p.name} checks.")
            elif action == 'call':
                print(f"{p.name} calls.")
            elif action == 'raise':
                print(f"{p.name} raises to {amount}.")
            elif action == 'allin':
                print(f"{p.name} goes all-in ({amount} pts)!")

        if raised:
            to_act = [j for j in active if j != i and not players[j].folded and not players[j].all_in]
        if sum(1 for pl in players if not pl.folded) <= 1:
            break


# ---------- Pots and showdown ----------

def build_pots(players):
    contributions = [(p, p.total_committed) for p in players]
    levels = sorted({c for _, c in contributions if c > 0})
    pots = []
    prev = 0
    for level in levels:
        slice_amount = sum(max(0, min(c, level) - prev) for _, c in contributions)
        eligible = [p for p, c in contributions if c >= level and not p.folded]
        if slice_amount > 0 and eligible:
            pots.append({'amount': slice_amount, 'eligible': eligible})
        prev = level
    return pots


def award_pot_all_folded(players, stats, human_idx=0):
    winner = next(p for p in players if not p.folded)
    pot = sum(p.total_committed for p in players)
    winner.stack += pot
    print(f"\n{winner.name} wins the pot ({pot} pts) -- everyone else folded.")
    human = players[human_idx]
    human_won = pot if winner is human else 0
    stats.record('poker', wagered=human.total_committed, won=human_won)


def showdown(players, board, stats, human_idx=0):
    contenders = [p for p in players if not p.folded]
    pots = build_pots(players)
    human = players[human_idx]
    human_won_total = 0

    print(ui.gold("\n-- Showdown --"))
    for p in contenders:
        score, _ = best_hand(p.hole + board)
        p.showdown_score = score
        print(f"{p.name}: {ui.cards_str(p.hole)}  ->  {HAND_NAMES[score[0]]}")

    for pot in pots:
        eligible = pot['eligible']
        best_score = max(p.showdown_score for p in eligible)
        winners = [p for p in eligible if p.showdown_score == best_score]
        share = pot['amount'] // len(winners)
        remainder = pot['amount'] - share * len(winners)
        for idx, w in enumerate(winners):
            amt = share + (remainder if idx == 0 else 0)
            w.stack += amt
            if w is human:
                human_won_total += amt
        names = ", ".join(w.name for w in winners)
        print(f"Pot of {pot['amount']} pts -> {names} ({HAND_NAMES[best_score[0]]})")

    stats.record('poker', wagered=human.total_committed, won=human_won_total)


# ---------- Hand and session loop ----------

def play_hand(players, button_idx, stats, human_idx=0):
    for p in players:
        p.reset_for_hand()

    deck = cards.new_deck()
    for p in players:
        p.hole = [deck.pop(), deck.pop()]

    n = len(players)
    sb_idx = (button_idx + 1) % n
    bb_idx = (button_idx + 2) % n
    for idx, amt in ((sb_idx, SMALL_BLIND), (bb_idx, BIG_BLIND)):
        pay = min(amt, players[idx].stack)
        players[idx].stack -= pay
        players[idx].current_bet += pay
        players[idx].total_committed += pay
        if players[idx].stack == 0:
            players[idx].all_in = True

    board = []

    first_to_act = (bb_idx + 1) % n
    preflop_order = [(first_to_act + i) % n for i in range(n)]
    betting_round(players, preflop_order, board, human_idx=human_idx)

    postflop_order = [(sb_idx + i) % n for i in range(n)]

    if sum(1 for p in players if not p.folded) > 1:
        deck.pop()  # burn
        board.extend([deck.pop() for _ in range(3)])  # flop
        betting_round(players, postflop_order, board, human_idx=human_idx)

    if sum(1 for p in players if not p.folded) > 1:
        deck.pop()  # burn
        board.append(deck.pop())  # turn
        betting_round(players, postflop_order, board, human_idx=human_idx)

    if sum(1 for p in players if not p.folded) > 1:
        deck.pop()  # burn
        board.append(deck.pop())  # river
        betting_round(players, postflop_order, board, human_idx=human_idx)

    ui.clear()
    print(ui.gold("Final board:"))
    render_board(board)

    if sum(1 for p in players if not p.folded) <= 1:
        award_pot_all_folded(players, stats, human_idx=human_idx)
    else:
        showdown(players, board, stats, human_idx=human_idx)

    for i, p in enumerate(players):
        tag = " (you)" if i == human_idx else ""
        print(f"{p.name}{tag}: stack {p.stack}")


def play(bankroll, stats, save_callback):
    if bankroll.is_broke():
        ui.failure("You're out of points!")
        return

    ui.clear()
    ui.header(bankroll)
    ui.info("Welcome to the poker table! Buy in with points to get chips.")
    buy_in = ui.prompt_bet(bankroll.balance, min_bet=BIG_BLIND * 2, label="poker buy-in")
    if buy_in is None:
        return

    bankroll.withdraw(buy_in)
    save_callback()

    players = [
        Player("You", buy_in, is_bot=False),
        Player("Tex", buy_in, is_bot=True, personality='TAG'),
        Player("Lucy", buy_in, is_bot=True, personality='LAG'),
        Player("Cal", buy_in, is_bot=True, personality='Station'),
    ]
    button_idx = 0

    while True:
        for p in players:
            if p.is_bot and p.stack <= 0:
                p.stack = buy_in  # house rebuy keeps the table full

        play_hand(players, button_idx, stats, human_idx=0)
        save_callback()
        button_idx = (button_idx + 1) % len(players)

        human = players[0]
        if human.stack <= 0:
            ui.failure("\nYou're out of chips at the table!")
            ui.pause()
            break

        if not ui.prompt_yes_no("\nPlay another hand? (No cashes out)"):
            break

    payout = players[0].stack
    if payout > 0:
        bankroll.deposit(payout)
        ui.success(f"\nYou leave the table with {payout} pts, added to your balance.")
    else:
        ui.failure("\nYou leave the table with nothing.")
    save_callback()
