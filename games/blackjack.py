"""Blackjack: 6-deck shoe, dealer stands on all 17s, splitting up to 3 times,
double down, insurance, and a 5-Card Charlie auto-win rule."""
import cards
import ui

MAX_SPLITS = 3  # up to 4 hands total


def hand_value(hand_cards):
    """Returns (total, is_soft) for a list of Cards, aces counted flexibly."""
    total = sum(c.blackjack_value for c in hand_cards)
    aces = sum(1 for c in hand_cards if c.rank == 'A')
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


class Hand:
    def __init__(self, hand_cards, bet, from_split_aces=False):
        self.cards = hand_cards
        self.bet = bet
        self.doubled = False
        self.from_split_aces = from_split_aces
        self.stood = False
        self.busted = False
        self.result = None  # 'blackjack', 'charlie', or None (resolved vs dealer later)

    @property
    def value(self):
        return hand_value(self.cards)[0]

    @property
    def is_soft(self):
        return hand_value(self.cards)[1]

    @property
    def is_natural_blackjack(self):
        return len(self.cards) == 2 and self.value == 21 and not self.from_split_aces

    def describe(self):
        soft = "soft " if self.is_soft and self.value != 21 else ""
        return f"{soft}{self.value}"


def dealer_should_hit(dealer_cards):
    value, _ = hand_value(dealer_cards)
    return value < 17  # stands on all 17s, including soft 17


def show_table(bankroll, dealer_cards, hands, active_index=None, reveal_dealer=False):
    ui.clear()
    ui.header(bankroll)
    print(ui.gold("\n-- Dealer --"))
    ui.render_cards(dealer_cards, hide_first=not reveal_dealer)
    if reveal_dealer:
        value, soft = hand_value(dealer_cards)
        print(f"Dealer total: {value}{' (soft)' if soft else ''}")
    for i, h in enumerate(hands):
        label = f"-- Your Hand {i + 1}/{len(hands)} --" if len(hands) > 1 else "-- Your Hand --"
        marker = " <--" if active_index == i else ""
        print(ui.gold(f"\n{label}{marker}"))
        ui.render_cards(h.cards)
        status = f"Total: {h.describe()}  |  Bet: {h.bet}"
        if h.busted:
            status += "  " + ui.RED + "BUST" + ui.RESET
        print(status)


def deal_initial(shoe, bet):
    player_cards = [shoe.deal(), shoe.deal()]
    dealer_cards = [shoe.deal(), shoe.deal()]  # index 0 = hole card, index 1 = up card
    return Hand(player_cards, bet), dealer_cards


def offer_insurance(bankroll, dealer_cards, bet):
    if dealer_cards[1].rank != 'A':
        return 0
    insurance_cost = bet // 2
    if insurance_cost <= 0 or not bankroll.can_afford(insurance_cost):
        return 0
    if ui.prompt_yes_no(f"Dealer shows an Ace. Buy insurance for {insurance_cost} pts?"):
        bankroll.withdraw(insurance_cost)
        return insurance_cost
    return 0


def player_turn(hands, shoe, bankroll, dealer_cards, split_count):
    i = 0
    while i < len(hands):
        hand = hands[i]
        if hand.from_split_aces or hand.is_natural_blackjack:
            i += 1
            continue
        while True:
            value, _ = hand_value(hand.cards)
            if value > 21:
                hand.busted = True
                break
            if len(hand.cards) >= 5:
                hand.result = 'charlie'
                hand.stood = True
                break

            options = ["Hit", "Stand"]
            can_double = len(hand.cards) == 2 and bankroll.can_afford(hand.bet)
            can_split = (len(hand.cards) == 2 and hand.cards[0].rank == hand.cards[1].rank
                         and split_count[0] < MAX_SPLITS and bankroll.can_afford(hand.bet))
            if can_double:
                options.append("Double Down")
            if can_split:
                options.append("Split")

            show_table(bankroll, dealer_cards, hands, active_index=i)
            choice = ui.menu("Your move", options)
            action = options[choice - 1]

            if action == "Hit":
                hand.cards.append(shoe.deal())
                continue
            if action == "Stand":
                hand.stood = True
                break
            if action == "Double Down":
                bankroll.withdraw(hand.bet)
                hand.bet *= 2
                hand.doubled = True
                hand.cards.append(shoe.deal())
                hand.stood = True
                value, _ = hand_value(hand.cards)
                if value > 21:
                    hand.busted = True
                break
            if action == "Split":
                bankroll.withdraw(hand.bet)
                split_count[0] += 1
                is_ace_split = hand.cards[0].rank == 'A'
                first_card, second_card = hand.cards[0], hand.cards[1]
                hand.cards = [first_card, shoe.deal()]
                hand.from_split_aces = is_ace_split
                new_hand = Hand([second_card, shoe.deal()], hand.bet, from_split_aces=is_ace_split)
                hands.insert(i + 1, new_hand)
                if is_ace_split:
                    break  # split aces get exactly one card, no further action
                continue
        i += 1


def resolve_round(bankroll, stats, hands, dealer_cards, insurance_bet, dealer_had_blackjack):
    wagered = sum(h.bet for h in hands) + insurance_bet
    returned = 0

    if insurance_bet:
        if dealer_had_blackjack:
            returned += insurance_bet * 3  # stake back + 2:1 payout

    dealer_value, _ = hand_value(dealer_cards)
    dealer_busted = dealer_value > 21

    for h in hands:
        if h.is_natural_blackjack:
            if dealer_had_blackjack:
                returned += h.bet  # push
            else:
                returned += h.bet + (h.bet * 3 // 2)
        elif h.busted:
            pass  # bet already forfeited
        elif h.result == 'charlie':
            returned += h.bet * 2
        elif dealer_busted or h.value > dealer_value:
            returned += h.bet * 2
        elif h.value == dealer_value:
            returned += h.bet
        # else: lose, nothing returned

    if returned:
        bankroll.deposit(returned)
    stats.record('blackjack', wagered=wagered, won=returned)


def play_round(bankroll, stats, shoe):
    ui.clear()
    ui.header(bankroll)
    bet = ui.prompt_bet(bankroll.balance, min_bet=1, label="blackjack bet")
    if bet is None:
        return False

    bankroll.withdraw(bet)
    hand, dealer_cards = deal_initial(shoe, bet)
    hands = [hand]

    show_table(bankroll, dealer_cards, hands)
    insurance_bet = offer_insurance(bankroll, dealer_cards, bet)

    dealer_had_blackjack = False
    upcard = dealer_cards[1]
    dealer_could_have_blackjack = upcard.rank == 'A' or upcard.blackjack_value == 10
    if dealer_could_have_blackjack:
        dealer_value, _ = hand_value(dealer_cards)
        dealer_had_blackjack = dealer_value == 21

    if dealer_had_blackjack:
        show_table(bankroll, dealer_cards, hands, reveal_dealer=True)
        ui.info("Dealer has blackjack!")
    elif hand.is_natural_blackjack:
        show_table(bankroll, dealer_cards, hands, reveal_dealer=True)
        ui.success("Blackjack! You win!")
    else:
        split_count = [0]
        player_turn(hands, shoe, bankroll, dealer_cards, split_count)

        any_live = any(not h.busted and h.result != 'charlie' for h in hands)
        show_table(bankroll, dealer_cards, hands, reveal_dealer=True)
        if any_live:
            while dealer_should_hit(dealer_cards):
                dealer_cards.append(shoe.deal())
            show_table(bankroll, dealer_cards, hands, reveal_dealer=True)

    resolve_round(bankroll, stats, hands, dealer_cards, insurance_bet, dealer_had_blackjack)

    for i, h in enumerate(hands):
        label = f"Hand {i + 1}: " if len(hands) > 1 else ""
        if h.is_natural_blackjack and not dealer_had_blackjack:
            ui.success(f"{label}Blackjack! +{h.bet * 3 // 2} pts")
        elif h.result == 'charlie':
            ui.success(f"{label}5-Card Charlie! Auto-win! +{h.bet} pts")
        elif h.busted:
            ui.failure(f"{label}Bust. -{h.bet} pts")
        else:
            dealer_value, _ = hand_value(dealer_cards)
            dealer_busted = dealer_value > 21
            if dealer_busted or h.value > dealer_value:
                ui.success(f"{label}Win! +{h.bet} pts")
            elif h.value == dealer_value:
                ui.info(f"{label}Push.")
            else:
                ui.failure(f"{label}Lose. -{h.bet} pts")

    ui.header(bankroll)
    return True


def play(bankroll, stats, save_callback):
    shoe = cards.Shoe(6)
    while True:
        if bankroll.is_broke():
            ui.failure("You're out of points!")
            return
        played = play_round(bankroll, stats, shoe)
        save_callback()
        if not played:
            return
        if bankroll.is_broke():
            ui.failure("You've busted out of points!")
            ui.pause()
            return
        if not ui.prompt_yes_no("\nPlay another hand?"):
            return
