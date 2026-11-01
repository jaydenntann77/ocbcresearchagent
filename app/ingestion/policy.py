from app.common import config, guard


def install_ingestion_guard():
    """The ingestion service may reach only the OCBC website (plus loopback).
    It owns the corpus directories, so it has no filesystem restriction there,
    but it cannot read orchestrator conversation storage."""
    guard.install(guard.Policy(
        role="ingestion",
        denied_roots=[config.ORCH_DIR],
        allowed_hosts=set(config.OCBC_ALLOWED_HOSTS),
        block_subprocess=True,
    ))
