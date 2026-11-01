"""Source document viewer (port 8103) - serves the salesperson's browser via
the gateway only (gateway token). Renders PDF pages with excerpt highlights
and serves original PDFs. The orchestrator cannot reach this service: its
process policy forbids connecting to this port and it holds no token."""
from __future__ import annotations

import json
import re
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import Response

from app.common import config, guard

guard.install(guard.Policy(
    role="docs",
    denied_roots=[config.ORCH_DIR, config.COLLECTIONS_DIR],
    read_only_roots=[config.DATA_DIR / "corpus"],
    allowed_hosts=set(),
))

import fitz  # noqa: E402

from app.common.freshness import label as freshness_label  # noqa: E402
from app.common.security import require_token  # noqa: E402

app = FastAPI(title="Document viewer", docs_url=None, redoc_url=None, openapi_url=None)
auth = require_token(config.TOKEN_GATEWAY_DOCS)
DOC_ID_RE = re.compile(r"^[a-z0-9\-]{6,40}$")


def _conn():
    conn = sqlite3.connect(f"file:{config.META_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _doc(doc_id: str) -> dict:
    if not DOC_ID_RE.match(doc_id):
        raise HTTPException(400, "invalid document id")
    with _conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "document not found")
    return dict(row)


@app.get("/v1/health")
def health():
    return {"ok": True}


@app.get("/v1/documents/{doc_id}", dependencies=[Depends(auth)])
def document(doc_id: str):
    d = _doc(doc_id)
    with _conn() as conn:
        pages = [dict(r) for r in conn.execute(
            "SELECT pdf_page, printed_page, ocr, ocr_failed FROM pages WHERE doc_id=? ORDER BY pdf_page", (doc_id,))]
    return {
        "doc_id": d["doc_id"], "title": d["title"], "author": d["author"], "category": d["category"],
        "section": d["section"], "report_type": d["report_type"], "source_url": d["source_url"],
        "alias_urls": json.loads(d["alias_urls"]), "publication_date": d["publication_date"],
        "listing_date": d["listing_date"], "printed_date": d["printed_date"], "meta_date": d["meta_date"],
        "date_confidence": d["date_confidence"], "date_basis": d["date_basis"], "date_flags": json.loads(d["date_flags"]),
        "page_count": d["page_count"], "sha256": d["sha256"], "status": d["status"], "pages": pages,
        "freshness": freshness_label(d["publication_date"], d["report_type"], d["date_confidence"]),
        "dev_fixture": bool(d["dev_fixture"]),
    }


@app.get("/v1/documents/{doc_id}/pages/{page}.png", dependencies=[Depends(auth)])
def page_image(doc_id: str, page: int, q: str | None = Query(default=None, max_length=4000), dpi: int = 110):
    d = _doc(doc_id)
    if page < 1 or page > (d["page_count"] or 0):
        raise HTTPException(404, "page not found")
    with fitz.open(d["raw_path"]) as pdf:
        p = pdf[page - 1]
        if q:
            for part in re.split(r"\n|(?<=[.;:])\s+", q):
                words = part.replace(" | ", " ").split()
                for size in (10, 6, 4):
                    if len(words) < 3:
                        break
                    found = False
                    for start in range(0, max(1, len(words) - size + 1), size):
                        phrase = " ".join(words[start:start + size])
                        for rect in p.search_for(phrase):
                            annot = p.add_highlight_annot(rect)
                            annot.set_colors(stroke=(1, 0.85, 0.2))
                            annot.update()
                            found = True
                    if found:
                        break
        pix = p.get_pixmap(dpi=max(60, min(dpi, 200)), annots=True)
    return Response(pix.tobytes("png"), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@app.get("/v1/documents/{doc_id}/pdf", dependencies=[Depends(auth)])
def pdf(doc_id: str):
    d = _doc(doc_id)
    with open(d["raw_path"], "rb") as fh:
        data = fh.read()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc_id}.pdf"'})
