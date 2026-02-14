"""Background ingestion worker for document processing."""

import threading
import traceback
from pathlib import Path
from typing import Callable, Optional

from psk_bot.ingestion.parsers import parse_document
from psk_bot.ingestion.pipeline import chunk_text
from psk_bot.logging import get_logger
from psk_bot.services.document_manager import get_document_manager
from psk_bot.settings import settings

logger = get_logger(__name__)


class IngestionWorker:
    """Handles background document ingestion."""
    
    def __init__(self):
        self._active_jobs: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
    
    def ingest_document(self, doc_id: str, callback: Optional[Callable] = None):
        """
        Start ingestion of a document in a background thread.
        
        Args:
            doc_id: Document ID to ingest
            callback: Optional callback function called when complete
        """
        thread = threading.Thread(
            target=self._run_ingestion,
            args=(doc_id, callback),
            daemon=True
        )
        
        with self._lock:
            self._active_jobs[doc_id] = thread
        
        thread.start()
        logger.info("Started ingestion job for document: %s", doc_id)
    
    def is_processing(self, doc_id: str) -> bool:
        """Check if a document is currently being processed."""
        with self._lock:
            thread = self._active_jobs.get(doc_id)
            return thread is not None and thread.is_alive()
    
    def _run_ingestion(self, doc_id: str, callback: Optional[Callable] = None):
        """Run the actual ingestion process."""
        doc_manager = get_document_manager()
        
        try:
            # Update status to processing
            doc_manager.update_status(doc_id, "processing")
            
            # Get document info and file path
            doc = doc_manager.get_document(doc_id)
            if not doc:
                raise ValueError(f"Document not found: {doc_id}")
            
            file_path = doc_manager.get_document_file_path(doc_id)
            if not file_path or not file_path.exists():
                raise ValueError(f"Document file not found: {doc_id}")
            
            logger.info("Parsing document: %s", file_path)
            
            # Step 1: Parse document
            text = parse_document(file_path)
            if not text or len(text.strip()) < 50:
                raise ValueError("Document contains too little text to process")
            
            logger.info("Document parsed: %d characters", len(text))
            
            # Step 2: Chunk text
            chunks = chunk_text(
                text,
                chunk_size=settings.chunk_size,
                overlap=settings.chunk_overlap
            )
            
            if not chunks:
                raise ValueError("No chunks created from document")
            
            logger.info("Created %d chunks", len(chunks))
            
            # Step 3: Create vector store for this document
            from psk_bot.services.vector_store import VectorStoreService
            
            vector_store = VectorStoreService(config=settings, doc_id=doc_id)
            
            # Step 4: Add documents to vector store
            documents = [{"content": chunk, "doc_id": doc_id} for chunk in chunks]
            vector_store.add_documents(documents)
            
            logger.info("Vector store created with %d documents", len(documents))
            
            # Update status to ready
            doc_manager.update_status(doc_id, "ready", chunk_count=len(chunks))
            logger.info("Ingestion complete for document: %s", doc_id)
            
            if callback:
                callback(doc_id, True, None)
                
        except Exception as e:
            error_msg = str(e)
            logger.error("Ingestion failed for %s: %s\n%s", doc_id, error_msg, traceback.format_exc())
            doc_manager.update_status(doc_id, "failed", error_message=error_msg)
            
            if callback:
                callback(doc_id, False, error_msg)
        
        finally:
            # Clean up job tracking
            with self._lock:
                self._active_jobs.pop(doc_id, None)


# Global singleton
_ingestion_worker: Optional[IngestionWorker] = None


def get_ingestion_worker() -> IngestionWorker:
    """Get the global ingestion worker instance."""
    global _ingestion_worker
    if _ingestion_worker is None:
        _ingestion_worker = IngestionWorker()
    return _ingestion_worker
