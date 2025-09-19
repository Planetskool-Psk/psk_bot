"""Document ingestion helper."""

import os
import sys
import time
from pathlib import Path

# Ensure project root on path when running as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import config
from gentari_bot.ingestion.pdf import chunk_text, parse_pdf
from gentari_bot.services import VectorStoreService
from utils.logger import log


def main() -> None:
    """Ingest PDF content into the vector store."""
    log.info("Starting ingestion process...")

    pdf_path = Path(config.PDF_PATH)
    if not pdf_path.exists():
        log.error("PDF file not found at: %s", pdf_path)
        log.error("Place your PDF in the 'data' directory or update the PDF_PATH env var.")
        return

    start = time.perf_counter()
    document_text = parse_pdf(pdf_path)
    if not document_text:
        log.error("Failed to extract text from PDF. Aborting.")
        return
    parse_time = time.perf_counter() - start
    log.info("PDF parsed in %.2f seconds", parse_time)

    chunks_start = time.perf_counter()
    chunks = chunk_text(document_text)
    if not chunks:
        log.error("Failed to chunk text. Aborting.")
        return
    chunk_time = time.perf_counter() - chunks_start
    log.info("Text chunked in %.2f seconds", chunk_time)

    vector_start = time.perf_counter()
    vector_store = VectorStoreService()
    vector_store.create_and_save_store(chunks)
    vector_time = time.perf_counter() - vector_start
    log.info("Vector store created and saved in %.2f seconds", vector_time)

    total_time = time.perf_counter() - start
    log.info("Ingestion completed successfully in %.2f seconds", total_time)


if __name__ == "__main__":
    main()
