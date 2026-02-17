"""Document parsers with OCR support for images and scanned documents."""

import io
from pathlib import Path
from typing import List, Optional, Tuple

from psk_bot.logging import get_logger

logger = get_logger(__name__)

# ── OCR helpers ──────────────────────────────────────────────────────────

# Minimum characters per page to consider it "has real text".
# Pages below this threshold are treated as scanned/image pages and OCR'd.
_MIN_TEXT_CHARS_PER_PAGE = 30


def _ocr_available() -> bool:
    """Check if Tesseract OCR is installed and accessible."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr_image(image, lang: str = "eng") -> str:
    """Run Tesseract OCR on a PIL Image and return extracted text."""
    try:
        import pytesseract
        text = pytesseract.image_to_string(image, lang=lang, config="--psm 6")
        return text.strip()
    except Exception as e:
        logger.warning("OCR failed on image: %s", e)
        return ""


def _preprocess_image_for_ocr(image):
    """Enhance an image for better OCR accuracy."""
    from PIL import Image, ImageEnhance, ImageFilter

    # Convert to RGB if needed (e.g. RGBA PNGs, CMYK)
    if image.mode not in ("L", "RGB"):
        image = image.convert("RGB")

    # Convert to grayscale
    gray = image.convert("L")

    # Upscale small images for better OCR
    w, h = gray.size
    if w < 1000 or h < 1000:
        scale = max(2, 1500 // min(w, h))
        gray = gray.resize((w * scale, h * scale), Image.LANCZOS)

    # Increase contrast
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(1.8)

    # Sharpen
    gray = gray.filter(ImageFilter.SHARPEN)

    return gray


# ── PDF parser ─────────────────────────────────────────────────────────


def parse_pdf(file_path: Path) -> str:
    """Parse PDF with OCR fallback for scanned pages and embedded images.

    Strategy per page:
      1. Extract text via PyMuPDF (fitz).
      2. If text is sparse (< _MIN_TEXT_CHARS_PER_PAGE chars), render the page
         as an image and OCR it (scanned-page detection).
      3. Separately extract embedded images from every page and OCR those
         that are large enough to contain meaningful text (diagrams, charts,
         screenshots, etc.).
      4. De-duplicate: if OCR text from an embedded image is already covered
         by the main page text, skip it.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — falling back to pypdf (no OCR)")
        return _parse_pdf_legacy(file_path)

    has_ocr = _ocr_available()
    if not has_ocr:
        logger.warning("Tesseract OCR not available — images/scanned pages will be skipped")

    doc = fitz.open(str(file_path))
    text_parts: List[str] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_label = f"[Page {page_num + 1}]"

        # ── 1. Native text extraction ──
        page_text = page.get_text("text").strip()

        # ── 2. Scanned-page OCR ──
        if len(page_text) < _MIN_TEXT_CHARS_PER_PAGE and has_ocr:
            logger.info("Page %d has little text (%d chars) — running full-page OCR",
                        page_num + 1, len(page_text))
            ocr_text = _ocr_pdf_page(page)
            if ocr_text:
                page_text = ocr_text

        # ── 3. Extract & OCR embedded images ──
        if has_ocr:
            image_texts = _extract_image_texts_from_page(page, page_num + 1, doc)
            # Only add image text that isn't already in the page text
            for img_text in image_texts:
                if img_text and not _text_overlap(img_text, page_text):
                    page_text += f"\n\n[Image content]\n{img_text}"

        if page_text:
            text_parts.append(f"{page_label}\n{page_text}")

    page_count = len(doc)
    doc.close()

    text = "\n\n".join(text_parts)
    logger.info("Parsed PDF: %s (%d pages, %d chars, OCR=%s)",
                file_path.name, page_count, len(text), has_ocr)
    return text


def _ocr_pdf_page(page) -> str:
    """Render a PDF page to an image and OCR it."""
    try:
        from PIL import Image

        # Render at 2x resolution for better OCR
        mat = __import__("fitz").Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = _preprocess_image_for_ocr(img)
        return _ocr_image(img)
    except Exception as e:
        logger.warning("Full-page OCR failed: %s", e)
        return ""


def _extract_image_texts_from_page(page, page_num: int, doc) -> List[str]:
    """Extract embedded images from a PDF page and OCR them."""
    from PIL import Image

    texts: List[str] = []
    try:
        image_list = page.get_images(full=True)
    except Exception:
        return texts

    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = doc.extract_image(xref)
            if not base_image:
                continue

            image_bytes = base_image["image"]
            img = Image.open(io.BytesIO(image_bytes))

            # Skip tiny images (icons, bullets, decorations)
            w, h = img.size
            if w < 80 or h < 80:
                continue

            # Skip very small images that are likely logos/decorations
            if w * h < 10000:
                continue

            logger.debug("OCR on embedded image p%d-img%d (%dx%d)", page_num, img_index, w, h)
            processed = _preprocess_image_for_ocr(img)
            text = _ocr_image(processed)

            # Only keep if we got meaningful text (not just noise)
            if text and len(text.strip()) > 10:
                texts.append(text.strip())

        except Exception as e:
            logger.debug("Failed to extract image xref=%d from page %d: %s", xref, page_num, e)

    return texts


def _text_overlap(new_text: str, existing_text: str, threshold: float = 0.6) -> bool:
    """Check if new_text significantly overlaps with existing_text."""
    if not new_text or not existing_text:
        return False
    new_words = set(new_text.lower().split())
    existing_words = set(existing_text.lower().split())
    if not new_words:
        return True
    overlap = len(new_words & existing_words) / len(new_words)
    return overlap >= threshold


def _parse_pdf_legacy(file_path: Path) -> str:
    """Fallback PDF parser using pypdf (no OCR)."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        text_parts = []
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"[Page {page_num}]\n{page_text}")

        text = "\n\n".join(text_parts)
        logger.info("Parsed PDF (legacy): %s (%d pages, %d chars)",
                     file_path.name, len(reader.pages), len(text))
        return text

    except ImportError:
        logger.error("Neither PyMuPDF nor pypdf installed!")
        raise
    except Exception as e:
        logger.error("Failed to parse PDF %s: %s", file_path, e)
        raise


# ── Image file parser ──────────────────────────────────────────────────


def parse_image(file_path: Path) -> str:
    """Parse an image file using OCR."""
    if not _ocr_available():
        raise RuntimeError(
            "Tesseract OCR is required for image files. "
            "Install: brew install tesseract (macOS) / "
            "apt install tesseract-ocr (Linux) / "
            "choco install tesseract (Windows)"
        )

    from PIL import Image

    img = Image.open(str(file_path))
    logger.info("OCR on image: %s (%dx%d)", file_path.name, img.width, img.height)

    processed = _preprocess_image_for_ocr(img)
    text = _ocr_image(processed)

    if not text or len(text.strip()) < 10:
        logger.warning("OCR extracted very little text from %s", file_path.name)
        return text or ""

    logger.info("Parsed image: %s (%d chars)", file_path.name, len(text))
    return text


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


# ── HTML parser ─────────────────────────────────────────────────────────


def parse_html(file_path: Path) -> str:
    """Parse an HTML file, extracting both visible text and structural context.

    Strategy:
      1. Read the raw HTML (multi-encoding fallback).
      2. Use BeautifulSoup to strip scripts/styles and extract the readable
         text while preserving structural hints (headings, list items, table
         rows) so that RAG can reason over the original page layout.
      3. Preserve <code>/<pre> blocks as-is for code-based RAG.
      4. Keep the *raw HTML source* appended at the end (truncated) so that
         questions about the HTML code itself ("what classes does the header
         use?") can be answered.
    """
    try:
        from bs4 import BeautifulSoup, Tag
    except ImportError:
        logger.error("beautifulsoup4 is required for HTML parsing. Run: pip install beautifulsoup4 lxml")
        raise

    raw_html = _read_text_file(file_path)
    if not raw_html:
        return ""

    # Prefer lxml but fall back to Python's built-in html.parser
    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except Exception:
        soup = BeautifulSoup(raw_html, "html.parser")

    # Remove elements that never contribute useful text
    for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    text_parts: List[str] = []

    # ── Extract <title> ──
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        text_parts.append(f"Page Title: {title_tag.get_text(strip=True)}")

    # ── Extract <meta description> ──
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        text_parts.append(f"Description: {meta_desc['content'].strip()}")

    # ── Walk the body tree and preserve structure ──
    body = soup.body or soup
    for element in body.descendants:
        if not isinstance(element, Tag):
            continue

        tag_name = element.name

        # Headings
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            heading_text = element.get_text(" ", strip=True)
            if heading_text:
                level = tag_name[1]
                text_parts.append(f"{'#' * int(level)} {heading_text}")

        # Paragraphs and divs with direct text
        elif tag_name in ("p", "article", "section", "blockquote"):
            para_text = element.get_text(" ", strip=True)
            if para_text and len(para_text) > 5:
                text_parts.append(para_text)

        # List items
        elif tag_name == "li":
            li_text = element.get_text(" ", strip=True)
            if li_text:
                text_parts.append(f"• {li_text}")

        # Table rows — pipe-delimited
        elif tag_name == "tr":
            cells = [td.get_text(" ", strip=True) for td in element.find_all(["td", "th"])]
            row_text = " | ".join(c for c in cells if c)
            if row_text:
                text_parts.append(row_text)

        # Code blocks
        elif tag_name in ("pre", "code"):
            code_text = element.get_text().strip()
            if code_text and len(code_text) > 5:
                text_parts.append(f"```\n{code_text}\n```")

    # Deduplicate consecutive identical lines (common with nested tags)
    deduped: List[str] = []
    for line in text_parts:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    visible_text = "\n\n".join(deduped)

    # ── Optionally append raw HTML source (only first 3000 chars to avoid chunk noise) ──
    combined = visible_text
    raw_section_len = 0
    if len(visible_text) < 500:
        # Very little visible text — include some raw HTML for context
        max_raw = 3000
        raw_section = raw_html.strip()
        raw_section_len = len(raw_section)
        if len(raw_section) > max_raw:
            raw_section = raw_section[:max_raw] + "\n... [HTML source truncated]"
        combined = f"{visible_text}\n\n─── RAW HTML SOURCE ───\n{raw_section}"

    logger.info("Parsed HTML: %s (%d chars visible text, %d chars raw source)",
                file_path.name, len(visible_text), raw_section_len)
    return combined


def _read_text_file(file_path: Path) -> str:
    """Read a text file with multi-encoding fallback."""
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
    for encoding in encodings:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return file_path.read_bytes().decode('utf-8', errors='ignore')


# ── Excel parser (XLS / XLSX) ──────────────────────────────────────────


def parse_excel(file_path: Path) -> str:
    """Parse Excel files (.xls, .xlsx) into structured text for RAG.

    Each worksheet is rendered as a markdown-style table so the LLM
    can reason over rows, columns, headers, and numeric data.
    """
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl is required for Excel parsing. Run: pip install openpyxl")
        raise

    ext = file_path.suffix.lower()

    # For .xls (legacy format), try xlrd
    if ext == ".xls":
        return _parse_xls_legacy(file_path)

    # .xlsx via openpyxl
    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    text_parts: List[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows_data: List[List[str]] = []

        for row in ws.iter_rows(values_only=True):
            cells = [str(cell).strip() if cell is not None else "" for cell in row]
            # Skip completely empty rows
            if any(c for c in cells):
                rows_data.append(cells)

        if not rows_data:
            continue

        sheet_text = f"## Sheet: {sheet_name}\n"

        # Use first row as header if it looks like one (mostly text)
        header = rows_data[0]
        data_rows = rows_data[1:] if len(rows_data) > 1 else []

        # Markdown table: header
        sheet_text += "| " + " | ".join(header) + " |\n"
        sheet_text += "| " + " | ".join(["---"] * len(header)) + " |\n"

        # Markdown table: data rows
        for row_cells in data_rows:
            # Pad or trim to match header column count
            padded = row_cells + [""] * (len(header) - len(row_cells))
            padded = padded[:len(header)]
            sheet_text += "| " + " | ".join(padded) + " |\n"

        text_parts.append(sheet_text)

    wb.close()

    text = "\n\n".join(text_parts)
    logger.info("Parsed Excel: %s (%d sheets, %d chars)",
                file_path.name, len(wb.sheetnames) if text_parts else 0, len(text))
    return text


def _parse_xls_legacy(file_path: Path) -> str:
    """Parse legacy .xls files using xlrd."""
    try:
        import xlrd
    except ImportError:
        logger.error(
            "xlrd is required for .xls files. Run: pip install xlrd\n"
            "Alternatively, convert to .xlsx and re-upload."
        )
        raise

    wb = xlrd.open_workbook(str(file_path))
    text_parts: List[str] = []

    for sheet_idx in range(wb.nsheets):
        ws = wb.sheet_by_index(sheet_idx)
        if ws.nrows == 0:
            continue

        sheet_text = f"## Sheet: {ws.name}\n"

        # Header row
        header = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
        sheet_text += "| " + " | ".join(header) + " |\n"
        sheet_text += "| " + " | ".join(["---"] * len(header)) + " |\n"

        # Data rows
        for r in range(1, ws.nrows):
            cells = [str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)]
            if any(c for c in cells):
                sheet_text += "| " + " | ".join(cells) + " |\n"

        text_parts.append(sheet_text)

    text = "\n\n".join(text_parts)
    logger.info("Parsed XLS (legacy): %s (%d sheets, %d chars)",
                file_path.name, wb.nsheets, len(text))
    return text


def parse_docx(file_path: Path) -> str:
    """Parse Microsoft Word DOCX file, including images via OCR."""
    try:
        from docx import Document
        
        doc = Document(str(file_path))
        text_parts = []
        
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        
        # Extract text from tables
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    text_parts.append(row_text)
        
        # Extract and OCR images embedded in the DOCX
        if _ocr_available():
            image_texts = _extract_docx_images(doc, file_path.name)
            page_text = "\n".join(text_parts)
            for img_text in image_texts:
                if img_text and not _text_overlap(img_text, page_text):
                    text_parts.append(f"[Image content]\n{img_text}")
        
        text = "\n\n".join(text_parts)
        logger.info("Parsed DOCX: %s (%d paragraphs, %d chars)", file_path.name, len(doc.paragraphs), len(text))
        return text
        
    except ImportError:
        logger.error("python-docx not installed. Run: pip install python-docx")
        raise
    except Exception as e:
        logger.error("Failed to parse DOCX %s: %s", file_path, e)
        raise


def _extract_docx_images(doc, filename: str) -> List[str]:
    """Extract images from a DOCX file and OCR them."""
    from PIL import Image

    texts: List[str] = []
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            try:
                image_data = rel.target_part.blob
                img = Image.open(io.BytesIO(image_data))

                w, h = img.size
                if w < 80 or h < 80 or w * h < 10000:
                    continue

                logger.debug("OCR on DOCX image in %s (%dx%d)", filename, w, h)
                processed = _preprocess_image_for_ocr(img)
                text = _ocr_image(processed)

                if text and len(text.strip()) > 10:
                    texts.append(text.strip())
            except Exception as e:
                logger.debug("Failed to extract DOCX image: %s", e)

    if texts:
        logger.info("Extracted text from %d images in %s", len(texts), filename)
    return texts


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
        '.html': parse_html,
        '.htm': parse_html,
        '.xls': parse_excel,
        '.xlsx': parse_excel,
        '.docx': parse_docx,
        '.png': parse_image,
        '.jpg': parse_image,
        '.jpeg': parse_image,
        '.tiff': parse_image,
        '.tif': parse_image,
        '.bmp': parse_image,
        '.webp': parse_image,
    }
    
    parser = parsers.get(ext)
    if not parser:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {', '.join(parsers.keys())}")
    
    return parser(file_path)


def get_supported_extensions() -> set:
    """Get set of supported file extensions."""
    return {
        '.pdf', '.txt', '.md', '.html', '.htm',
        '.xls', '.xlsx', '.docx',
        '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.webp',
    }
