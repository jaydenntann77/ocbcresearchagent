# Research Desk: OCBC research assistant for salespeople

Research Desk answers client-driven research questions from **OCBC research PDFs only**.
For a question such as *"Give me OCBC's forecast for USD/SGD through 2027, together with the supporting
rationale"*, the orchestrator plans the work, sends a structured task to the FX specialist (and to others only
when the question needs them), and then validates the returned evidence. The answer you get back has these parts:

* the forecast table, with the source's exact values and its original horizon labels (`Dec-26` … `Dec-27`, `3M/6M/12M`)
* the source's own qualifications, quoted verbatim, e.g. *"not meant to serve as point forecast … but … trajectory bias"*
* the data date the source states, e.g. *"Latest Forecast Update: 25 September 2026"*
* dated rationale excerpts. Each citation opens the source PDF page with the excerpt highlighted.
* a clear statement of what is missing, conflicting or stale

The current corpus was ingested on **1 Nov 2026 (SGT)** and covers **26 October – 1 November 2026**.
It holds 25 documents (see [reports/ingestion_report.md](reports/ingestion_report.md)).

---

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python -m app.setup_models
```

The step above downloads the local embedding model. This is the only time the model host is contacted.

```bash
python -m app.ingestion.run
```

The step above runs the 7-day OCBC ingestion. It is safe to re-run.

```bash
python run.py
```

Open http://127.0.0.1:8000 for the workspace and http://127.0.0.1:8000/admin for corpus status.

`python run.py --stop` stops a running stack. Copy `.env.example` to `.env` to change settings.
Python 3.10+ is required. Everything runs locally and binds to 127.0.0.1 only. OCR uses RapidOCR (ONNX), so you
do not need Tesseract.

**Model credential (optional).** Without `ANTHROPIC_API_KEY` in `.env` the app runs in **extractive mode**:

* forecast values come straight from parsed tables
* direct answers use fixed templates around those values
* rationale and risks are **verbatim** sentences from the PDFs

That is still a complete, validated answer, but nobody writes a synthesis. Set `ANTHROPIC_API_KEY` in `.env` and
restart to switch on **model-assisted synthesis**, which works like this:

* it uses `claude-opus-5-5` with structured JSON output and server-side refusal fallback, and has no tools
* the model sees only specialist evidence, wrapped as untrusted data
* every model sentence must cite evidence IDs and goes through the validator; failing sentences are dropped

The UI shows which mode is active. The model path was verified live on 1 Nov 2026: all 16 end-to-end
scenarios pass in model-assisted mode, and the validator removed model sentences the evidence did not support.
A question costs roughly US$0.05–0.10 on Opus 5.5 (estimate from token counts, not metered).

---

## Architecture

```
 Browser ──► Gateway :8000 ──► Conversation API / Orchestrator :8100 ──► Specialist service :8101 (FX, Rates, Macro, Equities, Credit)
   │          (static UI,         │  plan → tasks → follow-up round          │  hybrid retrieval over its OWN collection only
   │           fixed proxy        │  compose → validate → answer             │  returns SpecialistResponse (signed evidence)
   │           routes)            └────────────────────────────────────────► Validator :8102 (verdicts only)
   ├──────────► Document viewer :8103 (page images with highlight, original PDF)  ◄── corpus (read-only)
   └──────────► Ingestion worker + admin :8104 ── the ONLY process allowed to reach www.ocbc.com
                       │ writes
                       ▼
     data/corpus/raw/*.pdf  data/corpus/corpus.db  data/collections/{fx,rates,macro,equities,credit}-<build>.db
     data/orchestrator/conversations.db (the orchestrator's only storage)
```

| Component | Code | Responsibility |
|---|---|---|
| Frontend | `frontend/` | Research workspace, source drawer, copy actions, corpus status/admin view. Renders all text with `textContent`. |
| Gateway | `app/gateway/service.py` | Serves the UI. Proxies only `/api/chat`, `/api/meta`, `/api/conversations*`, `/api/docs/*`, `/api/admin/*`. Has **no route** to specialists or validator. |
| Orchestrator | `app/orchestrator/` | Guardrails (web/advice), planning (`planner.py`), specialist tasks, follow-up round, composition (`composer.py`), optional model synthesis (`llm.py`), conversation history. |
| Specialists | `app/research/` | Five agents in one service. Each gets handles only to its permitted collection (`config/specialists.json`). Exact forecast-cell lookup plus BM25/FTS5 and local-embedding retrieval with RRF fusion and exact-identifier boosting. |
| Validator | `app/validator/` | Deterministic checks of draft answer + evidence ledger against the corpus. Returns verdicts only. |
| Document viewer | `app/docs/` | Page PNG with the cited excerpt highlighted, original PDF (`#page=N`), document metadata. |
| Ingestion | `app/ingestion/` | Discovery, allow-listed fetching, validation, dedup, extraction (prose, tables, OCR), date resolution, chunking/routing, indexing, checkpoints, scheduler, admin API, report. |

### Agent access controls: how they are enforced (not by prompts)

| Boundary | Enforcement |
|---|---|
| Orchestrator cannot read the corpus | It is a separate OS process. `app/common/guard.py` installs CPython audit hooks plus an import blocker at startup, and these cannot be removed. They deny `open`/`listdir`/SQLite connects anywhere under `data/` except `data/orchestrator/`. They block imports of PDF, OCR, embedding and retrieval modules. They allow DNS only for the model API, and only when a key is configured. They allow loopback connections only to the specialist and validator ports. Subprocesses are blocked. |
| Orchestrator has no retrieval tools | The specialist service has exactly one agent endpoint, `POST /v1/tasks`. There is no search, chunk, document or embedding endpoint. Corpus text reaches the orchestrator only as evidence excerpts inside a validated `SpecialistResponse`. |
| Scoped credentials | `run.py` generates fresh tokens per launch and gives each process only the ones it needs (orchestrator→specialists, orchestrator→validator, gateway→orchestrator/docs/admin). The orchestrator holds no docs or admin token. |
| Evidence integrity | The specialist service HMAC-signs every evidence item with a key shared only with the validator. The validator rejects forged or altered evidence, then re-checks document, page, verbatim excerpt and forecast cell against the corpus. |
| Specialists cannot talk to the user | Wire contracts use `extra="forbid"`, so a `message_to_user` field fails validation. The gateway has no route to the specialist service. Progress messages ("Reviewing FX research") are fixed strings generated by the application. |
| Specialists only search their own collection | `CollectionRegistry.grant()` issues handles only for permitted collections. `open_for('fx','credit')` raises `CollectionAccessDenied`. |
| No internet at answer time | The specialist, validator, docs and gateway processes allow no external DNS. Only the ingestion process may resolve `www.ocbc.com`. |
| Ingestion stays inside OCBC research | Every URL and each redirect hop must be `https://www.ocbc.com` under `/group/research/` or `/iwov-resources/sg/ocbc/gbc/pdf/`. robots.txt is honoured. Requests are rate-limited (≥1 s apart) with bounded retries. No search engines. |

Audit hooks are defence in depth on top of process separation. Native code inside an allowed module could
still bypass them. For production, also run each service under its own OS account with filesystem ACLs and an
egress firewall.

---

## Ingestion

**Discovery.** The pipeline checks four sources:

* the research index page
* each category page
* the AJAX listing component that the category pages call: `POST /group/research/research-with-filter/<id>.ajax` with `monthParam/yearParam/category`, for every month overlapping the window. This returns the complete month; "See more" only pages on the client.
* the equity investment-reports page

**Window.** The window is computed at run time: N calendar dates ending today in Asia/Singapore, inclusive
(default N=7). A different N is recorded as an **expanded** window and shown in every answer banner.

**Eligibility** is decided by publication date, never by download date or HTTP `Last-Modified`. HTTP dates
are recorded for reference only.

**Date-resolution rule** (`app/ingestion/dates.py`). It uses two signals:

* **L**, the website listing date
* **P**, the printed date in the page-1 header

| Case | Outcome |
|---|---|
| L = P | high confidence |
| L and P differ by 1–3 days | P is used, medium confidence, flagged |
| L and P differ by more than 3 days | quarantined |
| L only | high if the PDF metadata date is within 3 days, else medium |
| P only | medium |
| neither | quarantined |

A PDF metadata title that carries a different date is flagged but never used. One DMO's metadata title says
"DMO 23 Apr 2026"; it is flagged.

**Validation and dedup.** Downloads are accepted only on the `%PDF-` signature plus a successful parse. HTML
served with a `.pdf` name is rejected. Documents are keyed by SHA-256 (`ocbc-<12 hex>`). Identical content at
another URL is recorded as an alias. New content at the same URL supersedes the old version, which is kept for
audit.

**Idempotent and resumable.** Item states are committed as they change. An interrupted run resumes. A re-run
reports `unchanged` and changes no records; this was verified on the real corpus.

**Extraction.**

* PyMuPDF, with a word-layout parser for forecast tables. Each cell keeps its instrument label, horizon label, exact string value, unit, group, table title, footnotes and stated data date.
* Spot or "Current" columns are stored as observations and never presented as forecasts.
* Generic tables become whole chunks; long ones are split by row with the header repeated.
* Image-only pages are OCR'd and flagged.
* Passages with instruction-like text are withheld from all collections.

**Routing.** Each section goes to its category's specialist. Multi-sector reports also go, section by
section, to any specialist whose lexicon score qualifies, with the original document ID and page kept.

**Refresh.** There is an admin "Refresh" button, an explicit "Run with this window" control (with a
confirmation), and a cron schedule (SGT) configurable in the admin view or with `RA_INGEST_SCHEDULE_CRON`.

## Answer rules implemented

* Forecast values are copied cell for cell. There is no interpolation, inversion or unit conversion. A request for SGD/USD reports that OCBC publishes USD-SGD and that the pair was not inverted.
* Requested horizons that are missing are reported with the exact wording "The ingested OCBC research does not contain a verified forecast for the … horizon". Relative horizons (3M/6M/12M) are shown as published and never mapped to dates.
* Conflicts:
  * The same instrument and horizon with different values in different reports is a revision only when the newer report states a later forecast-update date. Both sources stay in the explanation.
  * Otherwise both values are shown and the conflict is labelled **unresolved**.
  * Values are never averaged.
* Coverage statuses are kept distinct: no relevant information, document inaccessible, extraction failed, conflicting sources, horizon not covered.
* Web or browsing requests get a notice and are answered from the corpus only. Requests for original ideas or recommendations get a notice plus OCBC's published views. The validator blocks recommendation language that is not in the cited source.
* **Validation checks:**
  * evidence signature, document, page and verbatim excerpt
  * forecast-record match and row value/label/unit/scenario match
  * every number in a sentence present in its cited evidence
  * wording overlap for model summaries
  * recommendation language
  * currency-pair direction

  Failing statements are removed and the count is disclosed. If the validator is unreachable, the whole answer is withheld.

## Dates and freshness

Every answer shows four dates:

* source publication dates
* the corpus window
* the corpus refresh time
* the answer generation time

All are in SGT. Each source carries its own badge with age in days. Mixed-date answers say so, and passed
horizons are flagged separately. Freshness thresholds by report type live in `config/freshness.json` and are
shown in the UI:

| Report type | Recent | Older | Stale |
|---|---|---|---|
| Daily | ≤ 2 days | ≤ 7 days | beyond |
| Weekly | ≤ 7 days | ≤ 21 days | beyond |
| Thematic / event notes | ≤ 14 days | ≤ 45 days | beyond |
| Monthly / outlook | ≤ 31 days | ≤ 120 days | beyond |

"Date uncertain" is used whenever date confidence is low. These labels describe document age only; they are
not a judgement that a forecast is still valid.

---

## Hosting a demo on Hugging Face Spaces (free)

The hosted demo runs the same six services in one Docker container, with `RA_PUBLIC_MODE=1`. In that mode:

* **Fixed corpus.** It is built on your machine and uploaded with the app. The container never crawls OCBC; the ingest and schedule endpoints return 403.
* **Access password.** Visitors sign in with a shared password (`APP_PASSWORD`) and get a signed session cookie. Failed logins are throttled.
* **Private history.** Each visitor sees only their own conversations.
* **Limits.** Each visitor can ask 20 questions per hour. After 200 model-written summaries in a day (SGT), answers switch to quoting sources directly until the next day.
* **Network exposure.** Only the gateway listens on the network (0.0.0.0:7860). Every other service stays on 127.0.0.1 inside the container.

**First deployment:**

1. Create a free account at huggingface.co.
2. In your own terminal, run `hf auth login` and paste a token with *write* access.
3. Upload the app and the current corpus:
   ```bash
   python scripts/deploy_space.py <your-hf-username>/research-desk
   ```
4. On the Space page, open **Settings → Variables and secrets** and add these as **Secrets**:
   * `APP_PASSWORD`: the password you give your friends
   * `ANTHROPIC_API_KEY`: optional; without it the demo runs in extractive mode
5. The Space builds itself (about 5–10 minutes). Share the direct URL, `https://<username>-research-desk.hf.space`.

**To refresh the hosted corpus**, run `python -m app.ingestion.run` locally, then run the deploy script again.
The free tier sleeps after a period without visitors and wakes on the next visit. Conversation history
is lost when the Space restarts. Set a monthly spend limit in the Anthropic console.

---

## Tests

```bash
python -m pytest tests -v
```

This runs 56 automated tests:

* **Unit:** window, dates, freshness, horizons, pairs, planner, guardrails, injection detection
* **Real corpus (read-only):** exact cell values against PDF page words, date confidence, table integrity, routing, no duplicates
* **Boundaries:** subprocesses install the real service policies and attempt forbidden operations
* **Fixture scenarios:** a full offline pipeline run against a mocked OCBC site in an isolated temp corpus

```bash
python -m tests.e2e_scenarios
```

This runs 16 end-to-end scenarios against the live stack and real corpus and writes
[reports/scenario_results.md](reports/scenario_results.md).

Results are summarised in [reports/test_results.md](reports/test_results.md).

The development fixtures are synthetic PDFs marked "TEST FIXTURE":

* `tests/fixtures/make_fixtures.py` generates them
* `tests/fixtures/fixture_site.py` serves them from a mocked OCBC site

They are generated into a temporary `RA_DATA_DIR` with `RA_DEV_FIXTURE_CORPUS=1`. They are flagged
`dev_fixture=1` and never reach the real corpus, whose indexer only accepts `dev_fixture=0`.

## Verified example questions (real corpus, 26 Oct – 1 Nov 2026)

| Question | What you get |
|---|---|
| Give me OCBC's forecast for USD/SGD through 2027, together with the supporting rationale. | FX only. Dec-26 1.2700 · Mar-27 1.2670 · Jun-27 1.2630 · Sep-27 1.2610 · Dec-27 1.2550, plus 3M 1.27 · 6M 1.27 · 12M 1.26 (FX Weekly 26 Oct, p.6–7, forecast update 25 Sep). Qualification notes are verbatim. Rationale comes from DMOs dated 28–30 Oct. |
| What is OCBC's USD/SGD forecast for 2028? | No values. "The ingested OCBC research does not contain a verified forecast for the 2028 horizon (USDSGD)." |
| How do OCBC's Fed funds rate forecasts and USD/SGD forecasts fit together? | FX + Rates. Fed Funds Rate 3M/6M/12M 4.25 alongside the USD-SGD rows. |
| What are the main risks identified in the latest credit research? | Credit. Issuer-level risks from the Daily Credit Snapshots, cited. |
| What is OCBC's latest view on JPY and the BoJ? | FX + Rates. FX Weekly's medium-term JPY view and DTO/WMV notes on the BoJ. |
| What is OCBC's latest equity research view on Singapore REITs? | No verified evidence. Equity Research published nothing in the window, and the answer says so. |

## Known limitations and unresolved blockers

* **Model summaries depend on wording overlap.** The validator checks model sentences for cited numbers, pair direction, recommendation language and at least 60% word overlap with the cited excerpts. That catches added facts and figures, but a fluent paraphrase that shifts emphasis can still pass. Extractive mode (no key) avoids this entirely.
* **Scenarios that the real 7-day corpus does not contain** were verified only on isolated fixtures:
  * forecast revisions and unresolved conflicts (the window holds one forecast-table set)
  * a fully scanned document (only image-only divider and chart pages were OCR'd)
  * an unavailable listing section (all 29 checks succeeded)
  * a document with embedded malicious instructions (0 flagged)
* **Equities coverage gap.** No equity research was published in the window. Answers report this instead of widening the date range.
* **Narrative selection is heuristic.** Ranking uses retrieval score, entity mentions and view/risk phrasing. Findings are always verbatim and cited, but relevance can vary. Some answers include a headline-style sentence, or few excerpts (e.g. SGD rates returns 2).
* **OCR of chart pages yields noisy text.** It is flagged, and chart images are not interpreted.
* **The forecast-table parser** is tuned to OCBC's word-layout tables (period-header detection). An unusual table layout would fall back to a generic table, with no forecast cells extracted.
* **Process guards are defence in depth.** They are not an OS sandbox; see the access-control note above. Users are not authenticated, because this is a local single-user deployment bound to 127.0.0.1.
* **The scheduler runs only while the ingestion service is up.**
* **Not published.** Nothing has been published externally or sent to clients.
