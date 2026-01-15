"""Document management service for admin operations."""

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import List, Optional

from gentari_bot.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DocumentInfo:
    """Represents a document in the system."""
    
    id: str
    name: str
    filename: str
    file_type: str
    file_size: int
    status: str  # uploading, processing, ready, failed
    chunk_count: int = 0
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "DocumentInfo":
        return cls(**data)


class DocumentManager:
    """Manages document storage, metadata, and lifecycle."""
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.docx'}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    
    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
        
        self._base_dir = base_dir
        self._documents_dir = base_dir / "data" / "documents"
        self._metadata_path = self._documents_dir / "metadata.json"
        self._vector_store_base = base_dir / "vector_store"
        self._lock = Lock()
        
        self._ensure_directories()
        self._documents: List[DocumentInfo] = []
        self._load_metadata()
    
    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        self._documents_dir.mkdir(parents=True, exist_ok=True)
        self._vector_store_base.mkdir(parents=True, exist_ok=True)
    
    def _load_metadata(self):
        """Load document metadata from JSON file."""
        if self._metadata_path.exists():
            try:
                with open(self._metadata_path, 'r') as f:
                    data = json.load(f)
                    self._documents = [
                        DocumentInfo.from_dict(doc) 
                        for doc in data.get("documents", [])
                    ]
                logger.info("Loaded %d documents from metadata", len(self._documents))
            except Exception as e:
                logger.error("Failed to load metadata: %s", e)
                self._documents = []
        else:
            self._documents = []
            self._save_metadata()
    
    def _save_metadata(self):
        """Save document metadata to JSON file."""
        with self._lock:
            data = {
                "documents": [doc.to_dict() for doc in self._documents],
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
            with open(self._metadata_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def _generate_doc_id(self, name: str) -> str:
        """Generate a unique document ID."""
        # Create a slug from name + short UUID
        slug = "".join(c if c.isalnum() else "_" for c in name.lower())
        slug = slug[:30]  # Limit length
        short_uuid = str(uuid.uuid4())[:8]
        return f"{slug}_{short_uuid}"
    
    def _get_document_path(self, doc_id: str) -> Path:
        """Get the storage path for a document."""
        return self._documents_dir / doc_id
    
    def _get_vector_store_path(self, doc_id: str) -> Path:
        """Get the vector store path for a document."""
        return self._vector_store_base / doc_id
    
    def validate_file(self, filename: str, file_size: int) -> tuple[bool, str]:
        """Validate file type and size."""
        ext = Path(filename).suffix.lower()
        
        if ext not in self.SUPPORTED_EXTENSIONS:
            return False, f"Unsupported file type: {ext}. Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
        
        if file_size > self.MAX_FILE_SIZE:
            return False, f"File too large: {file_size / 1024 / 1024:.1f}MB. Maximum: {self.MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        
        return True, ""
    
    def create_document(self, filename: str, file_content: bytes, display_name: str = None) -> DocumentInfo:
        """
        Create a new document entry and save the file.
        
        Args:
            filename: Original filename
            file_content: File content as bytes
            display_name: Optional display name (defaults to filename without extension)
        
        Returns:
            DocumentInfo object
        """
        # Determine display name
        if not display_name:
            display_name = Path(filename).stem.replace("_", " ").replace("-", " ").title()
        
        # Generate document ID
        doc_id = self._generate_doc_id(display_name)
        
        # Get file info
        ext = Path(filename).suffix.lower()
        file_type = ext[1:]  # Remove the dot
        file_size = len(file_content)
        
        # Create document directory
        doc_path = self._get_document_path(doc_id)
        doc_path.mkdir(parents=True, exist_ok=True)
        
        # Save the file
        file_path = doc_path / f"original{ext}"
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        # Create document info
        doc_info = DocumentInfo(
            id=doc_id,
            name=display_name,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            status="uploading"
        )
        
        # Add to documents list
        self._documents.append(doc_info)
        self._save_metadata()
        
        logger.info("Created document: %s (%s)", doc_id, filename)
        return doc_info
    
    def list_documents(self) -> List[DocumentInfo]:
        """Get all documents."""
        return self._documents.copy()
    
    def get_document(self, doc_id: str) -> Optional[DocumentInfo]:
        """Get a document by ID."""
        for doc in self._documents:
            if doc.id == doc_id:
                return doc
        return None
    
    def get_document_file_path(self, doc_id: str) -> Optional[Path]:
        """Get the file path for a document."""
        doc = self.get_document(doc_id)
        if not doc:
            return None
        
        doc_dir = self._get_document_path(doc_id)
        ext = f".{doc.file_type}"
        return doc_dir / f"original{ext}"
    
    def update_status(self, doc_id: str, status: str, error_message: str = None, chunk_count: int = None):
        """Update document status."""
        doc = self.get_document(doc_id)
        if doc:
            doc.status = status
            doc.updated_at = datetime.utcnow().isoformat() + "Z"
            if error_message is not None:
                doc.error_message = error_message
            if chunk_count is not None:
                doc.chunk_count = chunk_count
            self._save_metadata()
            logger.info("Updated document %s status to %s", doc_id, status)
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document and its associated data.
        
        Returns:
            True if deleted, False if not found
        """
        doc = self.get_document(doc_id)
        if not doc:
            return False
        
        # Remove from list
        self._documents = [d for d in self._documents if d.id != doc_id]
        self._save_metadata()
        
        # Delete document files
        doc_path = self._get_document_path(doc_id)
        if doc_path.exists():
            shutil.rmtree(doc_path)
        
        # Delete vector store
        vector_path = self._get_vector_store_path(doc_id)
        if vector_path.exists():
            shutil.rmtree(vector_path)
        
        logger.info("Deleted document: %s", doc_id)
        return True
    
    def get_ready_documents(self) -> List[DocumentInfo]:
        """Get all documents with 'ready' status."""
        return [doc for doc in self._documents if doc.status == "ready"]


# Global singleton instance
_document_manager: Optional[DocumentManager] = None


def get_document_manager() -> DocumentManager:
    """Get the global document manager instance."""
    global _document_manager
    if _document_manager is None:
        _document_manager = DocumentManager()
    return _document_manager
