# Ingestion and coverage report

* **Requested window:** 26 October – 1 November 2026 inclusive (7 calendar days ending on the run date, Asia/Singapore). Expanded beyond default: no.
* **First full run:** `run-20261101-024051-a601` started 1 Nov 2026, 02:40 SGT.
* **Last successful ingestion:** `run-20261101-032153-c102` finished 1 Nov 2026, 03:25 SGT (re-run; every document reported `unchanged`).
* **Source boundary:** https://www.ocbc.com research pages and `/iwov-resources/sg/ocbc/gbc/pdf/` only; robots.txt honoured; ≥1 s between requests; bounded retries; every redirect re-checked against the allow-list.
* **Coverage complete:** yes - every listing page and section was checked successfully.

## Totals (first full run)

| Outcome | Count |
|---|--:|
| Discovered (unique PDF URLs) | 131 |
| Downloaded, validated and indexed | 25 |
| Excluded by publication date | 106 |
| Duplicates (same content hash) | 0 |
| Quarantined (date uncertain) | 0 |
| Inaccessible | 0 |
| Download failed | 0 |
| Invalid PDF | 0 |
| Parse failed | 0 |

## Pages and sections checked

| Source | Section | Status | Items |
|---|---|---|--:|
| Research index (Recent Updates) | — | ok | 13 |
| Macro Views page | Macro Views | ok — static page; listings load via AJAX | 0 |
| Macro Views listing October 2026 | Regional Focus | ok | 14 |
| Macro Views listing October 2026 | Daily Treasury Outlook | ok | 22 |
| Macro Views listing October 2026 | Weekly Macro Views | ok | 4 |
| Macro Views listing November 2026 | Regional Focus | empty | 0 |
| Macro Views listing November 2026 | Daily Treasury Outlook | empty | 0 |
| Macro Views listing November 2026 | Weekly Macro Views | empty | 0 |
| FX And Rates page | FX And Rates | ok — static page; listings load via AJAX | 0 |
| FX And Rates listing October 2026 | Foreign Exchange (FX) | ok | 25 |
| FX And Rates listing October 2026 | Interest Rates and Bond Yields | ok | 12 |
| FX And Rates listing October 2026 | Interest Rates and Bonds Yields Forecast | empty | 0 |
| FX And Rates listing November 2026 | Foreign Exchange (FX) | empty | 0 |
| FX And Rates listing November 2026 | Interest Rates and Bond Yields | empty | 0 |
| FX And Rates listing November 2026 | Interest Rates and Bonds Yields Forecast | empty | 0 |
| Sustainability And Commodities page | Sustainability And Commodities | ok — static page; listings load via AJAX | 0 |
| Sustainability And Commodities listing October 2026 | ESG Weekly Reports | ok | 4 |
| Sustainability And Commodities listing October 2026 | ESG Thematic Reports | empty | 0 |
| Sustainability And Commodities listing October 2026 | Commodities | ok | 3 |
| Sustainability And Commodities listing November 2026 | ESG Weekly Reports | empty | 0 |
| Sustainability And Commodities listing November 2026 | ESG Thematic Reports | empty | 0 |
| Sustainability And Commodities listing November 2026 | Commodities | empty | 0 |
| Credit Research page | Credit Research | ok — static page; listings load via AJAX | 0 |
| Credit Research listing October 2026 | Credit Research | ok | 16 |
| Credit Research listing November 2026 | Credit Research | empty | 0 |
| Equity Research page | Equity Research | ok — static page; listings load via AJAX | 0 |
| Equity Research listing October 2026 | Equity Research | ok | 2 |
| Equity Research listing November 2026 | Equity Research | empty | 0 |
| Investment reports (equity) | Equity Research | ok | 21 |

## Coverage by specialist collection

| Specialist | Documents | Passages | Forecast cells |
|---|--:|--:|--:|
| FX | 17 | 70 | 372 |
| RATES | 20 | 69 | 30 |
| MACRO | 21 | 216 | 72 |
| EQUITIES | 7 | 19 | 0 |
| CREDIT | 12 | 130 | 0 |

Multi-sector reports (e.g. Daily Treasury Outlook, Daily Credit Snapshot) are indexed section-by-section into every specialist collection their content belongs to, keeping the original document ID and page.

**Gap:** no Equity Research publication was listed in the window (the most recent equity report on the site is dated 5 Oct 2026). The Equities collection contains only equity-market passages from multi-sector daily reports, so equity questions will mostly return a missing-coverage notice.

## Indexed documents

| Published | Title | Type / age | Date basis | Specialists | OCR pages | Doc ID |
|---|---|---|---|---|---|---|
| 2026-10-30 | [Daily Credit Snapshot (30 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2030%20October%202026.pdf) | daily · Recent (2d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-8179eedfbcb2` |
| 2026-10-30 | [Daily Market Outlook: AI Changes Risk-Off](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20103026.pdf) | daily · Recent (2d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-f238366707ce` |
| 2026-10-30 | [Daily Treasury Outlook (30 October 2026](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20301026%20.pdf) | daily · Recent (2d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-33c4aa111a0a` |
| 2026-10-29 | [Daily Credit Snapshot (29 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Credit%20Weekly/OCBC%20Daily%20Credit%20Snapshot%20-%2029%20October%202026.pdf) | daily · Older (3d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-14a05391fbbe` |
| 2026-10-29 | [Daily Market Outlook: USD Support, Upside Capped](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102926.pdf) | daily · Older (3d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-23a1639632ad` |
| 2026-10-29 | [Daily Treasury Outlook (29 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20291026%20.pdf) | daily · Older (3d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-f60510ee8a00` |
| 2026-10-29 | [Global Outlook: United Kingdom: Autumn Budget - Small steps](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Global%20Outlook/UK.Budget29Oct2026.pdf) | thematic · Recent (3d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-4de5b83d1bda` |
| 2026-10-29 | [Global Outlook: United States: FOMC Review - Dovish at the margins](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Global%20Outlook/US.FOMCReview29Oct26.pdf) | thematic · Recent (3d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-edc7a4d23f9b` |
| 2026-10-29 | [Interest Rates Focus: UST curve steepened on Fed hold; long-end gilts outperformed upon UK budget](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/UST%20curve%20steepened%20on%20Fed%20hold%3B%20long-end%20gilts%20outperformed%20upon%20UK%20budget.pdf) | thematic · Recent (3d at window end) | listing date and printed date agree (high) | RATES | — | `ocbc-85b487096eaa` |
| 2026-10-28 | [Daily Credit Snapshot (28 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Credit%20Weekly/OCBC%20Daily%20Credit%20Snapshot%20-%2028%20October%202026.pdf) | daily · Older (4d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-9c2a2c55482f` |
| 2026-10-28 | [Daily Market Outlook: USD Still Has Support](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102826.pdf) | daily · Older (4d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-2eb7261c7163` |
| 2026-10-28 | [Daily Treasury Outlook (28 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20281026%20.pdf) | daily · Older (4d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-358cec7cee72` |
| 2026-10-27 | [Credit Week in Brief (27 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Credit%20Weekly/Week%20in%20Brief%2027102026.pdf) | weekly · Recent (5d at window end) | listing date and printed date agree (high) | CREDIT | 1 | `ocbc-010c9d0429e0` |
| 2026-10-27 | [Daily Credit Snapshot (27 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2027%20October%202026.pdf) | daily · Older (5d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-06f1ae85be93` |
| 2026-10-27 | [Daily Market Outlook: JPY Finds Its Hedge](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102726.pdf) | daily · Older (5d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-5328de9d5d64` |
| 2026-10-27 | [Daily Treasury Outlook (27 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20271026%20.pdf) | daily · Older (5d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-eaed8313d942` |
| 2026-10-27 | [Interest Rates Focus: 5Y SGS Auction Preview](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/5Y%20SGS%20preview%20Oct2026.pdf) | thematic · Recent (5d at window end) | listing date and printed date agree (high) | CREDIT, RATES | — | `ocbc-fe834979d8de` |
| 2026-10-27 | [Sustainability Weekly (27 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/sustainability/Sustainability%20Weekly%2020261027.pdf) | weekly · Recent (5d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-3a1af26e955a` |
| 2026-10-26 | [China: Easing through the policy framework, not outright rate cuts](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/China/Week%20in%20Review/2026/China%20WIR%2026Oct26.pdf) | weekly · Recent (6d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-09945e4e1baa` |
| 2026-10-26 | [Commodities Outlook: Searching for a Floor](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Commodities%20Research/Outlook/2026/PMT261026.pdf) | thematic · Recent (6d at window end) | listing date and printed date agree (high) | MACRO, RATES | — | `ocbc-99b74edbabb2` |
| 2026-10-26 | [Daily Credit Snapshot (26 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2026%20October%202026.pdf) | daily · Older (6d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-e30038c96a36` |
| 2026-10-26 | [Daily Treasury Outlook (26 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20261026%20.pdf) | daily · Older (6d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-4e1086444fd5` |
| 2026-10-26 | [FX Weekly: AI Tests the Dollar](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/FX%20Ideas/FX%20Weekly%20102626.pdf) | weekly · Recent (6d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-87b1953be8a6` |
| 2026-10-26 | [Interest Rates Focus: UST yields in ranges](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/UST%20yields%20in%20ranges.pdf) | thematic · Recent (6d at window end) | listing date and printed date agree (high) | FX, RATES | — | `ocbc-2ccd95839d52` |
| 2026-10-26 | [Weekly Macro View (26 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Weekly%20Macro%20View/WMV%2026%20Oct%202026.pdf) | weekly · Recent (6d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | 1, 13, 15 | `ocbc-23abb814f685` |

## Date discrepancies flagged

* Daily Market Outlook: USD Support, Upside Capped: PDF metadata title 'DMO 23 Apr 2026' carries date 2026-04-23; it is not used (listing/printed date 2026-10-29 applies)
* Download PDF: no website listing date; printed date used

## Excluded by date

| Title | Reason |
|---|---|
| Monthly Commodities Outlook | website listing date 2026-10-01 outside window (not downloaded) |
| Tentative Relief | website listing date 2026-10-09 outside window (not downloaded) |
| Daily Credit Snapshot (01 Oct) | website listing date 2026-10-01 outside window (not downloaded) |
| Daily Credit Snapshot (02 Oct) | website listing date 2026-10-02 outside window (not downloaded) |
| Daily Credit Snapshot (19 Oct) | website listing date 2026-10-19 outside window (not downloaded) |
| Daily Credit Snapshot (20 Oct) | website listing date 2026-10-20 outside window (not downloaded) |
| Daily Credit Snapshot (21 Oct) | website listing date 2026-10-21 outside window (not downloaded) |
| Daily Credit Snapshot (22 Oct) | website listing date 2026-10-22 outside window (not downloaded) |
| Daily Credit Snapshot (23 Oct) | website listing date 2026-10-23 outside window (not downloaded) |
| Singapore 2H2026 Credit Outlook (030726) | website listing date 2026-07-03 outside window (not downloaded) |
| Credit Week in Brief (20 Oct) | website listing date 2026-10-20 outside window (not downloaded) |
| Credit Week in Brief (05 Oct) | website listing date 2026-10-05 outside window (not downloaded) |
| OCBC Asia Credit - Monthly (06 October) | website listing date 2026-10-06 outside window (not downloaded) |
| OCBC Asia Credit - Monthly (04 September) | website listing date 2026-09-04 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (1 Oct 2026) | website listing date 2026-10-01 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (2 Oct 2026) | website listing date 2026-10-02 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (5 Oct 2026) | website listing date 2026-10-05 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (6 Oct 2026) | website listing date 2026-10-06 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (7 Oct 2026) | website listing date 2026-10-07 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (8 Oct 2026) | website listing date 2026-10-08 outside window (not downloaded) |
| Daily Treasury Outlook (9 October 2026) | website listing date 2026-10-09 outside window (not downloaded) |
| Daily Treasury Outlook (12 October 2026) | website listing date 2026-10-12 outside window (not downloaded) |
| Daily Treasury Outlook (13 October 2026) | website listing date 2026-10-13 outside window (not downloaded) |
| Daily Treasury Outlook (14 October 2026) | website listing date 2026-10-14 outside window (not downloaded) |
| Daily Treasury Outlook (15 October 2026) | website listing date 2026-10-15 outside window (not downloaded) |
| Daily Treasury Outlook (16 October 2026) | website listing date 2026-10-16 outside window (not downloaded) |
| Daily Treasury Outlook (19 October 2026) | website listing date 2026-10-19 outside window (not downloaded) |
| Daily Treasury Outlook (20 October 2026) | website listing date 2026-10-20 outside window (not downloaded) |
| Daily Treasury Outlook (21 October 2026) | website listing date 2026-10-21 outside window (not downloaded) |
| Daily Treasury Outlook (22 October 2026) | website listing date 2026-10-22 outside window (not downloaded) |
| Daily Treasury Outlook (23 October 2026) | website listing date 2026-10-23 outside window (not downloaded) |
| Oil, Yields, USD | website listing date 2026-10-01 outside window (not downloaded) |
| Europe's Fiscal Faultline | website listing date 2026-10-02 outside window (not downloaded) |
| EURUSD's Balancing Act | website listing date 2026-10-06 outside window (not downloaded) |
| Rates Catch Breath | website listing date 2026-10-07 outside window (not downloaded) |
| Fed Firm, EUR Fragile | website listing date 2026-10-08 outside window (not downloaded) |
| Volatility Relief? | website listing date 2026-10-09 outside window (not downloaded) |
| Supported, Not Surging | website listing date 2026-10-13 outside window (not downloaded) |
| Breakout On Hold | website listing date 2026-10-14 outside window (not downloaded) |
| Why Isn’t USD Stronger? | website listing date 2026-10-15 outside window (not downloaded) |
| USD’s AI Achilles’ Heel | website listing date 2026-10-16 outside window (not downloaded) |
| USD: Still Supported | website listing date 2026-10-20 outside window (not downloaded) |
| GBP Boost, But Capped | website listing date 2026-10-21 outside window (not downloaded) |
| Relief, Not Resolution | website listing date 2026-10-22 outside window (not downloaded) |
| Different Shocks, Different Havens | website listing date 2026-10-23 outside window (not downloaded) |
| Carry Still Favoured | website listing date 2026-08-17 outside window (not downloaded) |
| Volatility Awakens | website listing date 2026-10-05 outside window (not downloaded) |
| JPY Nearing Turning Point | website listing date 2026-10-02 outside window (not downloaded) |
| Oil Relief, Fed Pressures | website listing date 2026-06-22 outside window (not downloaded) |
| Relief, Not Breakout | website listing date 2026-10-12 outside window (not downloaded) |
| USD’s AI Achilles’ Heel | website listing date 2026-10-19 outside window (not downloaded) |
| IDR: Beyond the MSCI Shock | website listing date 2026-10-19 outside window (not downloaded) |
| Looking for Another Slight Slope Increase | website listing date 2026-10-02 outside window (not downloaded) |
| Bonds rallied; CNY rates softened | website listing date 2026-10-16 outside window (not downloaded) |
| Bonds rallies; pass-through onto SGD rates | website listing date 2026-10-23 outside window (not downloaded) |
| Diverging bond performances; PBoC o/n reverse repo | website listing date 2026-10-20 outside window (not downloaded) |
| ECB review; SGD rates | website listing date 2026-06-12 outside window (not downloaded) |
| Flatter curves; firmer SGD rates | website listing date 2026-10-21 outside window (not downloaded) |
| MAS kept policy on hold | website listing date 2026-10-14 outside window (not downloaded) |
| Solid UST auctions; SGD rates lower | website listing date 2026-10-09 outside window (not downloaded) |
| Steeper UST curve; SGD rates retracement | website listing date 2026-10-05 outside window (not downloaded) |
| UST consolidation; MGS supply | website listing date 2026-10-12 outside window (not downloaded) |
| Views on short-end SGD and HKD rates | website listing date 2026-10-07 outside window (not downloaded) |
| Download PDF | resolved publication date 2026-06-19 outside window |
| AI-Led Resilience Buys Time, but Structural Challenges Persist | website listing date 2026-10-19 outside window (not downloaded) |
| China’s response to mounting external pressure | website listing date 2026-10-12 outside window (not downloaded) |
| Stronger external demand | website listing date 2026-10-19 outside window (not downloaded) |
| United States: CPI Review - Core in line but headline missed narrowly | website listing date 2026-10-15 outside window (not downloaded) |
| United States: Midterms 2026 Part 1 | website listing date 2026-10-14 outside window (not downloaded) |
| United States: Midterms 2026 Part 2 | website listing date 2026-10-15 outside window (not downloaded) |
| MSCI reclassification risks loom | website listing date 2026-10-16 outside window (not downloaded) |
| Budget 2027: Balancing policies, politics and priorities | website listing date 2026-10-09 outside window (not downloaded) |
| Singapore's 3Q26 GDP moderates while MAS held S$NEER policy unchanged | website listing date 2026-10-14 outside window (not downloaded) |
| August retail sales growth moderated mainly due to the auto-related drag | website listing date 2026-10-05 outside window (not downloaded) |
| Research Monitor (Oct) | website listing date 2026-10-01 outside window (not downloaded) |
| Weekly Macro View (12 Oct 2026) | website listing date 2026-10-12 outside window (not downloaded) |
| Weekly Macro View (19 Oct 2026) | website listing date 2026-10-19 outside window (not downloaded) |
| Weekly Macro View (5 Oct 2026) | website listing date 2026-10-05 outside window (not downloaded) |
| Keppel DC REIT (KDCREIT SP) - A stellar start to FY26 | website listing date 2026-04-16 outside window (not downloaded) |
| SG Plantations: Stay rooted | website listing date 2026-09-03 outside window (not downloaded) |
| HK/CN: Attractive valuations offset by tech volatility | website listing date 2026-10-02 outside window (not downloaded) |
| Singapore Hospitality Monitor – Autumnal gold and glow | website listing date 2026-10-05 outside window (not downloaded) |
| Salesforce.com Inc | website listing date 2020-12-02 outside window (not downloaded) |
| HSBC | website listing date 2020-12-07 outside window (not downloaded) |
| Mapletree Logistics Trust | website listing date 2020-12-16 outside window (not downloaded) |
| Adobe Inc. | website listing date 2020-12-18 outside window (not downloaded) |
| Alibaba Group | website listing date 2020-12-28 outside window (not downloaded) |
| Mapletree Industrial Trust | website listing date 2021-02-01 outside window (not downloaded) |
| DBS Group Holdings Ltd | website listing date 2021-02-10 outside window (not downloaded) |
| Wilmar International | website listing date 2021-02-24 outside window (not downloaded) |
| UOL Group Ltd | website listing date 2021-03-02 outside window (not downloaded) |
| Venture Corporation | website listing date 2021-03-02 outside window (not downloaded) |
| Singapore Hospitality – Beneficiary of vaccine development | website listing date 2020-12-18 outside window (not downloaded) |
| Singapore Strategy – Recovery will favour SG stocks | website listing date 2020-12-17 outside window (not downloaded) |
| Weekly S-REITS Tracker | website listing date 2020-12-07 outside window (not downloaded) |
| Singapore Residential Sector – Ending 2020 on a high | website listing date 2021-01-05 outside window (not downloaded) |
| Global Energy & Materials sectors – Riding on the reflation theme | website listing date 2021-01-13 outside window (not downloaded) |
| Global Real Estate – Ideas to play the Blue Wave | website listing date 2021-01-13 outside window (not downloaded) |
| Aviation – 2021: A year of recovery | website listing date 2021-01-14 outside window (not downloaded) |
| US Technology Sector – Let’s get cyclical | website listing date 2021-01-19 outside window (not downloaded) |
| Singapore Banks – Proposed guidelines for a green transition | website listing date 2021-02-01 outside window (not downloaded) |
| Asia Real Estate – Hitting the reset button | website listing date 2021-02-15 outside window (not downloaded) |
| Singapore REITs – Volatility expected given bond yields spike | website listing date 2021-03-10 outside window (not downloaded) |
| Sustainability Weekly (5 Oct 2026) | website listing date 2026-10-05 outside window (not downloaded) |
| Sustainability Weekly (12 Oct 2026) | website listing date 2026-10-12 outside window (not downloaded) |
| Sustainability Weekly (20 Oct 2026) | website listing date 2026-10-20 outside window (not downloaded) |

## Inaccessible documents and failures

* None in this run.

Passages withheld for embedded instruction-like text: 0.

