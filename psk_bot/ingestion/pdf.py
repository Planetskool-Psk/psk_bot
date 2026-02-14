"""PDF ingestion utilities."""

from pathlib import Path
from typing import List, Optional, Union

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from psk_bot.logging import get_logger
from psk_bot.settings import settings

logger = get_logger(__name__)


def parse_pdf(file_path: Union[str, Path]) -> Optional[str]:
    """Extract text from the provided PDF path."""
    path = Path(file_path)
    logger.info("Parsing PDF: %s", path)
    try:
        reader = PdfReader(str(path))
        text = "".join(filter(None, (page.extract_text() for page in reader.pages)))
        logger.info("Extracted %s characters from %s", len(text), path.name)
        return text
    except Exception:  # noqa: BLE001 - upstream library raises several exception types
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
