#!/usr/bin/env python3
"""Bulk-ingest a folder of documents into PSK Bot.

Usage:
    python scripts/bulk_ingest.py /path/to/folder
    python scripts/bulk_ingest.py /path/to/folder --name "AlgoSec Docs"

Supported file types: PDF, DOCX, TXT, MD, HTML, HTM, XLS, XLSX, images.
Each file becomes a separate document with its own vector store.
"""

import os
import sys
import time
import argparse
from pathlib import Path

# ── Environment setup ──────────────────────────────────────────────────
env_defaults = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "TOKENIZERS_PARALLELISM": "false",
    "FAISS_DISABLE_GPU": "1",
    "KMP_DUPLICATE_LIB_OK": "TRUE",
}
for key, val in env_defaults.items():
    os.environ.setdefault(key, val)

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from psk_bot.ingestion.parsers import parse_document, get_supported_extensions
from psk_bot.ingestion.pipeline import chunk_text
from psk_bot.logging import get_logger
from psk_bot.services.document_manager import get_document_manager, DocumentManager
from psk_bot.services.vector_store import VectorStoreService
from psk_bot.settings import settings

logger = get_logger(__name__)


def collect_files(folder: Path) -> list[Path]:
    """Recursively collect all supported files from a folder."""
    supported = {ext.lower() for ext in DocumentManager.SUPPORTED_EXTENSIONS}
    files = []
    for root, _dirs, filenames in os.walk(folder):
        for fname in sorted(filenames):
            fpath = Path(root) / fname
            if fpath.suffix.lower() in supported:
                files.append(fpath)
    return files


def ingest_one(file_path: Path, display_prefix: str = "") -> bool:
    """Ingest a single file: create doc entry, parse, chunk, vectorise."""
    doc_manager = get_document_manager()

    # Build display name
    stem = file_path.stem.replace("_", " ").replace("-", " ").title()
    display_name = f"{display_prefix}{stem}" if display_prefix else stem

    # Read file content
    file_content = file_path.read_bytes()
    valid, err = doc_manager.validate_file(file_path.name, len(file_content))
    if not valid:
        logger.warning("Skipping %s: %s", file_path.name, err)
        return False

    doc_info = doc_manager.create_document(
        filename=file_path.name,
        file_content=file_content,
        display_name=display_name,
    )
    doc_id = doc_info.id

    try:
        doc_manager.update_status(doc_id, "processing")

        # Step 1: Parse
        doc_file = doc_manager.get_document_file_path(doc_id)
        text = parse_document(doc_file)
        if not text or len(text.strip()) < 50:
            raise ValueError("Document contains too little text")

        # Step 2: Chunk
        chunks = chunk_text(
            text,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        if not chunks:
            raise ValueError("No chunks created from document")

        # Step 3: Vectorise
        vs = VectorStoreService(config=settings, doc_id=doc_id)
        documents = [{"content": c, "doc_id": doc_id} for c in chunks]
        vs.add_documents(documents)

        doc_manager.update_status(doc_id, "ready", chunk_count=len(chunks))
        logger.info(
            "✓ %s  →  %d chunks  (%d chars)",
            file_path.name,
            len(chunks),
            len(text),
        )
        return True

    except Exception as exc:
        doc_manager.update_status(doc_id, "failed", error_message=str(exc))
        logger.error("✗ %s  →  %s", file_path.name, exc)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-ingest a folder of documents into PSK Bot."
    )
    parser.add_argument("folder", type=Path, help="Path to folder containing documents")
    parser.add_argument(
        "--name",
        default="",
        help="Optional prefix for display names (e.g. 'AlgoSec - ')",
    )
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory")
        sys.exit(1)

    files = collect_files(folder)
    if not files:
        print(f"No supported files found in {folder}")
        print(f"Supported extensions: {', '.join(sorted(DocumentManager.SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    print(f"\nFound {len(files)} file(s) in {folder}")
    print(f"Supported extensions: {', '.join(sorted(DocumentManager.SUPPORTED_EXTENSIONS))}")
    print("-" * 60)

    start = time.perf_counter()
    success = 0
    failed = 0

    for i, fpath in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] {fpath.name} ({fpath.stat().st_size / 1024:.0f} KB)")
        if ingest_one(fpath, display_prefix=args.name):
            success += 1
        else:
            failed += 1

    elapsed = time.perf_counter() - start
    print("\n" + "=" * 60)
    print(f"Completed in {elapsed:.1f}s")
    print(f"  ✓ Success: {success}")
    print(f"  ✗ Failed:  {failed}")
    print(f"  Total:     {len(files)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
