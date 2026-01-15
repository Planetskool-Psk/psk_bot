"""HTTP routes for the Gentari Bot web application."""

import time
from typing import Any, Dict, List

from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context

bp = Blueprint("main", __name__)


@bp.get("/")
def index() -> str:
    return render_template("index.html")


@bp.get("/healthz")
def healthcheck():
    services = current_app.extensions.get("services")
    rag_ready = bool(services and services.rag_service.ready)
    vector_ready = bool(services and services.vector_store.ensure_ready())
    status_code = 200 if rag_ready and vector_ready else 503
    return (
        jsonify(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "rag_ready": rag_ready,
                "vector_store_ready": vector_ready,
                "model": services.llm._model if services else None,  # noqa: SLF001 - simple telemetry
            }
        ),
        status_code,
    )


@bp.post("/api/chat")
def api_chat():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = str(payload.get("question") or payload.get("message") or "").strip()
    history: List[Dict[str, str]] = payload.get("history") or []
    if not question:
        return jsonify({"error": "Question is required."}), 400

    services = current_app.extensions.get("services")
    if not services or not services.rag_service.ready:
        return jsonify({"error": "Service unavailable. Please ingest documents first."}), 503

    start = time.perf_counter()
    tokens: List[str] = []
    for token in services.rag_service.get_response_stream(question, history):
        tokens.append(token)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return jsonify({"response": "".join(tokens), "latency_ms": elapsed_ms})


@bp.post("/api/stream")
def api_stream():
    """Streaming endpoint using Server-Sent Events (SSE) for real-time responses."""
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = str(payload.get("question") or payload.get("message") or "").strip()
    history: List[Dict[str, str]] = payload.get("history") or []
    
    if not question:
        return jsonify({"error": "Question is required."}), 400

    services = current_app.extensions.get("services")
    if not services or not services.rag_service.ready:
        return jsonify({"error": "Service unavailable."}), 503

    def generate():
        try:
            for token in services.rag_service.get_response_stream(question, history):
                # SSE format: data: <content>\n\n
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


import re

# Greeting patterns - simple greetings that don't need RAG
GREETING_PATTERNS = [
    r"^(hi|hello|hey|hola|namaste|good\s*(morning|afternoon|evening|day))[\s!.,?]*$",
    r"^(hi|hello|hey)\s+(gia|there|bot)[\s!.,?]*$",
    r"^(what'?s\s*up|howdy|greetings)[\s!.,?]*$",
]

GREETING_RESPONSES = [
    "Hello! I'm Gia, your Gentari HR Assistant. How can I help you today?",
    "Hi there! I'm here to help with any HR-related questions you have. What would you like to know?",
    "Hello! Great to see you. Feel free to ask me anything about Gentari's HR policies.",
]

def is_greeting(text: str) -> bool:
    """Check if the text is a simple greeting."""
    text_lower = text.lower().strip()
    for pattern in GREETING_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def extract_search_terms(question: str) -> str:
    """Extract key search terms from a question for better semantic search.
    
    Removes common question words and articles to improve embedding match.
    E.g., "What is the Paternity Leave Policy?" -> "paternity leave policy"
    """
    # Common words to remove for better search
    stop_words = {
        # Question words
        'what', 'who', 'where', 'when', 'why', 'how', 'which', 'whom',
        # Articles and prepositions
        'is', 'are', 'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by',
        # Common verbs
        'can', 'could', 'would', 'should', 'do', 'does', 'did', 'have', 'has', 'had',
        'tell', 'me', 'about', 'explain', 'describe', 'give', 'get', 'please',
        # Pronouns
        'i', 'my', 'we', 'our', 'you', 'your', 'they', 'their',
    }
    
    # Clean the question
    import string
    text = question.lower()
    # Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # Split into words and filter
    words = text.split()
    key_words = [w for w in words if w not in stop_words and len(w) > 1]
    
    # If we have key words, use them; otherwise fall back to original
    if key_words:
        return ' '.join(key_words)
    return question


@bp.post("/api/prepare")
def api_prepare():
    """Prepare RAG context and return the prompt for direct Ollama call."""
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = str(payload.get("question") or payload.get("message") or "").strip()
    document_id = payload.get("document_id")  # Required: specific document to query
    history: List[Dict[str, str]] = payload.get("history") or []  # Conversation history
    
    if not question:
        return jsonify({"error": "Question is required."}), 400
    
    if not document_id:
        return jsonify({"error": "Please select a document to chat with."}), 400

    services = current_app.extensions.get("services")
    if not services or not services.rag_service.ready:
        return jsonify({"error": "Service unavailable."}), 503

    # Check if it's a simple greeting - respond directly without RAG
    if is_greeting(question):
        import random
        return jsonify({
            "is_greeting": True,
            "response": random.choice(GREETING_RESPONSES),
            "model": services.llm._model,
        })

    # Get RAG context and build prompt
    rag = services.rag_service
    
    # Use document-specific vector store
    documents = []
    from gentari_bot.services.vector_store import VectorStoreService
    from gentari_bot.services.document_manager import get_document_manager
    
    doc_manager = get_document_manager()
    doc_info = doc_manager.get_document(document_id)
    
    if not doc_info:
        return jsonify({"error": "Document not found."}), 404
    
    if doc_info.status != 'ready':
        return jsonify({"error": f"Document is still {doc_info.status}. Please wait."}), 400
    
    # Create vector store for this specific document
    doc_vector_store = VectorStoreService.for_document(document_id)
    if doc_vector_store.ensure_ready():
        # Extract key search terms for better semantic matching
        search_query = extract_search_terms(question)
        current_app.logger.info(f"Search query: '{question}' -> '{search_query}'")
        documents = doc_vector_store.search(search_query, k=5)  # More chunks for better accuracy
    
    # Build the current prompt with context
    if documents:
        current_prompt = rag._prompt_builder.build(question, documents, [])
    else:
        current_prompt = question
    
    # Build messages array for Ollama with conversation history
    # Format: system message (optional) + history + current question with RAG context
    history_messages = []
    
    # Add system message for consistent behavior
    system_message = """You are Gia, a friendly and knowledgeable HR assistant at Gentari. You speak naturally like a helpful colleague, not like a robot.

YOUR PERSONALITY:
- Warm, approachable, and professional
- Explain things clearly in your own words
- Be conversational, not mechanical

IMPORTANT RULES:
- Only use information from the context provided - never make things up
- NEVER say "According to Section...", "Page X says...", or reference document structure
- Rephrase information naturally while keeping all facts accurate
- Include specific numbers, dates, and details when answering
- If you don't have the information, say: "I don't have that specific information. Please reach out to HR at hr@gentari.com for assistance."
- NEVER provide links or URLs
- Use context from previous messages for follow-up questions"""
    
    history_messages.append({
        "role": "system",
        "content": system_message
    })
    
    # Add conversation history (limit to last 10 exchanges to avoid token overflow)
    max_history = 20  # 10 user + 10 assistant messages
    recent_history = history[-max_history:] if len(history) > max_history else history
    
    for msg in recent_history:
        if msg.get("role") in ["user", "assistant"]:
            history_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    # Add the current question with RAG context
    history_messages.append({
        "role": "user",
        "content": current_prompt
    })
    
    return jsonify({
        "prompt": current_prompt,
        "has_context": bool(documents),
        "model": services.llm._model,
        "options": rag._config.ollama_options,
        "history_messages": history_messages,
        "document_id": document_id
    })
