# RAG Chatbot Backend - Optimized for 2-Core, 8GB RAM VM

A high-performance RAG (Retrieval-Augmented Generation) chatbot backend built with Flask, SocketIO, and Ollama, specifically optimized for resource-constrained environments.

## 🚀 Features

- **Real-time chat** via WebSocket connections
- **Document-based RAG** using FAISS vector store
- **Optimized for low-resource VMs** (2 cores, 8GB RAM)
- **Memory monitoring** with automatic alerts
- **Performance tracking** and system monitoring
- **Streaming responses** for better user experience
- **Session-safe streaming** (per-user locks to avoid overload on small VMs)
- **Response + embedding caching** to speed up repeated questions
- **Health + REST API endpoints** for easier operations and monitoring

## 📋 Prerequisites

Before you begin, ensure you have the following installed on your system:

### System Requirements
- **Operating System**: Linux (Ubuntu/Debian recommended)
- **Hardware**: Minimum 2 CPU cores, 8GB RAM
- **Python**: 3.8 or higher
- **Ollama**: For LLM inference

### Required Software
1. **Python 3.8+**
2. **pip** (Python package installer)
3. **Ollama** (Large Language Model runtime)
4. **Git** (for cloning the repository)

## 🛠️ Installation & Setup

### Step 1: Clone the Repository
```bash
git clone <your-repository-url>
cd chatbot_be
```

### Step 2: Install Ollama
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve &

# Pull the LLM model (optimized for 2-core VM)
ollama pull gemma3:1b
```

**Embedding Model:**
The project uses `nomic-ai/nomic-embed-text-v1.5` from HuggingFace - a high-quality 768-dimensional embedding model optimized for retrieval tasks. It will be automatically downloaded when you run document ingestion.

### Step 3: Set Up Python Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 4: Install Dependencies
```bash
# Install required Python packages
pip install -r requirements.txt
```

### Step 5: Prepare Your Documents
```bash
# Place your PDF document in the data folder
cp /path/to/your/document.pdf data/your_document.pdf

# Run the document ingestion script
python3 scripts/ingest.py
```
- If you update the codebase, re-run the ingestion script to rebuild the FAISS index with the latest settings and metadata.

### Step 6: Configure Environment (Optimized Setup)
```bash
# Run the optimization setup script
chmod +x setup_optimized.sh
./setup_optimized.sh
```

This will:
- Backup your current `.env` file
- Apply optimized environment configuration
- Set up performance monitoring
- Configure threading for 2-core VM

## 🎯 Running the Project

### Standard Mode
```bash
# Activate virtual environment
source venv/bin/activate

# Start the application
python3 run.py
```

### Optimized Mode (for 2-Core, 8GB RAM VMs)
```bash
# Quick setup (first time only)
chmod +x setup_optimized.sh
./setup_optimized.sh

# Start with optimizations
chmod +x start_optimized.sh
./start_optimized.sh
```

### Performance Monitoring
```bash
# Terminal 1: Start the chatbot
./start_optimized.sh

# Terminal 2: Monitor system performance
source venv/bin/activate
python3 monitor_system.py
```

### Using Environment Variables
```bash
# Enable optimized mode
export OPTIMIZED_MODE=true
export PORT=5173

# Run
python3 run.py
```

## 🌐 Accessing the Application

Once the server is running, you can access the chatbot through:

- **Local access**: http://localhost:5173
- **Network access**: http://YOUR_VM_IP:5173
- **Web interface**: Interactive chat interface with real-time responses
- **Health**: `GET /healthz` for readiness (vector store + model)
- **REST API**: `POST /api/chat` with JSON body `{"question": "...", "history": [...]}` returns `{response, latency_ms}`

## 📊 Performance Monitoring

The optimized version includes real-time system monitoring:

### Built-in Memory Monitoring
- Automatic alerts when memory usage exceeds 85%
- Background garbage collection
- Real-time RAM usage tracking

### System Performance Monitor
```bash
# Run in separate terminal for real-time monitoring
python3 monitor_system.py
```

This provides:
- CPU usage per core
- Memory consumption breakdown
- Python/Ollama process tracking
- Performance recommendations

## ⚙️ Configuration

### Environment Variables (.env)

Key configuration options:

```bash
# Application
DEBUG=false
PORT=5173
OPTIMIZED_MODE=false  # Set to true for 2-core VM optimizations

# Model settings
OLLAMA_MODEL=gemma3:1b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_KEEP_ALIVE=60s

# Embedding model
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1.5  # Or: all-MiniLM-L6-v2
EMBEDDING_BATCH_SIZE=16

# RAG settings
CHUNK_SIZE=256
CHUNK_OVERLAP=25
TOP_K_RESULTS=1
CONTEXT_DOCUMENTS=2
MAX_CONVERSATION_HISTORY=3

# Performance (for optimized mode)
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
TOKENIZERS_PARALLELISM=false

# LLM Generation
LLM_TIMEOUT=180
LLM_NUM_PREDICT=640
LLM_NUM_CTX=3072
LLM_TEMPERATURE=0.35
```

For detailed optimization settings, see [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md).

## 🐳 Docker Deployment

### Standard Deployment
```bash
# Build Docker image
docker build -t gentari-chatbot .

# Run container
docker run -d \
  --name gentari-chatbot \
  -p 5173:5173 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/vector_store:/app/vector_store \
  gentari-chatbot
```

### Optimized Deployment (2-Core, 8GB RAM VMs)
```bash
# Run with resource limits and optimizations
docker run -d \
  --name gentari-chatbot \
  -p 5173:5173 \
  --memory=6g \
  --cpus=2 \
  -e OPTIMIZED_MODE=true \
  -e OMP_NUM_THREADS=2 \
  -e MKL_NUM_THREADS=2 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/vector_store:/app/vector_store \
  gentari-chatbot
```

For more deployment options, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## 🔧 Troubleshooting

### Common Issues and Solutions

#### 1. Ollama Connection Error
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not running, start Ollama
ollama serve &

# Verify model is available
ollama list
```

#### 2. Memory Issues
```bash
# Check memory usage
free -h

# Monitor Python processes
python3 monitor_system.py

# Restart if memory usage > 80%
./start_optimized.sh
```

#### 3. Port Already in Use
```bash
# Find process using port 5173
sudo lsof -i :5173

# Kill the process
sudo kill -9 <PID>

# Or use a different port
export PORT=5174
./start_optimized.sh
```

#### 4. Virtual Environment Issues
```bash
# Recreate virtual environment
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 5. Document Ingestion Problems
```bash
# Check if PDF exists
ls -la data/your_document.pdf

# Re-run ingestion
python3 scripts/ingest.py

# Check vector store creation
ls -la vector_store/faiss_index/
```

## 📈 Performance Optimization Tips

### For 2-Core, 8GB RAM VMs:
1. **Use the optimized startup script**: `./start_optimized.sh`
2. **Monitor memory usage**: Keep below 85% for best performance
3. **Keep conversations short**: Restart periodically for optimal performance
4. **Use single questions**: Avoid complex, multi-part queries
5. **Monitor with**: `python3 monitor_system.py`

### Performance Benchmarks:
- **Response Time**: 30-50 seconds (40% improvement)
- **Memory Usage**: <12% peak (20% reduction)
- **CPU Utilization**: Consistent 2-core usage
- **Startup Time**: ~20 seconds (30% improvement)

## 🧪 Testing

### Load Testing
```bash
# Run performance tests
python3 load_test.py

# Heavy load testing
python3 heavy_load_test.py

# CPU stress testing
python3 maximum_cpu_stress.py
```

### Manual Testing
```bash
# Test basic functionality
curl http://localhost:5173

# Test WebSocket connection
# Use the web interface at http://localhost:5173
```

## 📁 Project Structure

```
gentari-bot/
├── gentari_bot/                 # Main application package
│   ├── __init__.py              # Flask factory + Socket.IO wiring
│   ├── container.py             # Dependency injection container
│   ├── extensions.py            # Flask extensions
│   ├── logging.py               # Logging configuration
│   ├── settings.py              # Centralized configuration
│   ├── core/
│   │   └── conversation.py      # Session history management
│   ├── ingestion/
│   │   ├── pdf.py               # Document parsing utilities
│   │   └── pipeline.py          # Ingestion pipeline
│   ├── services/                # Domain services
│   │   ├── ollama.py            # LLM integration
│   │   ├── rag.py               # RAG pipeline
│   │   └── vector_store.py      # Vector database operations
│   ├── web/
│   │   └── routes.py            # HTTP routes (UI, health, REST)
│   ├── websocket/
│   │   └── events.py            # Socket.IO event handlers
│   └── templates/
│       └── index.html           # Web interface
├── scripts/                     # Utility scripts
│   ├── ingest.py                # Basic document ingestion
│   └── ingest_enhanced.py       # Enhanced ingestion with tests
├── docs/                        # Documentation
│   ├── DEPLOYMENT.md            # Deployment guide
│   └── OPTIMIZATION.md          # Performance optimization guide
├── data/                        # Document storage
├── vector_store/                # FAISS vector database
│   └── faiss_index/
├── .env                         # Environment configuration
├── .gitignore                   # Git ignore rules
├── Dockerfile                   # Docker configuration
├── requirements.txt             # Python dependencies
├── run.py                       # Application entrypoint
├── monitor_system.py            # System performance monitoring
├── start_optimized.sh           # Optimized startup script
├── setup_optimized.sh           # Optimization setup script
└── README.md                    # This file
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
1. Check the troubleshooting section above
2. Review the performance monitoring output
3. Check system resources with `python3 monitor_system.py`
4. Open an issue in the repository

## 📚 Additional Resources

- [Deployment Guide](docs/DEPLOYMENT.md) - Docker and production deployment
- [Optimization Guide](docs/OPTIMIZATION.md) - Performance tuning for constrained environments
- [Ollama Documentation](https://ollama.com/docs)
- [Flask-SocketIO Documentation](https://flask-socketio.readthedocs.io/)
- [FAISS Documentation](https://faiss.ai/)

---

**Note**: This project is specifically optimized for 2-core, 8GB RAM virtual machines. For different hardware configurations, you may need to adjust the settings in `.env` and the optimization parameters.
