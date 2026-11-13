"""Data model for the synthetic client book (dummy data only - no real clients).

Four tables:

* ``clients``      one row per counterpart (company / individual), keyed by ``client_id``
* ``contacts``     people at each client; users ask by person ("Jimmy from Company A"),
                   trades are booked to the company, so this table bridges the two
* ``trades``       one row per deal (swaps: one row per leg), using the 82 columns of the
                   sales/Murex export. CSV keeps the export's exact headers; SQLite uses
                   the snake_case names below.
* ``interactions`` logged client queries - the "longer-term benefit" query database
"""
from __future__ import annotations

# (export header, sqlite column, sqlite type). Order = export column order.
TRADE_COLUMNS: list[tuple[str, str, str]] = [
    ("Contract reference", "contract_ref", "TEXT"),
    ("Package reference", "package_ref", "TEXT"),
    ("Trn# (Internal)", "trn_internal", "TEXT PRIMARY KEY"),
    ("Portfolio", "portfolio", "TEXT"),
    ("Trade category", "trade_category", "TEXT"),
    ("Dealer", "dealer", "TEXT"),
    ("Remark / Comment", "remark", "TEXT"),
    ("Counterpart label", "counterpart_label", "TEXT"),
    ("Counterpart name", "counterpart_name", "TEXT"),
    ("CustSeg", "cust_seg", "TEXT"),
    ("Cust_RM", "cust_rm", "TEXT"),
    ("Trn.Date", "trn_date", "TEXT"),
    ("Date: Period calc. start", "period_start", "TEXT"),
    ("Date: Period calc. end", "period_end", "TEXT"),
    ("Instrument displayed label", "instrument_label", "TEXT"),
    ("DCR Opt Instrument", "dcr_opt_instrument", "TEXT"),
    ("CCY 1", "ccy1", "TEXT"),
    ("Notional Amount 1", "notional1", "REAL"),
    ("CCY 2", "ccy2", "TEXT"),
    ("Notional Amount 2", "notional2", "REAL"),
    ("InitialPrice", "initial_price", "REAL"),
    ("Strike / Rate", "strike_rate", "REAL"),
    ("Sale Credit CCY", "sale_credit_ccy", "TEXT"),
    ("Sales FX Margin (spread in FCY)", "sales_fx_margin_fcy", "REAL"),
    ("Amt at Sales Credit UDF (FCY)", "amt_sales_credit_udf_fcy", "REAL"),
    ("Total Sale Credit amt (FCY)", "total_sale_credit_fcy", "REAL"),
    ("Nominal currency", "nominal_ccy", "TEXT"),
    ("Nominal amt Adjusted", "nominal_amt_adj", "REAL"),
    ("Notional amt (SGD)", "notional_sgd", "REAL"),
    ("Sales FX Margin (spread in SGD)", "sales_fx_margin_sgd", "REAL"),
    ("Amt at Sales Credit UDF (SGD)", "amt_sales_credit_udf_sgd", "REAL"),
    ("Total Sales Credit amt (SGD)", "total_sales_credit_sgd", "REAL"),
    ("Costctr", "cost_centre", "TEXT"),
    ("Strategy", "strategy", "TEXT"),
    ("Trn.Fmly", "trn_family", "TEXT"),
    ("Trn.Group", "trn_group", "TEXT"),
    ("Trn.Type", "trn_type", "TEXT"),
    ("Status (LIVE/MKT_OP/DEAD)", "status", "TEXT"),
    ("TA RM ID", "ta_rm_id", "TEXT"),
    ("Expiry Date", "expiry_date", "TEXT"),
    ("Trn# (External)", "trn_external", "TEXT"),
    ("BUY/SELL", "buy_sell", "TEXT"),
    ("Spot Margin", "spot_margin", "REAL"),
    ("COMMENT_1", "comment_1", "TEXT"),
    ("SIBS CIF", "sibs_cif", "TEXT"),
    ("RM Team Name - L1", "rm_team_l1", "TEXT"),
    ("RM Team Name - L2", "rm_team_l2", "TEXT"),
    ("RM Team Name - L3", "rm_team_l3", "TEXT"),
    ("RM Team Name - L4", "rm_team_l4", "TEXT"),
    ("RM Team Name - L5", "rm_team_l5", "TEXT"),
    ("Customer RM Code", "customer_rm_code", "TEXT"),
    ("Amendment status", "amendment_status", "TEXT"),
    ("Contract NA event action", "contract_na_event_action", "TEXT"),
    ("Security ISIN", "security_isin", "TEXT"),
    ("Contract source module", "contract_source_module", "TEXT"),
    ("Last market operation (Label)", "last_market_operation", "TEXT"),
    ("Contract last event label", "contract_last_event", "TEXT"),
    ("Contract last impact event label", "contract_last_impact_event", "TEXT"),
    ("Sys.Date", "sys_date", "TEXT"),
    ("Sys.Time", "sys_time", "TEXT"),
    ("NFIN_NPV0", "nfin_npv0", "REAL"),
    ("NFIN_NPV0S", "nfin_npv0s", "REAL"),
    ("FXSPOT0S", "fxspot0s", "REAL"),
    ("NFIN_NPV1", "nfin_npv1", "REAL"),
    ("FXSPOT1S", "fxspot1s", "REAL"),
    ("NFIN_NPV1S", "nfin_npv1s", "REAL"),
    ("NFIN_NPV2", "nfin_npv2", "REAL"),
    ("FXSPOT2S", "fxspot2s", "REAL"),
    ("NFIN_NPV2S", "nfin_npv2s", "REAL"),
    ("PL currency", "pl_ccy", "TEXT"),
    ("Entity", "entity", "TEXT"),
    ("Entity accounting currency", "entity_accounting_ccy", "TEXT"),
    ("External/Inter/Intra", "external_inter_intra", "TEXT"),
    ("Internal", "internal", "TEXT"),
    ("Dealer ID", "dealer_id", "TEXT"),
    ("Contract origin reference", "contract_origin_ref", "TEXT"),
    ("Replacement: Origin Nb", "replacement_origin_nb", "TEXT"),
    ("Trader Credit UDF (FCY)", "trader_credit_udf_fcy", "REAL"),
    ("Trader Credit UDF (SGD)", "trader_credit_udf_sgd", "REAL"),
    ("Total Client Markup UDF (FCY)", "total_client_markup_fcy", "REAL"),
    ("Total Client Markup UDF (SGD)", "total_client_markup_sgd", "REAL"),
    ("Replacement: Date", "replacement_date", "TEXT"),
]

TRADE_HEADERS = [h for h, _, _ in TRADE_COLUMNS]
TRADE_FIELDS = [f for _, f, _ in TRADE_COLUMNS]

# The ~15 columns the agent actually needs for "client data" answers.
AGENT_TRADE_FIELDS = [
    "trn_internal", "counterpart_name", "sibs_cif", "instrument_label", "trn_type", "buy_sell",
    "ccy1", "notional1", "ccy2", "notional2", "strike_rate", "trn_date", "expiry_date", "status",
    "notional_sgd", "total_sales_credit_sgd", "nfin_npv0", "cust_rm",
]

CLIENT_COLUMNS = [
    ("client_id", "TEXT PRIMARY KEY"),
    ("sibs_cif", "TEXT UNIQUE"),
    ("counterpart_name", "TEXT"),
    ("counterpart_label", "TEXT"),
    ("aliases", "TEXT"),            # ';'-separated alternative names users might type
    ("cust_seg", "TEXT"),
    ("industry", "TEXT"),
    ("country", "TEXT"),
    ("profile", "TEXT"),            # e.g. exporter / importer / investor
    ("hedging_notes", "TEXT"),
    ("preferred_pairs", "TEXT"),    # ';'-separated, e.g. USDSGD;EURUSD
    ("cust_rm", "TEXT"),
    ("customer_rm_code", "TEXT"),
    ("rm_team_l1", "TEXT"), ("rm_team_l2", "TEXT"), ("rm_team_l3", "TEXT"),
    ("rm_team_l4", "TEXT"), ("rm_team_l5", "TEXT"),
]

CONTACT_COLUMNS = [
    ("contact_id", "TEXT PRIMARY KEY"),
    ("client_id", "TEXT REFERENCES clients(client_id)"),
    ("first_name", "TEXT"),
    ("last_name", "TEXT"),
    ("title", "TEXT"),
    ("email", "TEXT"),
    ("is_primary", "INTEGER"),
]

INTERACTION_COLUMNS = [
    ("interaction_id", "TEXT PRIMARY KEY"),
    ("client_id", "TEXT REFERENCES clients(client_id)"),
    ("contact_id", "TEXT REFERENCES contacts(contact_id)"),
    ("asked_at", "TEXT"),           # ISO datetime, SGT
    ("logged_by", "TEXT"),          # salesperson / RM who logged it
    ("question", "TEXT"),
    ("instruments", "TEXT"),        # ';'-separated instrument keys, e.g. USDSGD
    ("topic", "TEXT"),              # forecast / rates / commodities / macro
    ("answer_summary", "TEXT"),
    ("conversation_id", "TEXT"),    # link to orchestrator conversation (null for seeded rows)
]


def ddl() -> str:
    def table(name, cols):
        return f"CREATE TABLE IF NOT EXISTS {name} (" + ", ".join(f"{c} {t}" for c, t in cols) + ");"
    return "\n".join([
        table("clients", CLIENT_COLUMNS),
        table("contacts", CONTACT_COLUMNS),
        table("trades", [(f, t) for _, f, t in TRADE_COLUMNS]),
        table("interactions", INTERACTION_COLUMNS),
        "CREATE INDEX IF NOT EXISTS ix_trades_cif ON trades(sibs_cif);",
        "CREATE INDEX IF NOT EXISTS ix_contacts_client ON contacts(client_id);",
        "CREATE INDEX IF NOT EXISTS ix_interactions_client ON interactions(client_id);",
    ])
