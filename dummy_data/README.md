# Dummy client book (synthetic, not real data)

Every company, person, CIF, trade number and price here is **made up**. The spot levels are rough anchors chosen
so that strikes look believable. They are not market data, so never quote them.

Regenerate with:

```bash
python -m app.clientdata.generate
```

The script uses a fixed seed (`--seed 42`), so everyone gets the same book. It writes these CSVs plus
`data/clientdata/clientdata.db` (SQLite, git-ignored). The table definitions are in `app/clientdata/schema.py`.

| File | What it holds |
|---|---|
| `clients.csv` | 12 counterparts: segment, industry, hedging profile, preferred pairs, RM and RM team L1–L5 |
| `contacts.csv` | People at each client. Includes three "Jimmy"s at different clients, for testing ambiguous names |
| `trades.csv` | ~360 FX spot, forward, swap-leg and option rows using the 82 sales/Murex export columns, in export order |
| `interactions.csv` | Seeded past client queries, Sep–Nov 2026: the start of the query database |

Trades run from 4 May to 5 Nov 2026 (the research corpus end date). LIVE trades expire after 5 Nov 2026, so some
fall inside the Dec-26 / 2027 forecast horizons. "Meridian Foods Holdings" and "Meridian Food Industries" are
deliberately similar names.

## Pattern test clients (T01-T04) and demo mode

`dummy_data/patterns/` holds four extra clients built to exercise the client-box trade ideas. Its files are
`patterns_clients.csv`, `patterns_contacts.csv`, `patterns_trades.csv` (same export headers as `trades.csv` above)
and `patterns_interactions.csv`.
They are **separate from the 12 clients above**. Those 12 are never date-shifted and never changed.

**Dates are relative to today.** Every date in these files is written as an offset from the day you run the
app: `T-45` is 45 days ago, `T+6` is 6 days from now, `T+0` is today. Interaction times look like
`T-45 14:32`. When the app loads the files, it resolves the offsets against today (SGT). A trade or maturity date that lands on a
Saturday or Sunday moves to the next Monday. The trade
status is **not stored**: LIVE or DEAD is computed from the resolved maturity, so maturities stay upcoming
whenever you run it.

**Demo mode.** Use the "Demo mode: OFF / ON" button at the top of the page.

* It is OFF every time `run.py` starts. While it's OFF, T01-T04 don't exist: they're not identified and show
  no trades or ideas.
* While it's ON, they behave like any other client, and a banner shows that demo mode is on.
* It isn't available on the hosted demo (`RA_PUBLIC_MODE=1`).
* The app **never writes to `dummy_data/`**. Everything you save, including asks logged about T01-T04, goes
  to `data/clientdata/clientdata.db` as usual. Saved asks are hidden while demo mode is off and count again
  when it's back on.

| Client | Pattern |
|---|---|
| T01 Aurora Shipping Pte Ltd (Daniel Koh) | Monthly SELL USD/SGD 3M forwards (~USD 5m); a forward maturing in a few days; two maturities rolled with same-size swaps |
| T02 Bluewater Electronics Pte Ltd (Priya Nair) | Quarterly SELL USD/JPY 6M forwards (~USD 12m); newest ~3x the usual size; USD/SGD asks usually followed by a JPY/SGD ask |
| T03 Cendana Resources Sdn Bhd (Ahmad Faiz) | USD/INR NDFs: four BUYs then a SELL; USD/KRW NDFs: one fixing within a week and an offsetting BUY/SELL pair |
| T04 Dovetail Foods Pte Ltd (Mei Ling Chua) | Control: irregular USD/SGD trades and sizes, no rolls, two asks. It should trigger no ideas |

`app/clientdata/patterns.py` is the tool that created these files. To regenerate them, which overwrites the
folder, run:

```bash
python -m app.clientdata.patterns --write
```
