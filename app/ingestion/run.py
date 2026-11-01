"""CLI: python -m app.ingestion.run [--days N]

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
    args = ap.parse_args()
    install_ingestion_guard()
    from app.ingestion.pipeline import run_ingestion
    summary = run_ingestion(days=args.days, trigger="cli")
    print(json.dumps({k: v for k, v in summary.items() if k != "collections"}, indent=2))


if __name__ == "__main__":
    main()
