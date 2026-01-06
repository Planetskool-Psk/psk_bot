"""Composable ingestion pipeline for building the vector store."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from gentari_bot.logging import get_logger
from gentari_bot.services.vector_store import VectorStoreService
from gentari_bot.settings import AppSettings, settings

from .pdf import chunk_text, parse_pdf

logger = get_logger(__name__)


@dataclass
class IngestionReport:
    source: Path
    chunk_count: int
    characters: int
    elapsed_seconds: float
    parse_seconds: float
    chunk_seconds: float
    vector_seconds: float

    def as_dict(self) -> dict:
        return {
            "source": str(self.source),
            "chunk_count": self.chunk_count,
            "characters": self.characters,
            "elapsed_seconds": self.elapsed_seconds,
            "parse_seconds": self.parse_seconds,
            "chunk_seconds": self.chunk_seconds,
            "vector_seconds": self.vector_seconds,
        }


class IngestionPipeline:
    """Run parsing, chunking and vector store building as a single pipeline."""

    def __init__(
        self,
        *,
        config: AppSettings = settings,
        vector_store: Optional[VectorStoreService] = None,
    ) -> None:
        self._config = config
        self._vector_store = vector_store or VectorStoreService(config=config)

    def run(self, pdf_path: Path) -> Optional[IngestionReport]:
        start = time.perf_counter()
        parse_start = start
        text = parse_pdf(pdf_path)
        if not text:
            logger.error("No text extracted from %s", pdf_path)
            return None
        parse_time = time.perf_counter() - parse_start

        chunk_start = time.perf_counter()
        chunks = chunk_text(text)
        if not chunks:
            logger.error("Chunking failed for %s", pdf_path)
            return None
        chunk_time = time.perf_counter() - chunk_start

        vector_start = time.perf_counter()
        self._vector_store.create_and_save_store(chunks, batch_size=self._config.embedding_batch_size)
        vector_time = time.perf_counter() - vector_start

        elapsed = time.perf_counter() - start
        logger.info(
            "Ingestion completed in %.2fs (parse %.2fs | chunk %.2fs | vector %.2fs)",
            elapsed,
            parse_time,
            chunk_time,
            vector_time,
        )

        return IngestionReport(
            source=pdf_path,
            chunk_count=len(chunks),
            characters=len(text),
            elapsed_seconds=elapsed,
            parse_seconds=parse_time,
            chunk_seconds=chunk_time,
            vector_seconds=vector_time,
        )
