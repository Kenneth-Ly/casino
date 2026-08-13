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
