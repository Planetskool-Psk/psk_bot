"""Admin routes for document management."""

import os
from functools import wraps
from typing import Any, Dict

from flask import Blueprint, jsonify, render_template, request, session, redirect, url_for

from gentari_bot.logging import get_logger
from gentari_bot.services.document_manager import get_document_manager
from gentari_bot.services.ingestion_worker import get_ingestion_worker

logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Admin password from environment
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def require_admin(f):
    """Decorator to require admin authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_authenticated"):
            if request.is_json:
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.get("/login")
def login():
    """Render login page."""
    return render_template("admin_login.html")


@admin_bp.post("/login")
def do_login():
    """Process login."""
    password = request.form.get("password", "")
    
    if password == ADMIN_PASSWORD:
        session["admin_authenticated"] = True
        logger.info("Admin login successful")
        return redirect(url_for("admin.admin_page"))
    
    logger.warning("Admin login failed - invalid password")
    return render_template("admin_login.html", error="Invalid password")


@admin_bp.get("/logout")
def logout():
    """Log out admin."""
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
@require_admin
def admin_page():
    """Render admin dashboard."""
    return render_template("admin.html")


@admin_bp.get("/api/documents")
@require_admin
def list_documents():
    """List all documents."""
    doc_manager = get_document_manager()
    documents = doc_manager.list_documents()
    
    return jsonify({
        "documents": [doc.to_dict() for doc in documents],
        "count": len(documents)
    })


@admin_bp.post("/api/documents")
@require_admin
def upload_document():
    """Upload a new document."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    
    # Get optional display name
    display_name = request.form.get("name", "").strip() or None
    
    # Validate file
    doc_manager = get_document_manager()
    file_content = file.read()
    
    valid, error_msg = doc_manager.validate_file(file.filename, len(file_content))
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    try:
        # Create document entry
        doc_info = doc_manager.create_document(
            filename=file.filename,
            file_content=file_content,
            display_name=display_name
        )
        
        # Start background ingestion
        ingestion_worker = get_ingestion_worker()
        ingestion_worker.ingest_document(doc_info.id)
        
        logger.info("Document upload started: %s", doc_info.id)
        
        return jsonify({
            "success": True,
            "document": doc_info.to_dict(),
            "message": "Document uploaded. Ingestion started."
        }), 201
        
    except Exception as e:
        logger.error("Upload failed: %s", e)
        return jsonify({"error": str(e)}), 500


@admin_bp.get("/api/documents/<doc_id>")
@require_admin
def get_document(doc_id: str):
    """Get document details."""
    doc_manager = get_document_manager()
    doc = doc_manager.get_document(doc_id)
    
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    
    return jsonify({"document": doc.to_dict()})


@admin_bp.get("/api/documents/<doc_id>/status")
@require_admin
def get_document_status(doc_id: str):
    """Get document ingestion status."""
    doc_manager = get_document_manager()
    doc = doc_manager.get_document(doc_id)
    
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    
    ingestion_worker = get_ingestion_worker()
    is_processing = ingestion_worker.is_processing(doc_id)
    
    return jsonify({
        "id": doc.id,
        "status": doc.status,
        "is_processing": is_processing,
        "chunk_count": doc.chunk_count,
        "error_message": doc.error_message
    })


@admin_bp.delete("/api/documents/<doc_id>")
@require_admin
def delete_document(doc_id: str):
    """Delete a document."""
    doc_manager = get_document_manager()
    
    # Check if document exists
    doc = doc_manager.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    
    # Check if currently processing
    ingestion_worker = get_ingestion_worker()
    if ingestion_worker.is_processing(doc_id):
        return jsonify({"error": "Cannot delete document while processing"}), 409
    
    # Delete document
    success = doc_manager.delete_document(doc_id)
    
    if success:
        logger.info("Document deleted: %s", doc_id)
        return jsonify({"success": True, "message": "Document deleted"})
    else:
        return jsonify({"error": "Failed to delete document"}), 500


# Public API endpoint (no auth required) for chat dropdown
@admin_bp.get("/api/documents/public")
def list_ready_documents():
    """List documents available for chat (ready status only)."""
    doc_manager = get_document_manager()
    documents = doc_manager.get_ready_documents()
    
    return jsonify({
        "documents": [
            {"id": doc.id, "name": doc.name, "chunk_count": doc.chunk_count}
            for doc in documents
        ]
    })
