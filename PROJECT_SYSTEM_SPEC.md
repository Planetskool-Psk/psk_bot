
# Project Specification: System Requirements for RAG Chatbot


## Folder Structure
The project is organized as follows:

```
chatbot_be/
├── app/
│   ├── __init__.py
│   └── routes.py
├── config.py
├── data/
│   └── your_document.pdf
├── requirements.txt
├── Dockerfile
├── run.py
├── run.log
├── scripts/
│   └── ingest.py
├── services/
│   ├── __init__.py
│   ├── ollama_service.py
│   ├── rag_service.py
│   └── vector_store_service.py
├── templates/
│   └── index.html
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   └── pdf_parser.py
├── vector_store/
│   └── faiss_index/
│       ├── faiss_index.faiss
│       └── faiss_index.pkl
└── __pycache__/
```

The RAG Chatbot system is composed of several key components:

1. **Document Ingestion & Vectorization**
   - Company documents (PDFs) are parsed and split into text chunks.
   - Each chunk is converted into a vector using sentence-transformers.
   - Vectors and chunks are stored in a FAISS vector database for fast semantic search.

2. **Backend API (Python/Flask)**
   - Handles user queries via REST or SocketIO endpoints.
   - Performs semantic search in the FAISS vector store to retrieve relevant context.
   - Constructs prompts for the LLM based on retrieved context and chat history.

3. **Local LLM Inference (Ollama)**
   - Receives prompts from the backend and generates answers using a local LLM (e.g., Gemma, Llama).
   - Returns responses to the backend for delivery to the user.

4. **Frontend (optional)**
   - Can be integrated with a web UI or chat client for user interaction.

5. **Deployment**
   - All components run on a CPU-based Azure VM (Linux), with Docker support for containerization.

### Data Flow
1. User sends a question to the chatbot (via web or API).
2. Backend performs semantic search in the vector store to find relevant document chunks.
3. Backend builds a prompt and sends it to the LLM via Ollama.
4. LLM generates a response, which is returned to the user.

This architecture ensures fast, accurate, and secure answers based on company documents, with all data and models running locally for privacy and compliance.

### What We Are Doing
- Ingesting company documents (PDFs) and converting them into searchable vector stores.
- Using semantic search to retrieve relevant information for user queries.
- Generating accurate, context-based answers using a local LLM.
- Providing a secure, scalable backend for HR-related queries.

### How It Helps
- Reduces HR workload by automating responses to common employee questions.
- Ensures employees get instant, accurate answers based on official documents.
- Improves accessibility to HR policies and information.
- Can be customized for different organizations and document sets.

## Overview
This document outlines the recommended system specifications for deploying and running the RAG Chatbot backend (Python, Flask, Ollama, FAISS, Sentence Transformers) smoothly in a production or development environment.

## Minimum System Requirements (CPU-based)
- **CPU:** Quad-core processor (Intel i5/Ryzen 5 or Azure D2 v4 or better)
- **RAM:** 8 GB
- **Storage:** 10 GB free disk space (SSD recommended)
- **OS:** Linux (Ubuntu 20.04+, CentOS 8+, or equivalent)
- **Python:** 3.10+
- **Network:** Stable internet connection for model downloads and API calls

## Recommended System Requirements (CPU-based)
- **CPU:** 6+ core processor (Intel i7/Ryzen 7 or Azure D8 v4 or better)
- **RAM:** 16 GB or more
- **Storage:** 50 GB SSD (for vector store, models, logs)
- **OS:** Linux (Ubuntu 22.04+, CentOS 9+, or equivalent)
- **Python:** 3.12+
- **Network:** 100 Mbps+ for fast downloads and API access

## Additional Requirements
- **Docker:** (Optional) For containerized deployment
- **Ollama:** Must be installed and running locally or on a dedicated server
- **FAISS:** Must be compiled for your CPU architecture
- **Python Libraries:**
  - Flask
  - Flask-SocketIO
  - pypdf
  - langchain
  - sentence-transformers
  - faiss-cpu
  - python-dotenv
  - eventlet
  - Any other dependencies in `requirements.txt`

## Notes
- For best performance, use a machine with SSD storage and sufficient CPU cores.
- If running multiple concurrent users, scale RAM and CPU accordingly.
- Ensure Ollama and FAISS are configured for CPU-only operation.
- Monitor system resource usage and logs for bottlenecks.

## Example Production Setup (Azure CPU VM)
- **Azure VM:** Standard D8 v4 (8 vCPU, 32GB RAM, SSD)
- **Azure VM:** Standard D4 v4 (4 vCPU, 16GB RAM, SSD)
- **Local Server:** Intel i7, 32GB RAM, 1TB SSD

## Troubleshooting
- If LLM responses are slow, check CPU usage, RAM, and disk I/O.
- For large documents, increase RAM and storage.
- Use a smaller LLM model if hardware is limited.

---
For further optimization or scaling, consult the project documentation or contact the development team.
