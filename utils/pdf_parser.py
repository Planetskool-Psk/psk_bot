# /rag-chatbot-ollama/utils/pdf_parser.py

from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from .logger import log
import config


def parse_pdf(file_path):
    """Extracts text from a PDF file."""
    log.info(f"Parsing PDF from path: {file_path}")
    try:
        reader = PdfReader(file_path)
        text = "".join(
            page.extract_text() for page in reader.pages if page.extract_text()
        )
        log.info(f"Successfully extracted {len(text)} characters from the PDF.")
        return text
    except Exception as e:
        log.error(f"Failed to parse PDF {file_path}: {e}")
        return None


def chunk_text(text):
    """Splits text into semantically meaningful chunks."""
    log.info("Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        length_function=len,
        separators=[
            "\n\n",
            "\n",
            ".",
            " ",
            "",
        ],  # Splits by paragraph, then line, then sentence
    )
    chunks = text_splitter.split_text(text)
    log.info(f"Text split into {len(chunks)} chunks.")
    return chunks
