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
