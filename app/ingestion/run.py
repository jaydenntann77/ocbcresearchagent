"""CLI: python -m app.ingestion.run [--days N] [--reindex [--reparse]] [--add-pdf FILE --title T --date D]

Runs an ingestion under the ingestion service's network policy (OCBC
research boundary + loopback only)."""
from __future__ import annotations

import argparse
import json

from app.ingestion.policy import install_ingestion_guard


def main():
    ap = argparse.ArgumentParser(description="Ingest OCBC research PDFs published in the window.")
    ap.add_argument("--days", type=int, default=None,
                    help="window length in calendar days ending today SGT (default from RA_INGEST_WINDOW_DAYS=7). "
                         "Any other value is recorded and displayed as an explicit expansion.")
    ap.add_argument("--reindex", action="store_true",
                    help="don't crawl: recompute forecast keys and rebuild the search collections for the current window")
    ap.add_argument("--reparse", action="store_true",
                    help="with --reindex: re-extract every stored PDF first, so parser changes take effect")
    ap.add_argument("--add-pdf", metavar="FILE",
                    help="add a PDF that is not on the OCBC website; needs --title and --date")
    ap.add_argument("--title", help="with --add-pdf: report title as it should appear in answers")
    ap.add_argument("--date", help="with --add-pdf: publication date, YYYY-MM-DD")
    ap.add_argument("--category", help="with --add-pdf: e.g. 'Macro Views' (steers desk routing)")
    ap.add_argument("--section", help="with --add-pdf: e.g. 'Monthly Monitor'")
    ap.add_argument("--subcategory", help="with --add-pdf: e.g. 'researchmonitor' (sets the report type)")
    ap.add_argument("--ocr", action="store_true", help="with --add-pdf: the text came from OCR; flag every page")
    args = ap.parse_args()
    install_ingestion_guard()
    if args.add_pdf:
        from datetime import date
        from app.ingestion.pipeline import add_manual_pdf
        if not (args.title and args.date):
            ap.error("--add-pdf needs --title and --date")
        state = add_manual_pdf(args.add_pdf, args.title, date.fromisoformat(args.date), args.category,
                               args.section, args.subcategory, ocr=args.ocr)
        raise SystemExit(0 if state in ("indexed", "unchanged") else 1)
    if args.reindex:
        from app.ingestion.pipeline import reindex
        result = reindex(reparse=args.reparse)
        print(json.dumps({"window": result["window"]}, indent=2))
        return
    from app.ingestion.pipeline import run_ingestion
    summary = run_ingestion(days=args.days, trigger="cli")
    print(json.dumps({k: v for k, v in summary.items() if k != "collections"}, indent=2))


if __name__ == "__main__":
    main()
