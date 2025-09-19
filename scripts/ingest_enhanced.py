#!/usr/bin/env python3
"""Enhanced ingestion script with safety checks and reporting."""

import shutil
import sys
from pathlib import Path

# Ensure project root on path when running directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import config
from gentari_bot.ingestion.pdf import chunk_text, parse_pdf
from gentari_bot.services import VectorStoreService
from utils.logger import log


def backup_existing_store(target: Path) -> None:
    if not target.exists():
        return
    backup_dir = target.with_name(f"{target.name}_backup")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(target, backup_dir)
    log.info("Backed up existing vector store to %s", backup_dir)


def main() -> None:
    log.info("Starting enhanced document ingestion...")
    log.info("Chunking configuration: size=%s overlap=%s", config.CHUNK_SIZE, config.CHUNK_OVERLAP)

    pdf_path = Path(config.PDF_PATH)
    if not pdf_path.exists():
        log.error("PDF not found at %s", pdf_path)
        log.info("Place your PDF file at that location or update the PDF_PATH env var.")
        return

    backup_existing_store(Path(config.VECTOR_STORE_DIR))

    text = parse_pdf(pdf_path)
    if not text:
        log.error("No text extracted from PDF")
        return
    log.info("Extracted %s characters from %s", len(text), pdf_path.name)

    chunks = chunk_text(text)
    if not chunks:
        log.error("No text chunks generated from PDF")
        return
    log.info("Generated %s text chunks (avg length %.0f)", len(chunks), sum(len(chunk) for chunk in chunks) / len(chunks))

    vector_store = VectorStoreService()
    vector_store.create_and_save_store(chunks)

    if not vector_store.load_store():
        log.error("Failed to load the enhanced vector store")
        return

    sample_queries = [
        "company policy",
        "employee benefits",
        "vacation time",
        "working hours",
    ]
    log.info("Testing search quality with sample queries:")
    for query in sample_queries:
        results = vector_store.search(query, k=2)
        if results:
            relevance = results[0].get("relevance", results[0].get("similarity", 0))
            log.info("  '%s': %s results (best relevance %.3f)", query, len(results), relevance)
        else:
            log.info("  '%s': No results", query)

    log.info("Enhanced document ingestion completed. Restart the chatbot to use the new index.")


if __name__ == "__main__":
    main()
