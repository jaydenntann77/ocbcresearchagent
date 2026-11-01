# Hosted demo image (Hugging Face Spaces, Docker SDK).
# The corpus is built on the administrator's machine and shipped in data/;
# the container never crawls OCBC (RA_PUBLIC_MODE=1 disables ingestion).
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Spaces run containers as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .
# Local embedding model, fetched once at build time; runtime is offline.
RUN python -m app.setup_models

ENV RA_PUBLIC_MODE=1 \
    RA_GATEWAY_HOST=0.0.0.0 \
    RA_GATEWAY_PORT=7860
EXPOSE 7860
CMD ["python", "run.py"]
