"""Publish the app plus the locally built corpus to a Hugging Face Space.

    hf auth login                                   # once, in your own terminal
    python scripts/deploy_space.py <user>/<space-name> [--private]

Uploads the project's source files and the current corpus (raw PDFs,
corpus.db and the active search collections). Never uploads .env,
conversation history, the embedding model (downloaded at image build) or
old collection builds. Secrets (ANTHROPIC_API_KEY, APP_PASSWORD) are added
by you in the Space settings, not by this script.

To refresh the hosted corpus: run `python -m app.ingestion.run` locally,
then run this script again."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPACE_README = """---
title: Research Desk
emoji: 📈
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Evidence-based answers from OCBC research PDFs
---

# Research Desk

OCBC research assistant: answers client questions from ingested OCBC research PDFs, with every value and
statement cited to a document page and validated before it is shown. The corpus in this Space is fixed
(see the Corpus status page for its window); the hosted demo does not crawl or refresh.

Source code: https://github.com/jaydenntann77/ocbcresearchagent
"""
EXCLUDE_PREFIXES = (".claude/", "data/", ".env")


def source_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split("\n")
    return [f for f in out if f and not f.startswith(EXCLUDE_PREFIXES) and (ROOT / f).is_file()]


def corpus_files() -> list[str]:
    data = ROOT / "data"
    pointer = data / "collections" / "current.json"
    if not (data / "corpus" / "corpus.db").exists() or not pointer.exists():
        sys.exit("No corpus found. Run `python -m app.ingestion.run` first.")
    files = ["data/corpus/corpus.db", "data/collections/current.json"]
    files += [f"data/collections/{fn}" for fn in json.loads(pointer.read_text())["files"].values()]
    files += [p.relative_to(ROOT).as_posix() for p in (data / "corpus" / "raw").glob("*.pdf")]
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("space", help="<user>/<space-name>, e.g. jaydenntann77/research-desk")
    ap.add_argument("--private", action="store_true", help="create the Space as private (visitors need HF access)")
    args = ap.parse_args()
    from huggingface_hub import HfApi
    api = HfApi()
    try:
        who = api.whoami()["name"]
    except Exception:  # noqa: BLE001
        sys.exit("Not logged in to Hugging Face. Run `hf auth login` in your terminal first.")
    print(f"Logged in to Hugging Face as {who}")
    files = source_files() + corpus_files()
    with tempfile.TemporaryDirectory(prefix="ra-space-") as tmp:
        stage = Path(tmp)
        for f in files:
            dest = stage / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, dest)
        (stage / "README.md").write_text(SPACE_README, encoding="utf-8")
        size = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file()) / 1e6
        print(f"Staged {len(files)} files ({size:.1f} MB)")
        api.create_repo(args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
        api.upload_folder(folder_path=str(stage), repo_id=args.space, repo_type="space",
                          commit_message="Deploy Research Desk with locally built corpus",
                          delete_patterns=["app/**", "frontend/**", "config/**", "tests/**", "data/**", "scripts/**"])
    print(f"Uploaded. Build logs and settings: https://huggingface.co/spaces/{args.space}")
    print("Add secrets in Settings -> Variables and secrets: ANTHROPIC_API_KEY (optional) and APP_PASSWORD.")


if __name__ == "__main__":
    main()
