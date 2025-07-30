#!/usr/bin/env python3
"""
Enhanced document ingestion script with optimized chunking for better answer quality
Run this script to re-process your documents with the new optimized settings
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pdf_parser import parse_pdf, chunk_text
from services.vector_store_service import VectorStoreService
from utils.logger import log
import config
import shutil

def backup_existing_store():
    """Backup existing vector store before creating new one."""
    if os.path.exists(config.VECTOR_STORE_DIR):
        backup_dir = f"{config.VECTOR_STORE_DIR}_backup"
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        shutil.copytree(config.VECTOR_STORE_DIR, backup_dir)
        log.info(f"✅ Backed up existing vector store to {backup_dir}")

def main():
    log.info("🚀 Starting enhanced document ingestion with optimized chunking...")
    log.info(f"📊 New chunking settings: size={config.CHUNK_SIZE}, overlap={config.CHUNK_OVERLAP}")
    
    # Check if PDF exists
    if not os.path.exists(config.PDF_PATH):
        log.error(f"❌ PDF not found at {config.PDF_PATH}")
        log.info(f"📋 Please place your PDF file at: {config.PDF_PATH}")
        return
    
    try:
        # Backup existing store
        backup_existing_store()
        
        # Parse PDF with new chunking strategy
        log.info(f"📄 Parsing PDF: {config.PDF_PATH}")
        text = parse_pdf(config.PDF_PATH)
        
        if not text:
            log.error("❌ No text extracted from PDF")
            return
            
        log.info(f"✅ Extracted {len(text)} characters from PDF")
        
        # Chunk text with enhanced settings
        log.info("📊 Chunking text with enhanced settings...")
        text_chunks = chunk_text(text)
        
        if not text_chunks:
            log.error("❌ No text chunks extracted from PDF")
            return
        
        log.info(f"✅ Extracted {len(text_chunks)} text chunks")
        log.info(f"📏 Average chunk length: {sum(len(chunk) for chunk in text_chunks) / len(text_chunks):.0f} characters")
        
        # Sample some chunks for quality check
        log.info("📋 Sample chunks:")
        for i, chunk in enumerate(text_chunks[:3]):
            preview = chunk[:150] + "..." if len(chunk) > 150 else chunk
            log.info(f"  Chunk {i+1}: {preview}")
        
        # Create enhanced vector store
        log.info("🔍 Creating enhanced vector store with better retrieval...")
        vector_store = VectorStoreService()
        vector_store.create_and_save_store(text_chunks)
        
        # Verify the store
        log.info("✅ Verifying enhanced vector store...")
        if vector_store.load_store():
            log.info("✅ Enhanced vector store loaded successfully!")
            
            # Test search quality
            test_queries = [
                "company policy",
                "employee benefits", 
                "vacation time",
                "working hours"
            ]
            
            log.info("🧪 Testing search quality with sample queries:")
            for query in test_queries:
                results = vector_store.search(query, k=2)
                if results:
                    best_score = results[0].get("relevance", results[0].get("similarity", 0))
                    log.info(f"  '{query}': {len(results)} results, best relevance: {best_score:.3f}")
                else:
                    log.info(f"  '{query}': No results found")
        else:
            log.error("❌ Failed to load enhanced vector store")
            return
        
        log.info("🎉 Enhanced document ingestion completed successfully!")
        log.info("💡 The chatbot should now provide more comprehensive and accurate answers.")
        log.info("🔄 Restart the chatbot to use the enhanced vector store:")
        log.info("   ./start_optimized.sh")
        
    except Exception as e:
        log.error(f"❌ Error during enhanced ingestion: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
