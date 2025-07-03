# /rag-chatbot-ollama/scripts/ingest.py

import sys
import os

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pdf_parser import parse_pdf, chunk_text
from services.vector_store_service import VectorStoreService
from utils.logger import log
import config


def main():
    """Main ingestion script."""
    log.info("Starting ingestion process...")

    if not os.path.exists(config.PDF_PATH):
        log.error(f"PDF file not found at: {config.PDF_PATH}")
        log.error(
            "Please place your PDF in the 'data' directory and update 'config.py'."
        )
        return

    # 1. Parse PDF
    document_text = parse_pdf(config.PDF_PATH)
    if not document_text:
        log.error("Failed to extract text from PDF. Aborting.")
        return

    # 2. Chunk Text
    chunks = chunk_text(document_text)
    if not chunks:
        log.error("Failed to chunk text. Aborting.")
        return

    # 3. Create and Save Vector Store
    vector_store = VectorStoreService()
    vector_store.create_and_save_store(chunks)

    log.info("Ingestion process completed successfully!")


if __name__ == "__main__":
    main()
