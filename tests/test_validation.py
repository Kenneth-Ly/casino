from web.validation import validate_bet


def test_valid_bet_returns_amount_and_no_error():
    assert validate_bet("10", balance=50) == (10, None)


def test_non_numeric_bet_returns_error():
    amount, error = validate_bet("abc", balance=50)
    assert amount is None
    assert error is not None


def test_bet_above_balance_returns_error():
    amount, error = validate_bet("100", balance=50)
    assert amount is None
    assert error is not None


def test_bet_below_min_returns_error():
    amount, error = validate_bet("0", balance=50)
    assert amount is None
    assert error is not None


def test_negative_bet_returns_error():
    amount, error = validate_bet("-5", balance=50)
    assert amount is None
    assert error is not None


def test_blank_bet_returns_error():
    amount, error = validate_bet("", balance=50)
    assert amount is None
    assert error is not None
