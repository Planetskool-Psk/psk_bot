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
    
    Uses hierarchical separators to preserve natural text boundaries:
    sections → paragraphs → sentences → words.
    
    Args:
        text: The text to chunk
        chunk_size: Size of each chunk (defaults to settings.chunk_size)
        overlap: Overlap between chunks (defaults to settings.chunk_overlap)
    """
    effective_chunk = chunk_size or settings.chunk_size
    effective_overlap = overlap or settings.chunk_overlap
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=effective_chunk,
        chunk_overlap=effective_overlap,
        length_function=len,
        separators=[
            "\n\n\n",   # major sections
            "\n\n",      # paragraphs
            "\n",        # lines
            ". ",        # sentences
            "; ",        # clauses
            ", ",        # phrases
            " ",         # words
            "",          # characters (last resort)
        ],
    )
    chunks = splitter.split_text(text)
    
    # Filter out very short chunks that add noise
    min_chunk_len = 80
    filtered = [c for c in chunks if len(c.strip()) >= min_chunk_len]
    
    logger.info("Split text into %d chunks (%d dropped as too short)",
                len(filtered), len(chunks) - len(filtered))
    return filtered
