"""Per-game play statistics, persisted alongside the bankroll."""

DEFAULT_STATS = {
    "blackjack": {"plays": 0, "wagered": 0, "won": 0, "biggest_win": 0},
    "poker": {"plays": 0, "wagered": 0, "won": 0, "biggest_win": 0},
    "roulette": {"plays": 0, "wagered": 0, "won": 0, "biggest_win": 0},
    "slots": {"plays": 0, "wagered": 0, "won": 0, "biggest_win": 0, "jackpots": 0},
}

PLAY_LABEL = {
    "blackjack": "Hands",
    "poker": "Hands",
    "roulette": "Spins",
    "slots": "Spins",
}


class Stats:
    def __init__(self, data=None):
        self.data = {game: dict(vals) for game, vals in DEFAULT_STATS.items()}
        if data:
            for game, vals in data.items():
                if game in self.data:
                    self.data[game].update(vals)

    def record(self, game, wagered=0, won=0, jackpot=False):
        g = self.data[game]
        g["plays"] += 1
        g["wagered"] += wagered
        g["won"] += won
        if won > g["biggest_win"]:
            g["biggest_win"] = won
        if jackpot:
            g["jackpots"] = g.get("jackpots", 0) + 1

    def to_dict(self):
        return self.data
