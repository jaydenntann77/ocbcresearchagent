# Ingestion and coverage report

* **Requested window:** 7 October – 5 November 2026 inclusive (30 calendar days ending on the run date, Asia/Singapore). Expanded beyond default: no.
* **First full run:** `run-20261105-092053-8515` started 5 Nov 2026, 09:20 SGT.

* **Source boundary:** https://www.ocbc.com research pages and `/iwov-resources/sg/ocbc/gbc/pdf/` only; robots.txt honoured; ≥1 s between requests; bounded retries; every redirect re-checked against the allow-list.
* **Coverage complete:** NO - see failures below.

## Totals (first full run)

| Outcome | Count |
|---|--:|
| Discovered (unique PDF URLs) | 145 |
| Downloaded, validated and indexed | 53 |
| Excluded by publication date | 51 |
| Duplicates (same content hash) | 0 |
| Quarantined (date uncertain) | 1 |
| Inaccessible | 2 |
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
| Macro Views listing November 2026 | Daily Treasury Outlook | ok | 3 |
| Macro Views listing November 2026 | Weekly Macro Views | ok | 1 |
| FX And Rates page | FX And Rates | ok — static page; listings load via AJAX | 0 |
| FX And Rates listing October 2026 | Foreign Exchange (FX) | ok | 25 |
| FX And Rates listing October 2026 | Interest Rates and Bond Yields | ok | 12 |
| FX And Rates listing October 2026 | Interest Rates and Bonds Yields Forecast | empty | 0 |
| FX And Rates listing November 2026 | Foreign Exchange (FX) | ok | 4 |
| FX And Rates listing November 2026 | Interest Rates and Bond Yields | ok | 3 |
| FX And Rates listing November 2026 | Interest Rates and Bonds Yields Forecast | empty | 0 |
| Sustainability And Commodities page | Sustainability And Commodities | ok — static page; listings load via AJAX | 0 |
| Sustainability And Commodities listing October 2026 | ESG Weekly Reports | ok | 4 |
| Sustainability And Commodities listing October 2026 | ESG Thematic Reports | empty | 0 |
| Sustainability And Commodities listing October 2026 | Commodities | ok | 3 |
| Sustainability And Commodities listing November 2026 | ESG Weekly Reports | ok | 1 |
| Sustainability And Commodities listing November 2026 | ESG Thematic Reports | empty | 0 |
| Sustainability And Commodities listing November 2026 | Commodities | empty | 0 |
| Credit Research page | Credit Research | ok — static page; listings load via AJAX | 0 |
| Credit Research listing October 2026 | Credit Research | ok | 16 |
| Credit Research listing November 2026 | Credit Research | ok | 2 |
| Equity Research page | Equity Research | ok — static page; listings load via AJAX | 0 |
| Equity Research listing October 2026 | Equity Research | ok | 2 |
| Equity Research listing November 2026 | Equity Research | empty | 0 |
| Investment reports (equity) | Equity Research | ok | 21 |

## Coverage by specialist collection

| Specialist | Documents | Passages | Forecast cells |
|---|--:|--:|--:|
| FX | 62 | 276 | 1488 |
| RATES | 68 | 249 | 207 |
| MACRO | 73 | 906 | 288 |
| EQUITIES | 26 | 73 | 0 |
| CREDIT | 36 | 270 | 0 |

Multi-sector reports (e.g. Daily Treasury Outlook, Daily Credit Snapshot) are indexed section-by-section into every specialist collection their content belongs to, keeping the original document ID and page.

**Gap:** no Equity Research publication was listed in the window (the most recent equity report on the site is dated 5 Oct 2026). The Equities collection contains only equity-market passages from multi-sector daily reports, so equity questions will mostly return a missing-coverage notice.

## Indexed documents

| Published | Title | Type / age | Date basis | Specialists | OCR pages | Doc ID |
|---|---|---|---|---|---|---|
| 2026-11-04 | [Daily Credit Snapshot (04 Nov)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2004%20November%202026.pdf) | daily · Recent (1d at window end) | listing date and printed date agree (high) | CREDIT, FX, RATES | — | `ocbc-2748e32c43f6` |
| 2026-11-04 | [Daily Market Outlook: AUD Nears Its Limit](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/Softer%20UST%20yields%3B%20toppish%20AUD%20rates.pdf) | daily · Recent (1d at window end) | listing date and printed date agree (high) | FX, RATES | — | `ocbc-890fc55b8cca` |
| 2026-11-04 | [Daily Treasury Outlook (4 November 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20041126.pdf) | daily · Recent (1d at window end) | listing date and printed date agree (high) | EQUITIES, FX, MACRO, RATES | — | `ocbc-a649c6dad40c` |
| 2026-11-04 | [Sustainability Weekly (4 Nov 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/sustainability/Sustainability%20Weekly%2020261104.pdf) | weekly · Recent (1d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-00bdc38be8fd` |
| 2026-11-03 | [Daily Credit Snapshot (03 Nov)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2003%20November%202026.pdf) | daily · Recent (2d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-fd8277aa8e55` |
| 2026-11-03 | [Daily Market Outlook: Oil Relief, AI Doubts](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20110326.pdf) | daily · Recent (2d at window end) | listing date and printed date agree (high) | FX, MACRO | — | `ocbc-6d43d67051aa` |
| 2026-11-03 | [Daily Treasury Outlook (3 November 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20031126.pdf) | daily · Recent (2d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-344f196110d2` |
| 2026-11-03 | [Interest Rates Focus: USTs marked time; PBoC hiked FX reserve ratio](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/USTs%20marked%20time%3B%20PBoC%20hiked%20FX%20reserve%20ratio.pdf) | thematic · Recent (2d at window end) | listing date and printed date agree (high) | FX, RATES | — | `ocbc-6c22920d27d7` |
| 2026-11-02 | [Daily Treasury Outlook (2 November 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20021126.pdf) | daily · Older (3d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-a88fce5d6160` |
| 2026-11-02 | [FX Outlook: RMB: Longer Runway for Measured Appreciation](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/FX%20Ideas/RMB_%20Longer%20Runway%20for%20Measured%20Appreciation.pdf) | thematic · Recent (3d at window end) | listing date and printed date agree (high) | FX | — | `ocbc-f6103634c849` |
| 2026-11-02 | [FX Weekly: Firm, Not One-Way](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/FX%20Ideas/FX%20Weekly%20110226.pdf) | weekly · Recent (3d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-fe1023b392fb` |
| 2026-11-02 | [Interest Rates Focus: Rates: Event risks this week; PBoC benchmark](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/Event%20risks%20this%20week%3B%20PBoC%20benchmark.pdf) | thematic · Recent (3d at window end) | listing date and printed date agree (high) | RATES | — | `ocbc-e6f1fbf5482b` |
| 2026-11-02 | [Weekly Macro View (2 Nov 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Weekly%20Macro%20View/WMV%202%20Nov%202026.pdf) | weekly · Recent (3d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | 1, 18, 20, 21, 22 | `ocbc-ee1f36deea6a` |
| 2026-10-30 | [Daily Credit Snapshot (30 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2030%20October%202026.pdf) | daily · Older (6d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-8179eedfbcb2` |
| 2026-10-30 | [Daily Market Outlook: AI Changes Risk-Off](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20103026.pdf) | daily · Older (6d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-f238366707ce` |
| 2026-10-30 | [Daily Treasury Outlook (30 October 2026](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20301026%20.pdf) | daily · Older (6d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-33c4aa111a0a` |
| 2026-10-29 | [Daily Credit Snapshot (29 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Credit%20Weekly/OCBC%20Daily%20Credit%20Snapshot%20-%2029%20October%202026.pdf) | daily · Older (7d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-14a05391fbbe` |
| 2026-10-29 | [Daily Market Outlook: USD Support, Upside Capped](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102926.pdf) | daily · Older (7d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-23a1639632ad` |
| 2026-10-29 | [Daily Treasury Outlook (29 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20291026%20.pdf) | daily · Older (7d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-f60510ee8a00` |
| 2026-10-29 | [Global Outlook: United Kingdom: Autumn Budget - Small steps](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Global%20Outlook/UK.Budget29Oct2026.pdf) | thematic · Recent (7d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-4de5b83d1bda` |
| 2026-10-29 | [Global Outlook: United States: FOMC Review - Dovish at the margins](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Global%20Outlook/US.FOMCReview29Oct26.pdf) | thematic · Recent (7d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-edc7a4d23f9b` |
| 2026-10-29 | [Interest Rates Focus: UST curve steepened on Fed hold; long-end gilts outperformed upon UK budget](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/UST%20curve%20steepened%20on%20Fed%20hold%3B%20long-end%20gilts%20outperformed%20upon%20UK%20budget.pdf) | thematic · Recent (7d at window end) | listing date and printed date agree (high) | RATES | — | `ocbc-85b487096eaa` |
| 2026-10-28 | [Daily Credit Snapshot (28 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Credit%20Weekly/OCBC%20Daily%20Credit%20Snapshot%20-%2028%20October%202026.pdf) | daily · Stale (8d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-9c2a2c55482f` |
| 2026-10-28 | [Daily Market Outlook: USD Still Has Support](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102826.pdf) | daily · Stale (8d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-2eb7261c7163` |
| 2026-10-28 | [Daily Treasury Outlook (28 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20281026%20.pdf) | daily · Stale (8d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-358cec7cee72` |
| 2026-10-27 | [Credit Week in Brief (27 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Credit%20Weekly/Week%20in%20Brief%2027102026.pdf) | weekly · Older (9d at window end) | listing date and printed date agree (high) | CREDIT | 1 | `ocbc-010c9d0429e0` |
| 2026-10-27 | [Daily Credit Snapshot (27 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2027%20October%202026.pdf) | daily · Stale (9d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-06f1ae85be93` |
| 2026-10-27 | [Daily Market Outlook: JPY Finds Its Hedge](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102726.pdf) | daily · Stale (9d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-5328de9d5d64` |
| 2026-10-27 | [Daily Treasury Outlook (27 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20271026%20.pdf) | daily · Stale (9d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-eaed8313d942` |
| 2026-10-27 | [Interest Rates Focus: 5Y SGS Auction Preview](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/5Y%20SGS%20preview%20Oct2026.pdf) | thematic · Recent (9d at window end) | listing date and printed date agree (high) | CREDIT, RATES | — | `ocbc-fe834979d8de` |
| 2026-10-27 | [Sustainability Weekly (27 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/sustainability/Sustainability%20Weekly%2020261027.pdf) | weekly · Older (9d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-3a1af26e955a` |
| 2026-10-26 | [China: Easing through the policy framework, not outright rate cuts](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/China/Week%20in%20Review/2026/China%20WIR%2026Oct26.pdf) | weekly · Older (10d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-09945e4e1baa` |
| 2026-10-26 | [Commodities Outlook: Searching for a Floor](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Commodities%20Research/Outlook/2026/PMT261026.pdf) | thematic · Recent (10d at window end) | listing date and printed date agree (high) | MACRO, RATES | — | `ocbc-99b74edbabb2` |
| 2026-10-26 | [Daily Credit Snapshot (26 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2026%20October%202026.pdf) | daily · Stale (10d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-e30038c96a36` |
| 2026-10-26 | [Daily Treasury Outlook (26 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20261026%20.pdf) | daily · Stale (10d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-4e1086444fd5` |
| 2026-10-26 | [FX Weekly: AI Tests the Dollar](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/FX%20Ideas/FX%20Weekly%20102626.pdf) | weekly · Older (10d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-87b1953be8a6` |
| 2026-10-26 | [Interest Rates Focus: UST yields in ranges](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/UST%20yields%20in%20ranges.pdf) | thematic · Recent (10d at window end) | listing date and printed date agree (high) | FX, RATES | — | `ocbc-2ccd95839d52` |
| 2026-10-26 | [Weekly Macro View (26 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Weekly%20Macro%20View/WMV%2026%20Oct%202026.pdf) | weekly · Older (10d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | 1, 13, 15 | `ocbc-23abb814f685` |
| 2026-10-23 | [Daily Credit Snapshot (23 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2023%20October%202026.pdf) | daily · Stale (13d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-8d5a882d7481` |
| 2026-10-23 | [Daily Market Outlook: Different Shocks, Different Havens](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102326.pdf) | daily · Stale (13d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-f32dbad7b63c` |
| 2026-10-23 | [Daily Treasury Outlook (23 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20231026%20.pdf) | daily · Stale (13d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-a9b30a11fd04` |
| 2026-10-23 | [Interest Rates Focus: Bonds rallies; pass-through onto SGD rates](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/Bonds%20rallies%3B%20pass-through%20onto%20SGD%20rates.pdf) | thematic · Recent (13d at window end) | listing date and printed date agree (high) | MACRO, RATES | — | `ocbc-fec7ed91070d` |
| 2026-10-22 | [Daily Credit Snapshot (22 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2022%20October%202026.pdf) | daily · Stale (14d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-230689806933` |
| 2026-10-22 | [Daily Market Outlook: Relief, Not Resolution](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102226.pdf) | daily · Stale (14d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-067001d5c22a` |
| 2026-10-22 | [Daily Treasury Outlook (22 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20221026%20.pdf) | daily · Stale (14d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-cf8aa442da26` |
| 2026-10-21 | [Daily Credit Snapshot (21 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2021%20October%202026.pdf) | daily · Stale (15d at window end) | listing date and printed date agree (high) | CREDIT, FX, MACRO, RATES | — | `ocbc-29093be72542` |
| 2026-10-21 | [Daily Market Outlook: GBP Boost, But Capped](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102126.pdf) | daily · Stale (15d at window end) | listing date and printed date agree (high) | FX, MACRO | — | `ocbc-684ce4f0cfc1` |
| 2026-10-21 | [Daily Treasury Outlook (21 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20211026%20.pdf) | daily · Stale (15d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-bd8396825655` |
| 2026-10-21 | [Interest Rates Focus: Flatter curves; firmer SGD rates](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/Flatter%20curves%3B%20firmer%20SGD%20rates.pdf) | thematic · Older (15d at window end) | listing date and printed date agree (high) | RATES | — | `ocbc-d8b8105d1775` |
| 2026-10-20 | [Credit Week in Brief (20 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Credit%20Weekly/2026/Week%20in%20Brief%20-%20Credit%20-%20201026.pdf) | weekly · Older (16d at window end) | listing date and printed date agree (high) | CREDIT | 1 | `ocbc-6b599cae69c6` |
| 2026-10-20 | [Daily Credit Snapshot (20 Oct)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2020%20October%202026.pdf) | daily · Stale (16d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-aa685ad98e37` |
| 2026-10-20 | [Daily Market Outlook: USD: Still Supported](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20102026.pdf) | daily · Stale (16d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-ae87e99263da` |
| 2026-10-20 | [Daily Treasury Outlook (20 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20201026.pdf) | daily · Stale (16d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-f76e23c6f84a` |
| 2026-10-20 | [Interest Rates Focus: Diverging bond performances; PBoC o/n reverse repo](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/Diverging%20bond%20performances%3B%20PBoC%20reverse%20repo.pdf) | thematic · Older (16d at window end) | listing date and printed date agree (high) | FX, RATES | — | `ocbc-c2dfb3200590` |
| 2026-10-20 | [Sustainability Weekly (20 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/sustainability/Sustainability%20Weekly%2020261020.pdf) | weekly · Older (16d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-30fe166fea1e` |
| 2026-10-19 | [China: AI-Led Resilience Buys Time, but Structural Challenges Persist](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/China/China%20Insights/China%203Q%20GDP.pdf) | thematic · Older (17d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-94f5ae27bb59` |
| 2026-10-19 | [China: Stronger external demand](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/China/Week%20in%20Review/2026/China%20WIR%2019Oct26.pdf) | weekly · Older (17d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-d0c6ed51a442` |
| 2026-10-19 | [Daily Treasury Outlook (19 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20191026.pdf) | daily · Stale (17d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-af93b55a9317` |
| 2026-10-19 | [FX Outlook: IDR: Beyond the MSCI Shock](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/FX%20Ideas/IDR_%20Beyond%20the%20MSCI%20Shock.pdf) | thematic · Older (17d at window end) | listing date and printed date agree (high) | FX | — | `ocbc-24dbfed1866d` |
| 2026-10-19 | [FX Weekly: USD’s AI Achilles’ Heel](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/FX%20Ideas/FX%20Weekly%201019.pdf) | weekly · Older (17d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-9b21fa423c16` |
| 2026-10-19 | [Weekly Macro View (19 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Weekly%20Macro%20View/WMV%2019%20Oct%202026.pdf) | weekly · Older (17d at window end) | listing date and printed date agree (high) | MACRO, RATES | 1, 19, 21 | `ocbc-e6b1205e65e8` |
| 2026-10-16 | [Daily Market Outlook: USD’s AI Achilles’ Heel](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20101626.pdf) | daily · Stale (20d at window end) | listing date and printed date agree (high) | FX, MACRO | — | `ocbc-939b7dfdf799` |
| 2026-10-16 | [Daily Treasury Outlook (16 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20161026.pdf) | daily · Stale (20d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-3b91f1e0220f` |
| 2026-10-16 | [Indonesia: MSCI reclassification risks loom](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Indonesia/ID.MSCI.StandaloneConsultation.16Oct27.pdf) | thematic · Older (20d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-9d40f3050c8c` |
| 2026-10-15 | [Daily Market Outlook: Why Isn’t USD Stronger?](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20101526.pdf) | daily · Stale (21d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-486e1188a7b6` |
| 2026-10-15 | [Daily Treasury Outlook (15 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20151026%20.pdf) | daily · Stale (21d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-a0a999a6f4de` |
| 2026-10-15 | [Global Outlook: United States: Midterms 2026 Part 2](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Global%20Outlook/US.Midtermspart2.15Oct26%20.pdf) | thematic · Older (21d at window end) | listing date only (medium) | CREDIT, MACRO, RATES | — | `ocbc-0d3b0b0d11e0` |
| 2026-10-15 | [Interest Rates Focus: Bonds rallied; CNY rates softened](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/Bonds%20rallied%3B%20CNY%20rates%20softened.pdf) | thematic · Older (21d at window end) | printed date (minor listing discrepancy) (medium) | RATES | — | `ocbc-240f03bc27e7` |
| 2026-10-14 | [Daily Market Outlook: Breakout On Hold](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20101426.pdf) | daily · Stale (22d at window end) | listing date and printed date agree (high) | FX, MACRO | — | `ocbc-5a3b5043fb1a` |
| 2026-10-14 | [Daily Treasury Outlook (14 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20141026%20.pdf) | daily · Stale (22d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-f3d2497274e8` |
| 2026-10-14 | [Global Outlook: United States: Midterms 2026 Part 1](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Global%20Outlook/US.Midtermspart1.14Oct26.pdf) | thematic · Older (22d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-5e8287709fdf` |
| 2026-10-14 | [Interest Rates Focus: MAS kept policy on hold](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/MAS%20kept%20policy%20on%20hold.pdf) | thematic · Older (22d at window end) | listing date and printed date agree (high) | FX, RATES | — | `ocbc-5f5ab9155f76` |
| 2026-10-14 | [Singapore's 3Q26 GDP moderates while MAS held S$NEER policy unchanged](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Singapore/SG.3QGDPandMAS14Oct26.pdf) | thematic · Older (22d at window end) | listing date and printed date agree (high) | MACRO, RATES | — | `ocbc-a245a4495a06` |
| 2026-10-13 | [Daily Market Outlook: Supported, Not Surging](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20101326.pdf) | daily · Stale (23d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-d0c611a71ed5` |
| 2026-10-13 | [Daily Treasury Outlook (13 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20131026%20.pdf) | daily · Stale (23d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-d7d510145fc7` |
| 2026-10-12 | [China’s response to mounting external pressure](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/China/Week%20in%20Review/2026/China%20WIR%2012Oct26.pdf) | weekly · Stale (24d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-4deddb7b3b96` |
| 2026-10-12 | [Daily Treasury Outlook (12 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20121026%20.pdf) | daily · Stale (24d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-b1ffb92a30ab` |
| 2026-10-12 | [FX Weekly: Relief, Not Breakout](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/FX%20Ideas/FX%20Weekly%20101226.pdf) | weekly · Stale (24d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-4b80ba05fd21` |
| 2026-10-12 | [Interest Rates Focus: UST consolidation; MGS supply](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/UST%20consolidation%3B%20MGS%20supply.pdf) | thematic · Older (24d at window end) | listing date and printed date agree (high) | RATES | — | `ocbc-5b403f2b56fb` |
| 2026-10-12 | [Sustainability Weekly (12 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/sustainability/Sustainability%20Weekly%2020261012.pdf) | weekly · Stale (24d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-00740f449529` |
| 2026-10-12 | [Weekly Macro View (12 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Weekly%20Macro%20View/WMV%2012%20Oct%202026.pdf) | weekly · Stale (24d at window end) | listing date and printed date agree (high) | FX, MACRO | 1, 19, 21 | `ocbc-2d0ba2e9da13` |
| 2026-10-09 | [Commodities Outlook: Tentative Relief](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Commodities%20Research/Outlook/PMT091026.pdf) | thematic · Older (27d at window end) | listing date and printed date agree (high) | MACRO, RATES | — | `ocbc-39b9fce018b0` |
| 2026-10-09 | [Daily Market Outlook: Volatility Relief?](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20100926.pdf) | daily · Stale (27d at window end) | listing date and printed date agree (high) | FX, MACRO | — | `ocbc-e7b264b4a09c` |
| 2026-10-09 | [Daily Treasury Outlook (9 October 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20091026%20.pdf) | daily · Stale (27d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-fbf9bcd8acd4` |
| 2026-10-09 | [Interest Rates Focus: Solid UST auctions; SGD rates lower](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/Solid%20UST%20auctions%3B%20SGD%20rates%20lower.pdf) | thematic · Older (27d at window end) | listing date and printed date agree (high) | RATES | — | `ocbc-14e7c33e5e32` |
| 2026-10-09 | [Malaysia: Budget 2027: Balancing policies, politics and priorities](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Malaysia/MA_Budget2027review_9Oct26.pdf) | thematic · Older (27d at window end) | listing date and printed date agree (high) | MACRO | — | `ocbc-5808fbc6eaa7` |
| 2026-10-08 | [Daily Market Outlook: Fed Firm, EUR Fragile](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20100826.pdf) | daily · Stale (28d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-3a3d0ae994d9` |
| 2026-10-08 | [OCBC Daily Treasury Outlook (8 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20081026%20.pdf) | daily · Stale (28d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-ac7ddd8974dd` |
| 2026-10-07 | [Daily Market Outlook: Rates Catch Breath](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/DMO/2026/DMO%20100726.pdf) | daily · Stale (29d at window end) | listing date and printed date agree (high) | FX, MACRO, RATES | — | `ocbc-52668d1c2fde` |
| 2026-10-07 | [Interest Rates Focus: Views on short-end SGD and HKD rates](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/FX%20Outlook/Interest%20rates/Views%20on%20short-end%20SGD%20and%20HKD%20rates.pdf) | thematic · Older (29d at window end) | listing date and printed date agree (high) | RATES | — | `ocbc-eb8a8b4c9187` |
| 2026-10-07 | [OCBC Daily Treasury Outlook (7 Oct 2026)](https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Daily%20Treasury%20Outlook/2026/DTO%20071026%20.pdf) | daily · Stale (29d at window end) | listing date and printed date agree (high) | CREDIT, EQUITIES, FX, MACRO, RATES | — | `ocbc-5b050e47a238` |

## Date discrepancies flagged

* Daily Market Outlook: USD Support, Upside Capped: PDF metadata title 'DMO 23 Apr 2026' carries date 2026-04-23; it is not used (listing/printed date 2026-10-29 applies)
* Global Outlook: United States: Midterms 2026 Part 2: no printed date found; listing date not corroborated by PDF metadata
* Interest Rates Focus: Bonds rallied; CNY rates softened: listing date 2026-10-16 differs from printed date 2026-10-15 by 1 day(s); printed date used
* Download PDF: no website listing date; printed date used
* Global Outlook: United States: CPI Review - Core in line but headline missed narrowly: listing date 2026-10-15 conflicts with printed date 2026-10-05 (10 days)

## Excluded by date

| Title | Reason |
|---|---|
| Monthly Commodities Outlook | website listing date 2026-10-01 outside window (not downloaded) |
| Daily Credit Snapshot (01 Oct) | website listing date 2026-10-01 outside window (not downloaded) |
| Daily Credit Snapshot (02 Oct) | website listing date 2026-10-02 outside window (not downloaded) |
| Singapore 2H2026 Credit Outlook (030726) | website listing date 2026-07-03 outside window (not downloaded) |
| Credit Week in Brief (05 Oct) | website listing date 2026-10-05 outside window (not downloaded) |
| OCBC Asia Credit - Monthly (06 October) | website listing date 2026-10-06 outside window (not downloaded) |
| OCBC Asia Credit - Monthly (04 September) | website listing date 2026-09-04 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (1 Oct 2026) | website listing date 2026-10-01 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (2 Oct 2026) | website listing date 2026-10-02 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (5 Oct 2026) | website listing date 2026-10-05 outside window (not downloaded) |
| OCBC Daily Treasury Outlook (6 Oct 2026) | website listing date 2026-10-06 outside window (not downloaded) |
| Oil, Yields, USD | website listing date 2026-10-01 outside window (not downloaded) |
| Europe's Fiscal Faultline | website listing date 2026-10-02 outside window (not downloaded) |
| EURUSD's Balancing Act | website listing date 2026-10-06 outside window (not downloaded) |
| Carry Still Favoured | website listing date 2026-08-17 outside window (not downloaded) |
| Volatility Awakens | website listing date 2026-10-05 outside window (not downloaded) |
| JPY Nearing Turning Point | website listing date 2026-10-02 outside window (not downloaded) |
| Oil Relief, Fed Pressures | website listing date 2026-06-22 outside window (not downloaded) |
| Looking for Another Slight Slope Increase | website listing date 2026-10-02 outside window (not downloaded) |
| ECB review; SGD rates | website listing date 2026-06-12 outside window (not downloaded) |
| Steeper UST curve; SGD rates retracement | website listing date 2026-10-05 outside window (not downloaded) |
| Download PDF | resolved publication date 2026-06-19 outside window |
| August retail sales growth moderated mainly due to the auto-related drag | website listing date 2026-10-05 outside window (not downloaded) |
| Research Monitor (Oct) | website listing date 2026-10-01 outside window (not downloaded) |
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

## Inaccessible documents and failures

* https://www.ocbc.com/Softer%20UST%20yields%3B%20toppish%20AUD%20rates.pdf: inaccessible — source boundary: path outside OCBC research boundary: /Softer UST yields; toppish AUD rates.pdf
* https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Credit%20Research/Asian%20Credit%20Daily/2026/OCBC%20Daily%20Credit%20Snapshot%20-%2019%20October%202026.pdf: inaccessible — source boundary: path outside OCBC research boundary: /html/404.html
* https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/Regional%20Focus/Global%20Outlook/US.CPISeptember2026Review.15Oct26.pdf: quarantined — listing date 2026-10-15 conflicts with printed date 2026-10-05 (10 days)

Passages withheld for embedded instruction-like text: 0.

