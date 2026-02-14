# PSK Bot - PlanetSkool Assistant

A high-performance RAG (Retrieval-Augmented Generation) chatbot built with Flask and Ollama, featuring real-time streaming responses and a professional chat interface.

## 🚀 Features

- **Real-time streaming** - Character-by-character response streaming directly from Ollama
- **Document-based RAG** - FAISS vector store for semantic search across HR documents
- **Live text formatting** - Markdown formatting (bold, bullets, links) applied during streaming
- **Smart greeting detection** - Quick responses for casual greetings without RAG lookup
- **Professional UI** - Clean, modern chat interface with typing animations
- **Optimized for speed** - Configured for fast responses on CPU-only environments
- **REST API** - Health checks and chat endpoints for integration

## 📋 Prerequisites

### System Requirements
- **OS**: macOS, Linux (Ubuntu/Debian), or Windows with WSL
- **Hardware**: Minimum 4 CPU cores, 8GB RAM recommended
- **Python**: 3.10 or higher
- **Ollama**: For LLM and embedding inference

### Required Software
1. **Python 3.10+** with pip
2. **Ollama** (LLM runtime)
3. **Git** (for cloning)

## 🛠️ Installation & Setup

### Step 1: Clone the Repository
```bash
git clone <your-repository-url>
cd "PSK Bot"
```

### Step 2: Install Ollama

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Start Ollama service:**
```bash
ollama serve
```

### Step 3: Pull Required Models
```bash
# Pull the LLM model (lightweight, fast responses)
ollama pull qwen2.5:0.5b

# Pull the embedding model
ollama pull nomic-embed-text
```

> **Note:** The `qwen2.5:0.5b` model (397MB) is optimized for speed. For better quality responses, you can use `qwen2.5:1.5b` or `gemma3:1b` instead.

### Step 4: Set Up Python Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
.\venv\Scripts\activate   # Windows

# Upgrade pip
pip install --upgrade pip
```

### Step 5: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 6: Prepare Your Documents
```bash
# Create data folder if it doesn't exist
mkdir -p data

# Place your HR document(s) in the data folder
cp /path/to/your/hr_handbook.pdf data/

# Run document ingestion to build the vector store
python3 scripts/ingest.py
```

The ingestion script will:
- Parse PDF documents from the `data/` folder
- Chunk text into searchable segments
- Generate embeddings using `nomic-embed-text`
- Store vectors in FAISS index under `vector_store/faiss_index/`

### Step 7: Configure Environment (Optional)
```bash
# Copy the example environment file
cp .env.example .env

# Edit settings as needed
nano .env
```

## 🎯 Running the Application

### Quick Start
```bash
# Make sure Ollama is running
ollama serve &

# Activate virtual environment
source venv/bin/activate

# Start the chatbot
python3 run.py
```

The server will start at **http://localhost:5173**

### Production Mode
```bash
# Set production environment
export FLASK_ENV=production
export DEBUG=false

# Run with optimized settings
python3 run.py
```

### Using the Optimized Startup Script
```bash
chmod +x start_optimized.sh
./start_optimized.sh
```

## 🌐 Accessing the Application

| Endpoint | Description |
|----------|-------------|
| `http://localhost:5173` | Chat web interface |
| `GET /healthz` | Health check (RAG + vector store status) |
| `POST /api/chat` | REST API for chat (JSON body) |
| `POST /api/prepare` | Get RAG context for direct Ollama streaming |
| `POST /api/stream` | Server-Sent Events streaming endpoint |

### API Examples

**Health Check:**
```bash
curl http://localhost:5173/healthz
```

**Chat API:**
```bash
curl -X POST http://localhost:5173/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the leave policy?"}'
```

## ⚙️ Configuration

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5173` | Server port |
| `DEBUG` | `false` | Debug mode |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` | LLM model for responses |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM_NUM_PREDICT` | `200` | Max tokens per response |
| `LLM_NUM_CTX` | `1024` | Context window size |
| `LLM_TEMPERATURE` | `0.0` | Response randomness (0 = deterministic) |
| `LLM_NUM_THREAD` | `4` | CPU threads for inference |
| `TOP_K_RESULTS` | `2` | Number of documents to retrieve |
| `CHUNK_SIZE` | `200` | Document chunk size |

### Performance Tuning

For faster responses on CPU:
```bash
export LLM_NUM_PREDICT=100      # Shorter responses
export LLM_NUM_CTX=512          # Smaller context
export LLM_TEMPERATURE=0.0      # Deterministic (faster)
export LLM_NUM_THREAD=4         # Match your CPU cores
```

For better quality responses:
```bash
export OLLAMA_MODEL=qwen2.5:1.5b  # Larger model
export LLM_NUM_PREDICT=300        # Longer responses
export LLM_NUM_CTX=2048           # More context
export TOP_K_RESULTS=3            # More documents
```

## 📁 Project Structure

```
PSK Bot/
├── psk_bot/                 # Main application package
│   ├── __init__.py              # Flask app factory
│   ├── container.py             # Dependency injection
│   ├── settings.py              # Configuration management
│   ├── core/
│   │   └── conversation.py      # Session history
│   ├── services/
│   │   ├── ollama.py            # LLM client
│   │   ├── ollama_embeddings.py # Embedding service
│   │   ├── rag.py               # RAG pipeline
│   │   └── vector_store.py      # FAISS operations
│   ├── web/
│   │   └── routes.py            # HTTP endpoints
│   ├── websocket/
│   │   └── events.py            # Socket.IO handlers
│   └── templates/
│       └── index.html           # Chat UI
├── scripts/
│   ├── ingest.py                # Document ingestion
│   └── ingest_enhanced.py       # Enhanced ingestion
├── data/                        # PDF documents
├── vector_store/
│   └── faiss_index/             # FAISS index files
├── docs/                        # Documentation
├── run.py                       # Application entry point
├── requirements.txt             # Python dependencies
├── setup_server.sh              # One-command server setup script
├── gunicorn.conf.py             # Production WSGI config
└── README.md                    # This file
```

## 🚀 Server Deployment (Nginx)

### Automated Setup
```bash
# On your 2-core/12GB AMD Milan VM:
git clone <your-repo-url> /opt/psk-bot
cd /opt/psk-bot
sudo bash setup_server.sh --email your@email.com
```

This handles everything in one go: Ollama + models, Python venv, systemd, Nginx with SSL for `chatbot.planetskool.com`, firewall, and log rotation. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for all options.

### Robot API
```bash
# Full response
curl -X POST http://<server>/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"message": "Hello!", "session_id": "robot_01"}'

# SSE streaming
curl -X POST http://<server>/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"message": "What is the leave policy?", "document_id": "abc123"}'
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full API reference.

## 🔧 Troubleshooting

### Ollama Connection Error
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if not running
ollama serve &

# Verify models are available
ollama list
```

### Slow Responses
```bash
# Check CPU usage
top -l 1 | head -10

# Use a smaller model
ollama pull qwen2.5:0.5b
export OLLAMA_MODEL=qwen2.5:0.5b

# Reduce context size
export LLM_NUM_CTX=512
export LLM_NUM_PREDICT=100
```

### Vector Store Issues
```bash
# Check if index exists
ls -la vector_store/faiss_index/

# Re-run ingestion
python3 scripts/ingest.py

# Check document count in logs
# Should show "Vector store loaded: X documents"
```

### Port Already in Use
```bash
# Find process using port
lsof -i :5173

# Kill process
kill -9 <PID>

# Or use different port
export PORT=5174
python3 run.py
```

### Memory Issues
```bash
# Monitor memory
python3 monitor_system.py

# Reduce batch sizes in .env
export EMBEDDING_BATCH_SIZE=8
export LLM_NUM_BATCH=64
```

## 📊 Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│   Web Browser   │────▶│   Flask Server   │────▶│   Ollama    │
│   (index.html)  │     │   (routes.py)    │     │   (LLM)     │
└─────────────────┘     └──────────────────┘     └─────────────┘
        │                        │                      │
        │                        ▼                      │
        │               ┌──────────────────┐           │
        │               │   RAG Service    │           │
        │               │   (rag.py)       │           │
        │               └──────────────────┘           │
        │                        │                      │
        │                        ▼                      │
        │               ┌──────────────────┐           │
        │               │  Vector Store    │           │
        │               │  (FAISS)         │           │
        │               └──────────────────┘           │
        │                                              │
        └──────────── Direct Streaming ────────────────┘
```

**Flow:**
1. User sends message via web interface
2. Flask `/api/prepare` retrieves relevant documents from FAISS
3. Prompt is built with context and returned to browser
4. Browser streams response directly from Ollama at `localhost:11434`
5. Text is formatted live as characters stream in

## 📄 License

MIT License - see LICENSE file for details.

## 🆘 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs in terminal output
3. Open an issue in the repository

---

**Built with ❤️ for PlanetSkool**
