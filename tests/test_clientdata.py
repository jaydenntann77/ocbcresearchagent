import csv
import sqlite3

from app.clientdata import generate, schema


def test_trade_schema_matches_export_headers():
    assert len(schema.TRADE_COLUMNS) == 82
    assert len(set(schema.TRADE_FIELDS)) == 82
    assert schema.TRADE_HEADERS[0] == "Contract reference"
    assert schema.TRADE_HEADERS[-1] == "Replacement: Date"
    assert set(schema.AGENT_TRADE_FIELDS) <= set(schema.TRADE_FIELDS)


def test_generation_is_reproducible():
    a, b = generate.generate(seed=1, n_trades=50), generate.generate(seed=1, n_trades=50)
    assert a.trades == b.trades and a.clients == b.clients and a.interactions == b.interactions
    assert generate.generate(seed=2, n_trades=50).trades != a.trades


def test_book_is_internally_consistent():
    book = generate.generate()
    cifs = {c["sibs_cif"] for c in book.clients}
    client_ids = {c["client_id"] for c in book.clients}
    assert len(cifs) == len(book.clients)
    assert all(t["sibs_cif"] in cifs for t in book.trades)
    assert all(p["client_id"] in client_ids for p in book.contacts)
    assert all(i["client_id"] in client_ids for i in book.interactions)
    assert len({t["trn_internal"] for t in book.trades}) == len(book.trades)
    for t in book.trades:
        assert set(t) == set(schema.TRADE_FIELDS)
        assert t["trn_date"] <= generate.AS_OF.isoformat() <= "2027-12-31"
        assert t["expiry_date"] >= t["trn_date"]
        if t["status"] == "DEAD":
            assert t["expiry_date"] < generate.AS_OF.isoformat() and t["nfin_npv0"] == 0
        if t["status"] == "LIVE":
            assert t["expiry_date"] >= generate.AS_OF.isoformat()
        assert t["total_sales_credit_sgd"] >= 0
        anchor = generate.PAIRS[t["ccy1"] + t["ccy2"]][0]
        assert abs(t["initial_price"] / anchor - 1) < 0.15
    swap_legs = [t for t in book.trades if t["trn_type"] == "SWLEG"]
    assert swap_legs and all(t["package_ref"] for t in swap_legs)


def test_ambiguous_contacts_exist_for_identification_tests():
    book = generate.generate()
    jimmys = [p for p in book.contacts if p["first_name"] == "Jimmy"]
    assert len({p["client_id"] for p in jimmys}) >= 2
    names = [c["counterpart_name"] for c in book.clients]
    assert sum(n.startswith("Meridian Food") for n in names) == 2


def test_writers_round_trip(tmp_path):
    book = generate.generate(n_trades=40)
    db = generate.write_sqlite(book, tmp_path / "c.db")
    generate.write_csvs(book, tmp_path / "csv")
    conn = sqlite3.connect(db)
    assert conn.execute("select count(*) from trades").fetchone()[0] == len(book.trades)
    assert conn.execute("select count(*) from contacts").fetchone()[0] == len(book.contacts)
    with (tmp_path / "csv" / "trades.csv").open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == schema.TRADE_HEADERS
