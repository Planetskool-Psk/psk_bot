"""Document ingestion helper."""

import os
import sys
from pathlib import Path


def _configure_ingest_env() -> None:
    """Clamp threads for BLAS/torch to avoid segfaults on small Macs."""
    env_defaults = {
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "FAISS_DISABLE_GPU": "1",
        "KMP_DUPLICATE_LIB_OK": "TRUE",
    }
    for key, val in env_defaults.items():
        os.environ.setdefault(key, val)

    try:
        import torch  # type: ignore

        torch.set_num_threads(max(1, min(2, os.cpu_count() or 2)))
        if hasattr(torch, "set_num_interop_threads"):
            torch.set_num_interop_threads(1)
    except Exception:
        pass


_configure_ingest_env()

# Ensure project root on path when running as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from gentari_bot.ingestion.pipeline import IngestionPipeline
from gentari_bot.logging import get_logger
from gentari_bot.settings import settings

logger = get_logger(__name__)


def main() -> None:
    """Ingest PDF content into the vector store."""
    logger.info("Starting ingestion process...")

    pdf_path = Path(settings.pdf_path)
    if not pdf_path.exists():
        logger.error("PDF file not found at: %s", pdf_path)
        logger.error("Place your PDF in the 'data' directory or update the PDF_PATH env var.")
        return

    pipeline = IngestionPipeline()
    report = pipeline.run(pdf_path)
    if not report:
        logger.error("Ingestion failed.")
        return

    summary = report.as_dict()
    logger.info(
        "Ingestion completed successfully in %.2fs (%s chunks, %s characters)",
        summary["elapsed_seconds"],
        summary["chunk_count"],
        summary["characters"],
    )


if __name__ == "__main__":
    main()
