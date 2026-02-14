#!/usr/bin/env python3
"""Enhanced ingestion script with safety checks and reporting."""

import shutil
import sys
from pathlib import Path

# Ensure project root on path when running directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from psk_bot.ingestion.pipeline import IngestionPipeline
from psk_bot.logging import get_logger
from psk_bot.services import VectorStoreService
from psk_bot.settings import settings

logger = get_logger(__name__)


def backup_existing_store(target: Path) -> None:
    if not target.exists():
        return
    backup_dir = target.with_name(f"{target.name}_backup")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(target, backup_dir)
    logger.info("Backed up existing vector store to %s", backup_dir)


def main() -> None:
    logger.info("Starting enhanced document ingestion...")
    logger.info("Chunking configuration: size=%s overlap=%s", settings.chunk_size, settings.chunk_overlap)

    pdf_path = Path(settings.pdf_path)
    if not pdf_path.exists():
        logger.error("PDF not found at %s", pdf_path)
        logger.info("Place your PDF file at that location or update the PDF_PATH env var.")
        return

    backup_existing_store(Path(settings.vector_store_dir))

    pipeline = IngestionPipeline()
    report = pipeline.run(pdf_path)
    if not report:
        logger.error("Ingestion failed.")
        return
    logger.info(
        "Generated %s chunks from %s characters in %.2fs",
        report.chunk_count,
        report.characters,
        report.elapsed_seconds,
    )

    vector_store = VectorStoreService()

    if not vector_store.load_store():
        logger.error("Failed to load the enhanced vector store")
        return

    sample_queries = [
        "company policy",
        "employee benefits",
        "vacation time",
        "working hours",
    ]
    logger.info("Testing search quality with sample queries:")
    for query in sample_queries:
        results = vector_store.search(query, k=2)
        if results:
            relevance = results[0].get("relevance", results[0].get("similarity", 0))
            logger.info("  '%s': %s results (best relevance %.3f)", query, len(results), relevance)
        else:
            logger.info("  '%s': No results", query)

    logger.info("Enhanced document ingestion completed. Restart the chatbot to use the new index.")


if __name__ == "__main__":
    main()
