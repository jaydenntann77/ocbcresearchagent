"""One-off setup step: download the local embedding model into data/models.
This is the only time the model host is contacted; answer-time services load
the model from disk with HF_HUB_OFFLINE=1."""
from app.common import config


def main():
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    from fastembed import TextEmbedding
    from app.common.embedding import MODEL_NAME
    model = TextEmbedding(MODEL_NAME, cache_dir=str(config.MODELS_DIR))
    vec = list(model.embed(["warm-up"]))[0]
    print(f"Embedding model {MODEL_NAME} ready in {config.MODELS_DIR} (dim={len(vec)})")
    try:
        from rapidocr_onnxruntime import RapidOCR
        RapidOCR()
        print("OCR engine (RapidOCR) ready")
    except Exception as exc:  # noqa: BLE001
        print(f"OCR engine unavailable: {exc}")


if __name__ == "__main__":
    main()
