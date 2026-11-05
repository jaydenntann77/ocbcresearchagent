"""Local embedding model (BAAI/bge-small-en-v1.5 via fastembed/ONNX).
Runs fully offline from data/models once `python -m app.setup_models` has
downloaded it. Used by the ingestion (indexing) and research (query) services
only. If unavailable, retrieval falls back to lexical-only and says so."""
from __future__ import annotations

import os
import threading

import numpy as np

from app.common import config

MODEL_NAME = "BAAI/bge-small-en-v1.5"
_lock = threading.Lock()
_model = None
_error: str | None = None


def _load():
    global _model, _error
    with _lock:
        if _model is not None or _error is not None:
            return
        try:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from fastembed import TextEmbedding
            _model = TextEmbedding(MODEL_NAME, cache_dir=str(config.MODELS_DIR), local_files_only=True)
        except Exception as exc:  # noqa: BLE001
            _error = f"embedding model unavailable ({type(exc).__name__}: {exc}); semantic retrieval disabled"


def available() -> bool:
    _load()
    return _model is not None


def error() -> str | None:
    _load()
    return _error


def embed(texts: list[str], query: bool = False) -> np.ndarray | None:
    _load()
    if _model is None:
        return None
    if query:
        vecs = list(_model.query_embed(texts))
    else:
        # Small batches keep peak memory low: long passages in large batches
        # can exhaust RAM in the attention layers ("bad allocation").
        vecs = list(_model.passage_embed(texts, batch_size=16))
    arr = np.asarray(vecs, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-9, None)
