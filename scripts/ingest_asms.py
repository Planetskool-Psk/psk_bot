#!/usr/bin/env python3
"""Bulk ingest ASMS HTM documentation files into per-document vector stores.

Usage:
    python scripts/ingest_asms.py /path/to/asms-help-folder
    python scripts/ingest_asms.py /path/to/asms-help-folder --max-files 10   # test run

This script:
  1. Discovers all HTM/HTML content files in the folder
  2. Parses each file using the existing parse_html parser
  3. Chunks text with the configured chunk_size / chunk_overlap
  4. Creates a per-document FAISS vector store for each
  5. Registers each document in the metadata.json
"""

import os
import sys
import time
from pathlib import Path

# ── Thread / memory safety (must be set before torch import) ──
for key, val in {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "TOKENIZERS_PARALLELISM": "false",
    "FAISS_DISABLE_GPU": "1",
    "KMP_DUPLICATE_LIB_OK": "TRUE",
    "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
}.items():
    os.environ.setdefault(key, val)

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json

from psk_bot.ingestion.parsers import parse_document
from psk_bot.ingestion.pdf import chunk_text
from psk_bot.logging import get_logger
from psk_bot.services.document_manager import DocumentManager
from psk_bot.services.vector_store import VectorStoreService
from psk_bot.settings import settings

logger = get_logger(__name__)


# ── File discovery ───────────────────────────────────────────────────────

SKIP_STEMS = {"index", "toc", "search", "glossary", "_csh", "template", "default"}
SKIP_DIRS = {"skins", "resources/scripts", "resources/stylesheets", "resources"}


def collect_files(folder: Path) -> list[Path]:
    """Recursively find content HTM/HTML files, skipping navigation stubs."""
    files = []
    for ext in ("*.htm", "*.html"):
        for f in folder.rglob(ext):
            # Skip navigation / framework files
            if any(pat in f.stem.lower() for pat in SKIP_STEMS):
                continue
            rel = str(f.relative_to(folder)).lower()
            if any(skip in rel for skip in SKIP_DIRS):
                continue
            # Skip tiny files (likely nav stubs)
            if f.stat().st_size < 500:
                continue
            files.append(f)
    return sorted(files)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bulk-ingest ASMS HTM docs")
    parser.add_argument("input_folder", type=Path, help="Folder with HTM/HTML files")
    parser.add_argument("--max-files", type=int, default=0, help="Limit files (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no vector store")
    args = parser.parse_args()

    if not args.input_folder.exists():
        print(f"Error: folder not found: {args.input_folder}")
        sys.exit(1)

    # Discover files
    htm_files = collect_files(args.input_folder)
    if args.max_files:
        htm_files = htm_files[: args.max_files]
    print(f"Found {len(htm_files)} content files")

    if not htm_files:
        print("Nothing to ingest.")
        return

    # Init services
    doc_manager = DocumentManager(base_dir=PROJECT_ROOT)
    # Pre-load embedding model once (reused across all documents)
    print(f"Loading embedding model ({settings.embedding_model_name})...")
    embed_svc = VectorStoreService(config=settings)  # loads embedding model
    print("Embedding model ready.")

    print(f"Chunk config: size={settings.chunk_size}, overlap={settings.chunk_overlap}")

    t0 = time.perf_counter()
    stats = {"ingested": 0, "skipped": 0, "total_chunks": 0, "errors": []}

    for i, fpath in enumerate(htm_files, 1):
        stem = fpath.stem.replace("_", " ").replace("-", " ").title()
        tag = f"[{i}/{len(htm_files)}]"

        # ── 1. Parse ──
        try:
            text = parse_document(fpath)
        except Exception as e:
            msg = f"{tag} PARSE ERROR {fpath.name}: {e}"
            print(msg)
            stats["errors"].append(msg)
            stats["skipped"] += 1
            continue

        if not text or len(text.strip()) < 50:
            print(f"{tag} SKIP (too short) {fpath.name}")
            stats["skipped"] += 1
            continue

        # ── 2. Chunk ──
        chunks = chunk_text(text, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
        if not chunks:
            print(f"{tag} SKIP (no chunks) {fpath.name}")
            stats["skipped"] += 1
            continue

        if args.dry_run:
            print(f"{tag} DRY {stem}: {len(chunks)} chunks, {len(text)} chars")
            stats["ingested"] += 1
            stats["total_chunks"] += len(chunks)
            continue

        # ── 3. Register document ──
        file_content = fpath.read_bytes()
        doc_info = doc_manager.create_document(
            filename=fpath.name,
            file_content=file_content,
            display_name=stem,
        )

        # ── 4. Create per-document vector store ──
        try:
            vs = VectorStoreService(config=settings, doc_id=doc_info.id)
            # Reuse the already-loaded embedding model
            vs._embedding_model = embed_svc._embedding_model
            vs._use_ollama = embed_svc._use_ollama

            documents = [{"content": chunk, "doc_id": doc_info.id} for chunk in chunks]
            vs.add_documents(documents)

            doc_manager.update_status(doc_info.id, "ready", chunk_count=len(chunks))
            stats["ingested"] += 1
            stats["total_chunks"] += len(chunks)
            elapsed = time.perf_counter() - t0
            rate = stats["ingested"] / elapsed * 60 if elapsed > 0 else 0
            print(f"{tag} OK {stem}: {len(chunks)} chunks ({rate:.0f} docs/min)")

        except Exception as e:
            msg = f"{tag} VECTOR ERROR {fpath.name}: {e}"
            print(msg)
            stats["errors"].append(msg)
            doc_manager.update_status(doc_info.id, "failed", error_message=str(e))
            stats["skipped"] += 1

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*60}")
    print(f"Ingestion complete in {elapsed:.1f}s")
    print(f"  Ingested: {stats['ingested']}")
    print(f"  Skipped:  {stats['skipped']}")
    print(f"  Chunks:   {stats['total_chunks']}")
    if stats["errors"]:
        print(f"  Errors:   {len(stats['errors'])}")
        for e in stats["errors"][:10]:
            print(f"    - {e}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
