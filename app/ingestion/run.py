"""CLI: python -m app.ingestion.run [--days N] [--reindex [--reparse]]

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
    args = ap.parse_args()
    install_ingestion_guard()
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
