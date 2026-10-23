# lazy-ledger

Drop in a bank-statement CSV, get back a one-page monthly money report. Runs fully offline with **Gemma 3** on your own machine: no cloud, no API keys, your transactions never leave your laptop.

![demo](demo/demo.gif)

The report tells you three things:

1. **Where the money went** this month, by category, against your 3-month average.
2. **What's worth a second look**: a charge far above what you usually pay that merchant, a merchant you've never paid before, a subscription billed twice.
3. **Where the month is heading**: spend so far and the pace to month end.

## Quick start

```bash
pip install -r requirements.txt
python fetch_model.py              # Gemma 3 4B, ~2.5 GB, one time
python make_demo_data.py           # synthetic statement, no real data
python ledger.py demo/statement.csv
cat report.md
```

With your own statement: export CSV from your bank and run `python ledger.py my_statement.csv`. Columns are matched loosely: any header containing *date*, *description/merchant/details* and *amount* works, in English, Russian or Georgian. Optional: `--month 2026-10`, `--model path/to.gguf`, `--no-llm`.

## How it works

| Step | Who does it | Why |
|---|---|---|
| Read CSV, normalise dates and amounts | Python | Deterministic |
| Label each **new** merchant with a category | Gemma 3 4B via llama.cpp, JSON mode, 6 merchants per call | Merchant strings like `BOLT.EU/O/2610` need world knowledge, not regex |
| Cache labels in `merchants.json` | Python | Next month only genuinely new merchants reach the model; fix a wrong label once by editing the file |
| Flag spikes, new merchants, double billing | Plain statistics (median and MAD per merchant) | Explainable, no model to hallucinate |
| Compute the summary facts | Python | Numbers come from code, not the model |
| Turn facts into 2–3 readable sentences | Gemma | Then a guard checks every number Gemma wrote is one it was given; if not, the plain version is used |

## Honest numbers (demo data, 2-core CPU, no GPU)

- Categorisation: 30 of 31 merchants correct against the generator's ground truth (`demo/truth.csv`). The miss: `GLOVO*ORDER` labelled Groceries instead of Eating out.
- First run: 154 s, all 31 merchants labelled. Next run: 29 s, 0 merchants sent to the model; the remaining time is loading Gemma and writing the summary.
- `--no-llm` runs in under a second and still produces the table, flags and pace.

The demo statement is synthetic (`make_demo_data.py`) and includes planted anomalies: a 410 GEL food order, a double Netflix charge, an unknown merchant.

## Tests

```bash
python -m pytest -q     # model-free: parsing, flags, projection, number guard
```

## Licence

Code: MIT. Gemma weights: [Gemma Terms of Use](https://ai.google.dev/gemma/terms).

Built with Claude as the coding agent.
