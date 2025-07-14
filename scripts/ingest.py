# /rag-chatbot-ollama/scripts/ingest.py

import sys
import os

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pdf_parser import parse_pdf, chunk_text
from services.vector_store_service import VectorStoreService
from utils.logger import log
import config



import time

def main():
    """Main ingestion script with performance timing."""
    log.info("Starting ingestion process...")

    if not os.path.exists(config.PDF_PATH):
        log.error(f"PDF file not found at: {config.PDF_PATH}")
        log.error(
            "Please place your PDF in the 'data' directory and update 'config.py'."
        )
        return

    # 1. Parse PDF
    t0 = time.perf_counter()
    document_text = parse_pdf(config.PDF_PATH)
    t1 = time.perf_counter()
    parse_time = t1 - t0
    if not document_text:
        log.error("Failed to extract text from PDF. Aborting.")
        return
    log.info(f"PDF parsed in {parse_time:.2f} seconds.")
    if parse_time > 5:
        log.warning(f"PDF parsing took longer than 5 seconds: {parse_time:.2f}s")

    # 2. Chunk Text
    t2 = time.perf_counter()
    chunks = chunk_text(document_text)
    t3 = time.perf_counter()
    chunk_time = t3 - t2
    if not chunks:
        log.error("Failed to chunk text. Aborting.")
        return
    log.info(f"Text chunked in {chunk_time:.2f} seconds.")
    if chunk_time > 5:
        log.warning(f"Text chunking took longer than 5 seconds: {chunk_time:.2f}s")

    # 3. Create and Save Vector Store
    t4 = time.perf_counter()
    vector_store = VectorStoreService()
    vector_store.create_and_save_store(chunks)
    t5 = time.perf_counter()
    vector_time = t5 - t4
    log.info(f"Vector store created and saved in {vector_time:.2f} seconds.")
    if vector_time > 5:
        log.warning(f"Vector store creation took longer than 5 seconds: {vector_time:.2f}s")

    total_time = t5 - t0
    log.info(f"Ingestion process completed successfully in {total_time:.2f} seconds!")
    if total_time > 5:
        log.warning(f"Total ingestion time exceeded 5 seconds: {total_time:.2f}s")


if __name__ == "__main__":
    main()
