"""Player point balance, all-time high score, and save-file persistence."""
import json
import os

SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'save_data.json')
STARTING_BALANCE = 50


class Bankroll:
    def __init__(self, balance=STARTING_BALANCE, high_score=STARTING_BALANCE):
        self.balance = balance
        self.high_score = max(high_score, balance)

    def can_afford(self, amount):
        return 0 < amount <= self.balance

    def withdraw(self, amount):
        if amount > self.balance:
            raise ValueError(f"Cannot withdraw {amount}, balance is only {self.balance}")
        self.balance -= amount

    def deposit(self, amount):
        self.balance += amount
        if self.balance > self.high_score:
            self.high_score = self.balance

    def is_broke(self):
        return self.balance <= 0

    def reset_after_bust(self, amount=STARTING_BALANCE):
        self.balance = amount

    def to_dict(self):
        return {"balance": self.balance, "high_score": self.high_score}


def load_state():
    """Returns (Bankroll, stats_dict). Falls back to fresh defaults if no save file exists."""
    if not os.path.exists(SAVE_FILE):
        return Bankroll(), {}
    try:
        with open(SAVE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return Bankroll(), {}
    bankroll = Bankroll(
        balance=data.get('balance', STARTING_BALANCE),
        high_score=data.get('high_score', STARTING_BALANCE),
    )
    return bankroll, data.get('stats', {})


def save_state(bankroll, stats):
    data = bankroll.to_dict()
    data['stats'] = stats.to_dict()
    with open(SAVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
