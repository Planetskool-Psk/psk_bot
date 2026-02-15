"""PDF ingestion utilities."""

from pathlib import Path
from typing import List, Optional, Union

from langchain_text_splitters import RecursiveCharacterTextSplitter

from psk_bot.logging import get_logger
from psk_bot.settings import settings

logger = get_logger(__name__)


def parse_pdf(file_path: Union[str, Path]) -> Optional[str]:
    """Extract text from PDF — delegates to the OCR-capable parser in parsers.py."""
    from psk_bot.ingestion.parsers import parse_pdf as _parse_pdf_ocr

    path = Path(file_path)
    logger.info("Parsing PDF: %s", path)
    try:
        text = _parse_pdf_ocr(path)
        return text if text else None
    except Exception:
        logger.exception("Failed to parse PDF %s", path)
        return None


def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
    """Split text into semantically meaningful chunks.
    
    Args:
        text: The text to chunk
        chunk_size: Size of each chunk (defaults to settings.chunk_size)
        overlap: Overlap between chunks (defaults to settings.chunk_overlap)
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.chunk_size,
        chunk_overlap=overlap or settings.chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_text(text)
    logger.info("Split text into %s chunks", len(chunks))
    return chunks
