#!/usr/bin/env python3
"""Build a merged FAISS index from all per-document stores.

This creates a single combined index at vector_store/faiss_index/ so that
"All Documents" search is a single fast FAISS query instead of iterating
through hundreds of individual stores.
"""

import json
import pickle
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import faiss
import numpy as np


def build_merged_index():
    """Merge all per-document FAISS indexes into one combined index."""
    base_path = project_root / "vector_store"
    output_dir = base_path / "faiss_index"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load document manager to get list of ready docs
    from psk_bot.services.document_manager import get_document_manager

    doc_manager = get_document_manager()
    ready_docs = doc_manager.get_ready_documents()

    if not ready_docs:
        print("No ready documents found!")
        return

    print(f"Found {len(ready_docs)} ready documents")

    all_vectors = []
    all_documents = []
    source_mapping = []  # parallel list: index -> {doc_id, doc_name}

    loaded = 0
    skipped = 0
    total_chunks = 0

    for doc in ready_docs:
        doc_dir = base_path / doc.id
        index_path = doc_dir / "faiss_index.faiss"
        docs_path = doc_dir / "faiss_index.pkl"

        if not index_path.exists() or not docs_path.exists():
            skipped += 1
            continue

        try:
            index = faiss.read_index(str(index_path))
            with docs_path.open("rb") as f:
                documents = pickle.load(f)

            n = index.ntotal
            dim = index.d

            # Reconstruct vectors from the FAISS index
            vectors = np.zeros((n, dim), dtype="float32")
            for i in range(n):
                vectors[i] = index.reconstruct(i)

            all_vectors.append(vectors)
            all_documents.extend(documents)

            for _ in range(n):
                source_mapping.append({
                    "doc_id": doc.id,
                    "doc_name": doc.name,
                })

            total_chunks += n
            loaded += 1
            if loaded % 100 == 0:
                print(f"  Loaded {loaded}/{len(ready_docs)} documents ({total_chunks} chunks so far)...")

        except Exception as e:
            print(f"  Failed to load {doc.id}: {e}")
            skipped += 1

    if not all_vectors:
        print("No vectors loaded!")
        return

    print(f"\nLoaded {loaded} documents, skipped {skipped}")
    print(f"Total chunks: {total_chunks}")

    # Concatenate all vectors
    matrix = np.vstack(all_vectors)
    dimension = matrix.shape[1]

    print(f"Matrix shape: {matrix.shape}, dimension: {dimension}")

    # Build combined HNSW index (same type as per-document stores)
    print("Building HNSW index...")
    t0 = time.time()

    combined_index = faiss.IndexHNSWFlat(dimension, 32, faiss.METRIC_INNER_PRODUCT)
    combined_index.add(matrix)

    elapsed = time.time() - t0
    print(f"Index built in {elapsed:.1f}s")

    # Save FAISS index
    faiss.write_index(combined_index, str(output_dir / "faiss_index.faiss"))
    print(f"Saved FAISS index to {output_dir / 'faiss_index.faiss'}")

    # Save documents (text chunks)
    with (output_dir / "faiss_index.pkl").open("wb") as f:
        pickle.dump(all_documents, f)
    print(f"Saved {len(all_documents)} document chunks")

    # Save source mapping (chunk index -> document info)
    with (output_dir / "source_mapping.json").open("w", encoding="utf-8") as f:
        json.dump(source_mapping, f)
    print(f"Saved source mapping ({len(source_mapping)} entries)")

    # Save metadata
    metadata = {
        "embedding_model": "nomic-embed-text",
        "dimension": dimension,
        "metric": "ip",
        "document_count": total_chunks,
        "source_documents": loaded,
        "created_at": int(time.time()),
        "merged": True,
    }
    with (output_dir / "faiss_index.meta.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n✅ Merged index saved to {output_dir}")
    print(f"   {total_chunks} chunks from {loaded} documents")


if __name__ == "__main__":
    build_merged_index()
