#!/usr/bin/env python3
"""lazy-ledger: turn a raw bank-statement CSV into a one-page monthly money
report, fully offline, with Gemma running locally.

    python ledger.py demo/statement.csv
    python ledger.py my_statement.csv --month 2026-10 --model models/gemma3-4b.gguf

What it does, in order:
  1. Reads the CSV (Date, Description, Amount[, Currency]); column names are matched loosely.
  2. Labels every new merchant with Gemma (local, via llama.cpp). Labels are cached in
     merchants.json, so next month only genuinely new merchants hit the model, and you can
     fix a wrong label once by editing that file.
  3. Flags things worth a second look with plain statistics (no model needed):
     unusually large charges for a merchant, merchants never seen before, and
     subscriptions billed more than once in a month.
  4. Projects the current month's total from the days elapsed so far.
  5. Asks Gemma for a short plain-language summary and writes report.md.

Nothing leaves the machine. No API keys.
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime

CATEGORIES = [
    "Groceries", "Eating out", "Transport", "Bills & utilities", "Subscriptions",
    "Health", "Home", "Shopping", "Entertainment", "Income", "Transfers", "Other",
]
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- reading ----------

def _pick(header, *names):
    low = {h.lower().strip(): h for h in header}
    for n in names:
        for k, v in low.items():
            if n in k:
                return v
    return None


def parse_amount(s):
    s = (s or "").replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    s = s.replace(",", "")
    return float(re.sub(r"[^0-9.\-]", "", s) or 0)


def parse_date(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date: {s!r}")


def read_statement(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("empty statement")
    h = rows[0].keys()
    c_date = _pick(h, "date", "дата", "თარიღი")
    c_desc = _pick(h, "description", "merchant", "details", "назнач", "описан", "დანიშნულება")
    c_amt = _pick(h, "amount", "сумма", "თანხა")
    c_cur = _pick(h, "currency", "валют", "ვალუტა")
    if not (c_date and c_desc and c_amt):
        sys.exit(f"could not find date/description/amount columns in {list(h)}")
    tx = []
    for r in rows:
        tx.append({
            "date": parse_date(r[c_date]),
            "desc": " ".join(r[c_desc].split()).upper(),
            "amount": parse_amount(r[c_amt]),
            "cur": (r.get(c_cur) or "").strip() if c_cur else "",
        })
    return tx


# ---------- the model ----------

class Gemma:
    def __init__(self, model_path, threads=None):
        from llama_cpp import Llama  # imported lazily so --no-llm works without it
        self.llm = Llama(model_path=model_path, n_ctx=4096, verbose=False,
                         n_threads=threads or max(1, (os.cpu_count() or 2)))

    def chat(self, prompt, max_tokens=512, json_mode=False):
        kw = {"response_format": {"type": "json_object"}} if json_mode else {}
        r = self.llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens, temperature=0, **kw)
        return r["choices"][0]["message"]["content"].strip()


def label_merchants(names, gemma, batch=6):
    out = {}
    for i in range(0, len(names), batch):
        chunk = names[i:i + batch]
        prompt = (
            "You label bank-statement merchant strings for a person living in Tbilisi, Georgia.\n"
            f"Allowed categories: {', '.join(CATEGORIES)}.\n"
            "Ticket sellers, cinemas and concerts are Entertainment. Taxi apps (Bolt, Yandex Go), fuel and metro are Transport. "
            "Food delivery (Wolt, Glovo) and cafes are Eating out. Supermarket chains (Nikora, Spar, Carrefour, Agrohub) are Groceries. "
            "Furniture and hardware stores (IKEA, Gorgia) are Home.\n"
            "Reply with JSON only: an object mapping each merchant string, exactly as given, to one category.\n\n"
            "Merchants:\n" + "\n".join(f"- {n}" for n in chunk))
        try:
            got = json.loads(gemma.chat(prompt, max_tokens=60 * len(chunk), json_mode=True))
        except (json.JSONDecodeError, ValueError):
            got = {}
        for n in chunk:
            c = got.get(n)
            out[n] = c if c in CATEGORIES else "Other"
    return out


# ---------- analysis ----------

def month_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def find_flags(tx, month):
    """Plain-statistics checks. Returns a list of (transaction, reason)."""
    history = [t for t in tx if month_key(t["date"]) < month and t["amount"] < 0]
    current = [t for t in tx if month_key(t["date"]) == month and t["amount"] < 0]
    by_merchant = defaultdict(list)
    for t in history:
        by_merchant[t["desc"]].append(-t["amount"])
    flags = []
    for t in current:
        past = by_merchant.get(t["desc"], [])
        amt = -t["amount"]
        if not past:
            flags.append((t, "first time you've paid this merchant"))
            continue
        med = statistics.median(past)
        mad = statistics.median([abs(x - med) for x in past]) or max(1.0, 0.1 * med)
        if amt > med * 2.5 and (amt - med) / mad > 6:
            flags.append((t, f"{amt / med:.1f}x your usual {med:.0f} here"))
    subs = defaultdict(list)
    for t in current:
        if t["cat"] == "Subscriptions":
            subs[t["desc"]].append(t)
    for name, ts in subs.items():
        if len(ts) > 1:
            for t in ts[1:]:
                flags.append((t, f"{name} billed {len(ts)} times this month"))
    return flags


def summarise(tx, month):
    spend = defaultdict(lambda: defaultdict(float))
    for t in tx:
        if t["amount"] < 0 and t["cat"] not in ("Transfers", "Income"):
            spend[month_key(t["date"])][t["cat"]] += -t["amount"]
    past_months = sorted(m for m in spend if m < month)[-3:]
    rows = []
    for cat in CATEGORIES:
        now = spend[month].get(cat, 0.0)
        avg = statistics.mean([spend[m].get(cat, 0.0) for m in past_months]) if past_months else 0.0
        if now or avg:
            rows.append((cat, now, avg))
    rows.sort(key=lambda r: -r[1])
    return rows, past_months


def projection(tx, month):
    days = [t["date"] for t in tx if month_key(t["date"]) == month]
    if not days:
        return None
    last = max(days)
    y, m = map(int, month.split("-"))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    in_month = (nxt - date(y, m, 1)).days
    so_far = sum(-t["amount"] for t in tx if month_key(t["date"]) == month
                 and t["amount"] < 0 and t["cat"] not in ("Transfers", "Income"))
    if last.day >= in_month:
        return so_far, so_far, in_month, in_month
    return so_far, so_far / last.day * in_month, last.day, in_month


def key_facts(rows, flags, proj, cur):
    """The summary's content is computed here, not by the model."""
    facts = []
    if proj and proj[2] < proj[3]:
        facts.append(f"You have spent {proj[0]:,.0f} {cur} in the first {proj[2]} days and are on pace for about {proj[1]:,.0f} {cur}.")
    moved = [(c, n, v) for c, n, v in rows if v >= 50]
    if moved:
        c, n, v = max(moved, key=lambda r: abs(r[1] - r[2]))
        word = "up" if n > v else "down"
        facts.append(f"The biggest change is {c}: {n:,.0f} {cur}, {word} from a usual {v:,.0f} {cur}.")
    if flags:
        t, why = max(flags, key=lambda f: -f[0]["amount"])
        facts.append(f"Worth checking: {t['desc']} for {-t['amount']:,.0f} {cur} ({why}).")
    return facts


def numbers_ok(text, source):
    """Every number the model wrote must appear in the facts it was given."""
    norm = lambda x: x.replace(",", "")
    allowed = set(norm(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", source))
    return all(norm(n) in allowed for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text))


# ---------- report ----------

def write_report(path, month, cur, rows, past, flags, proj, summary, stats):
    L = [f"# Money report — {month}", ""]
    if summary:
        L += [summary, ""]
    if proj:
        so_far, full, d, n = proj
        if d < n:
            L += [f"**Spent so far:** {so_far:,.0f} {cur} in {d} of {n} days. "
                  f"**On pace for:** ~{full:,.0f} {cur} by month end.", ""]
        else:
            L += [f"**Spent this month:** {so_far:,.0f} {cur}.", ""]
    L += [f"## Where it went (vs. average of {', '.join(past) or 'no history'})", "",
          f"| Category | {month} | 3-month avg | Change |", "|---|---:|---:|---:|"]
    for cat, now, avg in rows:
        ch = f"{(now - avg) / avg * 100:+.0f}%" if avg else "new"
        L.append(f"| {cat} | {now:,.0f} | {avg:,.0f} | {ch} |")
    L += ["", "## Worth a second look", ""]
    if flags:
        for t, why in sorted(flags, key=lambda f: f[0]["date"]):
            L.append(f"- {t['date']:%d %b} · **{t['desc']}** · {-t['amount']:,.2f} {cur} — {why}")
    else:
        L.append("Nothing unusual this month.")
    L += ["", "---", f"Generated offline by lazy-ledger · {stats}"]
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("statement")
    ap.add_argument("--month", help="YYYY-MM (default: latest month in the file)")
    ap.add_argument("--model", default=os.path.join(HERE, "models", "gemma3-4b.gguf"))
    ap.add_argument("--cache", default=os.path.join(HERE, "merchants.json"))
    ap.add_argument("--out", default="report.md")
    ap.add_argument("--no-llm", action="store_true", help="skip Gemma; unknown merchants become Other")
    a = ap.parse_args()

    t0 = time.time()
    tx = read_statement(a.statement)
    month = a.month or max(month_key(t["date"]) for t in tx)
    cur = next((t["cur"] for t in tx if t["cur"]), "")

    cache = json.load(open(a.cache)) if os.path.exists(a.cache) else {}
    new = sorted({t["desc"] for t in tx} - set(cache))
    gemma = None
    labelled = 0
    if new and not a.no_llm:
        print(f"labelling {len(new)} new merchants with Gemma (cached: {len(cache)})…", file=sys.stderr)
        gemma = Gemma(a.model)
        cache.update(label_merchants(new, gemma))
        labelled = len(new)
        json.dump(cache, open(a.cache, "w"), indent=1, ensure_ascii=False, sort_keys=True)
    for t in tx:
        t["cat"] = cache.get(t["desc"], "Other")

    rows, past = summarise(tx, month)
    flags = find_flags(tx, month)
    proj = projection(tx, month)

    facts = key_facts(rows, flags, proj, cur)
    summary = " ".join(facts)
    if not a.no_llm and facts:
        gemma = gemma or Gemma(a.model)
        draft = gemma.chat(
            "You write the opening lines of a personal monthly spending report. Tone: calm, neutral, "
            "like a careful accountant talking to a friend. Do not praise or judge spending. "
            "Rewrite the facts below as 2-3 plain sentences addressed to the reader as \"you\". "
            "Keep every number exactly as written; add no new numbers, facts or advice. "
            "Output only the sentences, with no introduction.\n\n"
            "Example facts:\n- The biggest change is Transport: 80 USD, down from a usual 120 USD.\n"
            "Example output: Transport was the biggest shift this month: 80 USD against a usual 120 USD.\n\n"
            "Facts:\n" + "\n".join(f"- {f}" for f in facts), max_tokens=160)
        draft = "\n".join(l for l in draft.splitlines() if l.strip() and not l.rstrip().endswith(":")).strip()
        if numbers_ok(draft, " ".join(facts)):
            summary = draft
        else:
            print("Gemma's summary changed a number; using the plain version instead", file=sys.stderr)

    stats = f"{len(tx)} transactions, {labelled} new merchants labelled, {time.time() - t0:.0f}s"
    if a.no_llm and new:
        stats += f" (--no-llm: {len(new)} unlabelled merchants counted as Other)"
    write_report(a.out, month, cur, rows, past, flags, proj, summary, stats)
    print(f"wrote {a.out} ({stats})", file=sys.stderr)


if __name__ == "__main__":
    main()
