"""Document parsers for different file types."""

from pathlib import Path
from typing import Optional

from psk_bot.logging import get_logger

logger = get_logger(__name__)


def parse_pdf(file_path: Path) -> str:
    """Parse PDF file and extract text."""
    try:
        from pypdf import PdfReader
        
        reader = PdfReader(str(file_path))
        text_parts = []
        
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"[Page {page_num}]\n{page_text}")
        
        text = "\n\n".join(text_parts)
        logger.info("Parsed PDF: %s (%d pages, %d chars)", file_path.name, len(reader.pages), len(text))
        return text
        
    except ImportError:
        logger.error("pypdf not installed. Run: pip install pypdf")
        raise
    except Exception as e:
        logger.error("Failed to parse PDF %s: %s", file_path, e)
        raise


def parse_txt(file_path: Path) -> str:
    """Parse plain text file."""
    try:
        # Try UTF-8 first, then fallback to other encodings
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    text = f.read()
                logger.info("Parsed TXT: %s (%d chars, encoding: %s)", file_path.name, len(text), encoding)
                return text
            except UnicodeDecodeError:
                continue
        
        # Last resort: read as bytes and decode with errors ignored
        with open(file_path, 'rb') as f:
            text = f.read().decode('utf-8', errors='ignore')
        logger.info("Parsed TXT: %s (%d chars, fallback mode)", file_path.name, len(text))
        return text
        
    except Exception as e:
        logger.error("Failed to parse TXT %s: %s", file_path, e)
        raise


def parse_markdown(file_path: Path) -> str:
    """Parse Markdown file (keep as plain text for RAG)."""
    # For RAG purposes, we keep markdown as-is
    # The formatting will help provide context
    return parse_txt(file_path)


def parse_docx(file_path: Path) -> str:
    """Parse Microsoft Word DOCX file."""
    try:
        from docx import Document
        
        doc = Document(str(file_path))
        text_parts = []
        
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        
        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    text_parts.append(row_text)
        
        text = "\n\n".join(text_parts)
        logger.info("Parsed DOCX: %s (%d paragraphs, %d chars)", file_path.name, len(doc.paragraphs), len(text))
        return text
        
    except ImportError:
        logger.error("python-docx not installed. Run: pip install python-docx")
        raise
    except Exception as e:
        logger.error("Failed to parse DOCX %s: %s", file_path, e)
        raise


def parse_document(file_path: Path) -> str:
    """
    Parse a document based on its file extension.
    
    Args:
        file_path: Path to the document file
        
    Returns:
        Extracted text content
        
    Raises:
        ValueError: If file type is not supported
        Exception: If parsing fails
    """
    ext = file_path.suffix.lower()
    
    parsers = {
        '.pdf': parse_pdf,
        '.txt': parse_txt,
        '.md': parse_markdown,
        '.docx': parse_docx,
    }
    
    parser = parsers.get(ext)
    if not parser:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {', '.join(parsers.keys())}")
    
    return parser(file_path)


def get_supported_extensions() -> set:
    """Get set of supported file extensions."""
    return {'.pdf', '.txt', '.md', '.docx'}
