# Test results

Run on 1 Nov 2026 (SGT), Windows 11, Python 3.10.11, against the real corpus ingested the same day
(26 Oct – 1 Nov 2026, 25 documents).

## Automated tests: `python -m pytest tests -v`: **56 passed**

| Suite | Tests | What it proves |
|---|--:|---|
| `test_units.py` | 15 | Seven-date inclusive window (26 Oct–1 Nov). Date-resolution rule, including quarantine and "metadata alone is not enough"; HTTP dates never used. Freshness thresholds per report type. Horizon parsing and passed horizons. Pair direction kept. Planner sends USD/SGD to FX only, SGD rates to Rates, credit to Credit, Fed+USD/SGD to FX+Rates, JPY/BoJ to FX+Rates, ESG to Macro. Follow-up inherits context. Web/advice guardrails. Injection detector. |
| `test_real_corpus.py` | 11 | Every USD-SGD forecast cell appears verbatim on the same printed row of its source PDF page. Exact set Dec-26 1.2700 … Dec-27 1.2550. The spot "Current (25 Sep) 1.2773" is stored as an observation, not a forecast. Data date and "trajectory bias" footnote preserved. Table headers travel with the values. All 25 documents date-confident. Stale metadata title flagged. OCR pages flagged. Collections routed correctly. No duplicate hashes or URLs. |
| `test_boundaries.py` | 20 | In a subprocess that installs the real orchestrator policy, all of these are **denied**: reading raw PDFs, listing the raw dir, opening corpus.db or a collection DB (file and SQLite), importing PyMuPDF / retrieval / embedding modules, DNS for www.ocbc.com and www.google.com, loopback to the docs, ingestion and gateway ports, and subprocesses. Its own conversation store and the specialist/validator ports are allowed. The specialist process has no internet and no raw PDFs. The gateway has no data access and no route to specialists. A specialist payload with `message_to_user` is rejected. FX cannot open the Credit collection. |
| `test_fixture_scenarios.py` | 11 | A full offline pipeline runs against a mocked OCBC site in an isolated temp corpus. It shows: 403 recorded as inaccessible; HTML-as-PDF as invalid; listing/printed date conflict quarantined; same-hash duplicate recorded as an alias; out-of-window item not downloaded; a 500 on the credit listing makes coverage incomplete and is disclosed by the Credit specialist; the re-run is idempotent; fixtures flagged `dev_fixture=1`; the scanned page is OCR'd and flagged through to the answer; embedded instructions withheld and never quoted; unresolved conflict shows both values; revision applies the latest report with the basis explained; SGD/USD never inverted; semantic-retrieval outage disclosed. The validator rejects an unsupported number, an inverted pair, recommendation language, an uncited claim, unsupported wording, a tampered table value and forged evidence. |

One run, made while the live stack was mid-way through an admin refresh, reported 11 setup errors in
`test_fixture_scenarios.py`. The cause was not captured. Five subsequent runs (full suite and module alone)
all passed, and it could not be reproduced. Treat it as a possible flake in the subprocess-based fixture
runner.

## End-to-end scenarios: `python -m tests.e2e_scenarios`: **16/16 passed**

Full evidence is in [scenario_results.md](scenario_results.md). Each required scenario and how it was exercised:

| Required scenario | Exercised on | Result |
|---|---|---|
| Forecast directly available in a PDF table | Real corpus | PASS. 8 USD/SGD rows, all equal to the extracted cells, FX lead only. |
| Requested horizon missing | Real corpus (2028) | PASS. No values, explicit "does not contain a verified forecast for the 2028 horizon". |
| Cross-sector question | Real corpus | PASS. FX + Rates; Fed Funds Rate and USD-SGD rows. |
| Forecast revision / unresolved conflict | **Fixture only** | PASS on fixtures. The real 7-day corpus has a single forecast-table set, so there was nothing to revise. |
| Different source dates in one answer | Real corpus | PASS. Sources from 26, 28 and 30 Oct with per-source freshness (Recent 6d / Older 4d / Recent 2d) and a mixed-date note. |
| Scanned / difficult document | Real image-only pages + fixture full scan | PASS. Real WMV and Credit Week in Brief pages OCR'd and flagged. A fully scanned report exists only as a fixture. |
| Unavailable research section | **Fixture** (all 29 real checks succeeded) | PASS. Failed section disclosed and coverage marked incomplete. The real Equity Research section had no in-window publications, which the answer reports. |
| Request to browse the web | Real corpus | PASS. Notice shown; answer only from OCBC PDFs. |
| Request for an original investment idea | Real corpus | PASS. Notice shown; no unsourced recommendation language. |
| Malicious instructions in a document | **Fixture only** (0 in real corpus) | PASS. Flagged at ingestion, withheld, never quoted. |
| Attempted orchestrator corpus-access call | Live HTTP + process policy | PASS. 401/403/404 on every probe; in-process attempts denied. |
| Attempted specialist user-facing message | Contract + routing | PASS. Rejected by strict schema; no gateway route. |

## Manual / UI verification (built-in browser)

* **Desktop (1360×860).** Empty state with suggestions. Live progress steps ("Reviewing FX research"). Answer card with status, mode and specialist badges; the four-date strip; forecast table with right-aligned tabular numbers and calendar/relative groups; verbatim source notes; rationale with source, date and freshness meta; sources list.
* **Source drawer.** A citation opens the drawer showing the dates (listing, printed, data date), freshness rule, page and document ID. The rendered page shows the cited USD-SGD row highlighted (FX Weekly p.6). "Open PDF at page 6" and "Original on ocbc.com" links are present.
* **Mobile (375×812).** No horizontal page scroll (document width 375 = viewport). The table scrolls inside its card. Header and freshness wrap. Navigation sits behind the menu button.
* **Admin / corpus status.** Summary cards, coverage by specialist, freshness policy, refresh and explicit window controls, cron schedule, section checks, documents with date basis and flags, excluded list.
* **Error states.**
  * Specialist service stopped: "The research service is unavailable … No answer was generated", and the other services kept running.
  * Validator stopped: the answer was withheld rather than shown unvalidated.
  * Semantic model missing: lexical-only retrieval, disclosed.
  * Model credential missing: "Extractive mode" pill and sidebar note.
* **Admin API through the gateway.**
  * Cron `0 8 * * *` saved, next run 08:00 SGT. An invalid cron is rejected (400). The schedule was cleared afterwards.
  * An admin-triggered refresh ran with 25 unchanged, 106 excluded and no errors. A concurrent second refresh is rejected (409).

## Model-assisted mode (live Claude API)

After an API key was added, the stack was restarted in model-assisted mode (`claude-opus-5-5`) and all
**16/16** end-to-end scenarios passed again. On the USD/SGD question (13.5 s):

* The 8 forecast values were unchanged.
* Model sentences named and dated their source reports.
* The validator rejected one model sentence the evidence did not support, and it was dropped.

Refusal and API-error fallbacks were not triggered.

## Not tested / unavailable conditions
* **Real-site failure modes.** Inaccessible documents, a failing section, quarantined dates, duplicates and malicious documents did not occur on the live site in this window. They are covered only by fixtures.
* **Browsers.** No cross-browser testing beyond the built-in Chromium pane. No screen-reader audit.
