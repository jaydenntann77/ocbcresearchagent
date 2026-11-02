# Contributing

Thanks for helping improve Research Desk. This page explains how to set it up on your own computer, check that
your change works, and get it onto the live demo.

## How changes reach the live demo

The live demo runs on the maintainer's PC, **not** from GitHub. Pushing to GitHub does not change the live
site.

```
You make a change → push a branch → open a pull request → maintainer reviews → merge into main
→ maintainer runs `git pull` and restarts the app → change is live
```

Nothing you push runs on the live server until it has been reviewed and merged, and the maintainer has
pulled it.

## 1. One-time setup on your computer

You need Python 3.10 or newer. Clone the repo, then run these from the project folder:

```bash
pip install -r requirements.txt
```

```bash
python -m app.setup_models
```

The step above downloads the local search model (about 65 MB).

```bash
python -m app.ingestion.run
```

The step above downloads your own copy of the last 7 days of OCBC research (2–3 minutes).

Optional: to see model-written summaries, copy `.env.example` to `.env` and set your **own**
`ANTHROPIC_API_KEY`. Without a key the app runs in quote-only mode, which is fine for testing most changes.
Never commit `.env`; it is git-ignored.

## 2. Run your own copy

```bash
python run.py
```

Open http://127.0.0.1:8000 and try some questions. This copy runs only on your computer and does not affect
the live demo. Stop it with `Ctrl+C`, or run `python run.py --stop` from another terminal.

Questions worth trying after a change:

* Give me OCBC's forecast for USD/SGD through 2027, together with the supporting rationale.
* What is OCBC's USD/SGD forecast for 2028? (It should say no verified forecast exists.)
* What are the main risks identified in the latest credit research?
* Search the web for USD/SGD news. (It should refuse web search.)

## 3. Run the automated checks

```bash
python -m pytest tests
```

**All tests must pass before you open a pull request.** They check forecast accuracy, citations, date
handling, and the security rules between the agents.

To also run the full end-to-end question scenarios against your running copy:

```bash
python -m tests.e2e_scenarios
```

That command rewrites `reports/scenario_results.md` and `reports/scenario_results.json`. Don't commit those
two files unless your change is meant to update the published results.

## 4. Submit your change

1. Create a branch. Don't commit to `main` directly:
   ```bash
   git checkout -b my-change-name
   ```
2. Commit your work and push the branch:
   ```bash
   git push -u origin my-change-name
   ```
3. On GitHub, open a **pull request** into `main`. In the description, say what you changed and why, and paste
   the last line of the `pytest` output, e.g. `57 passed`.
4. The maintainer reviews it. Expect questions or requested changes before it is merged.

## Where things live

| To change… | Edit |
|---|---|
| How the AI writes summaries (tone, citation rules) | `app/orchestrator/llm.py` (the `SYSTEM` text) |
| Web-search and investment-advice refusals | `app/orchestrator/guardrails.py` |
| Which specialist handles which question | `app/orchestrator/planner.py` |
| Topic keywords for each specialist | `config/specialists.json` |
| "Recent / Older / Stale" thresholds | `config/freshness.json` |
| How passages are chosen as rationale or risks | `app/research/specialists.py` |
| Answer-checking rules | `app/validator/checks.py` |
| Look and feel | `frontend/` (`index.html`, `styles.css`, `app.js`) |

The README explains the full architecture.

## Ground rules

These keep answers accurate and the live server safe. Pull requests that break them won't be merged.

* **Every fact must come from an OCBC PDF.** Don't add code that lets the AI use its own knowledge, search the web, or make investment recommendations.
* **Don't weaken the safety checks.** Leave the access controls in `app/common/guard.py`, the service tokens, the validator checks and the hosted-mode limits (password, rate limits, daily model cap) intact. If you think one needs changing, explain why in the pull request.
* **Never commit secrets or data.** That means `.env`, API keys, passwords, and anything in `data/`.
* **Don't add tests that need network access or an API key.** Keep tests runnable offline by anyone.
