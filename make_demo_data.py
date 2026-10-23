"""Generate a synthetic bank statement for demos and tests.

Nothing here is real data. Six months of everyday spending for one person in
Tbilisi, in GEL, with a few planted anomalies so the detector has something
to find. Ground-truth categories are written to a separate file so the
categorizer can be scored honestly.

    python make_demo_data.py            # writes demo/statement.csv + demo/truth.csv
"""
import csv
import os
import random
from datetime import date, timedelta

random.seed(7)

# merchant -> (category, typical amount, spread, visits per month)
MERCHANTS = {
    "CARREFOUR TBILISI MALL": ("Groceries", 85, 30, 6),
    "SPAR #114 VAKE": ("Groceries", 32, 12, 8),
    "NIKORA 2 SABURTALO": ("Groceries", 24, 9, 7),
    "AGROHUB MARKET": ("Groceries", 60, 20, 2),
    "BOLT.EU/O/2610": ("Transport", 9, 4, 10),
    "YANDEX GO TBILISI": ("Transport", 11, 5, 4),
    "METROMONEY TOPUP": ("Transport", 20, 0, 1),
    "WISSOL PETROL #31": ("Transport", 120, 25, 1),
    "COFFEESTA VAKE": ("Eating out", 12, 4, 6),
    "STAMBA HOTEL CAFE": ("Eating out", 48, 15, 2),
    "WOLT TBILISI": ("Eating out", 38, 12, 5),
    "GLOVO*ORDER": ("Eating out", 31, 10, 3),
    "MAGTICOM MOBILE": ("Bills & utilities", 25, 0, 1),
    "SILKNET INTERNET": ("Bills & utilities", 59, 0, 1),
    "TELASI ELECTRICITY": ("Bills & utilities", 70, 25, 1),
    "TBILISI ENERGY GAS": ("Bills & utilities", 45, 30, 1),
    "GWP WATER": ("Bills & utilities", 14, 3, 1),
    "NETFLIX.COM": ("Subscriptions", 30, 0, 1),
    "SPOTIFY P2A1": ("Subscriptions", 16, 0, 1),
    "OPENAI *CHATGPT SUBSCR": ("Subscriptions", 55, 0, 1),
    "ICLOUD STORAGE APPLE": ("Subscriptions", 8, 0, 1),
    "PSP PHARMACY 77": ("Health", 22, 10, 2),
    "AVERSI PHARMA": ("Health", 18, 8, 1),
    "GORGIA HYPERMARKET": ("Home", 75, 40, 1),
    "IKEA TBILISI": ("Home", 140, 60, 0.3),
    "ZARA EAST POINT": ("Shopping", 120, 50, 0.6),
    "ALIEXPRESS.COM": ("Shopping", 35, 20, 1.5),
    "CINEMA AMIRANI": ("Entertainment", 24, 6, 1),
    "BILETEBI.GE TICKETS": ("Entertainment", 60, 25, 0.5),
    "WORLD CLASS FITNESS": ("Health", 150, 0, 1),
}

ANOMALIES = [
    # (month offset from start, day, merchant, amount, why)
    (5, 9, "WOLT TBILISI", 410.0, "10x a usual food order"),
    (5, 14, "NETFLIX.COM", 30.0, "charged twice in one month"),
    (5, 21, "UNKNOWN MERCHANT 8841 LTD", 265.0, "merchant never seen before"),
    (4, 3, "TELASI ELECTRICITY", 260.0, "electricity bill 3-4x normal"),
]


def month_start(d, k):
    m = d.month - 1 + k
    return date(d.year + m // 12, m % 12 + 1, 1)


def main(out_dir="demo"):
    os.makedirs(out_dir, exist_ok=True)
    start = date(2026, 5, 1)
    rows = []
    for k in range(6):
        ms = month_start(start, k)
        days = (month_start(start, k + 1) - ms).days
        last_day = 23 if k == 5 else days  # current month is in progress
        for name, (cat, mu, sd, visits) in MERCHANTS.items():
            v = visits * last_day / days  # fewer visits in a month that is still in progress
            n = v if v >= 1 else (1 if random.random() < v else 0)
            n = max(0, int(round(random.gauss(n, n * 0.25)))) if n > 1 else int(n)
            for _ in range(n):
                day = random.randint(1, last_day)
                amt = round(max(1.0, random.gauss(mu, sd)) if sd else mu, 2)
                rows.append((ms + timedelta(days=day - 1), name, amt, cat))
    for k, day, name, amt, _ in ANOMALIES:
        cat = MERCHANTS.get(name, ("Other",))[0]
        rows.append((month_start(start, k) + timedelta(days=day - 1), name, amt, cat))
    rows.sort()
    with open(os.path.join(out_dir, "statement.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Description", "Amount", "Currency"])
        for d, name, amt, _ in rows:
            w.writerow([d.isoformat(), name, f"-{amt:.2f}", "GEL"])
    with open(os.path.join(out_dir, "truth.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Description", "Category"])
        for name in sorted({r[1] for r in rows}):
            w.writerow([name, MERCHANTS.get(name, ("Other",))[0]])
    print(f"{len(rows)} transactions -> {out_dir}/statement.csv")


if __name__ == "__main__":
    main()
