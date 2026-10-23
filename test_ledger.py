"""Model-free tests: python -m pytest -q"""
from datetime import date

import ledger


def tx(d, desc, amt, cat="Other"):
    return {"date": d, "desc": desc, "amount": amt, "cur": "GEL", "cat": cat}


def test_parse_amount_formats():
    assert ledger.parse_amount("-1 234.50") == -1234.5
    assert ledger.parse_amount("-12,5") == -12.5
    assert ledger.parse_amount("1,234.00") == 1234.0


def test_parse_date_formats():
    assert ledger.parse_date("2026-10-03") == date(2026, 10, 3)
    assert ledger.parse_date("03.10.2026") == date(2026, 10, 3)


def test_flags_spike_new_merchant_and_double_subscription():
    hist = [tx(date(2026, m, 5), "WOLT", -30 - m) for m in range(5, 10)]
    hist += [tx(date(2026, m, 1), "NETFLIX", -30, "Subscriptions") for m in range(5, 10)]
    now = [
        tx(date(2026, 10, 9), "WOLT", -400),
        tx(date(2026, 10, 10), "WOLT", -36),
        tx(date(2026, 10, 1), "NETFLIX", -30, "Subscriptions"),
        tx(date(2026, 10, 14), "NETFLIX", -30, "Subscriptions"),
        tx(date(2026, 10, 20), "NEW SHOP", -50),
    ]
    reasons = {(t["desc"], -t["amount"]): w for t, w in ledger.find_flags(hist + now, "2026-10")}
    assert ("WOLT", 400) in reasons
    assert ("WOLT", 36) not in reasons
    assert "billed 2 times" in reasons[("NETFLIX", 30)]
    assert "first time" in reasons[("NEW SHOP", 50)]


def test_numbers_guard():
    src = "You spent 2,947 GEL; usual 364 GEL."
    assert ledger.numbers_ok("You spent 2947 GEL against 364.", src)
    assert not ledger.numbers_ok("You spent 3,000 GEL.", src)


def test_projection_mid_month():
    t = [tx(date(2026, 10, 1), "A", -100), tx(date(2026, 10, 10), "A", -100)]
    so_far, full, d, n = ledger.projection(t, "2026-10")
    assert (so_far, d, n) == (200, 10, 31) and round(full) == 620
