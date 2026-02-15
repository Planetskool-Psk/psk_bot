"""HTTP routes for the PSK Bot web application."""

import json
import time
from collections import defaultdict
from functools import wraps
from threading import Lock
from typing import Any, Dict, List

from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context

bp = Blueprint("main", __name__)

# ─── Rate limiter for robot API ───────────────────────────────────────
_rate_limits: Dict[str, List[float]] = defaultdict(list)
_rate_lock = Lock()


def _check_rate_limit(client_id: str, max_per_minute: int) -> bool:
    """Simple in-memory sliding-window rate limiter."""
    now = time.time()
    window = 60.0
    with _rate_lock:
        timestamps = _rate_limits[client_id]
        # Remove old entries
        _rate_limits[client_id] = [t for t in timestamps if now - t < window]
        if len(_rate_limits[client_id]) >= max_per_minute:
            return False
        _rate_limits[client_id].append(now)
        return True


def require_api_key(f):
    """Decorator to enforce API key authentication on robot endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from psk_bot.settings import settings
        api_key = settings.api_key
        if not api_key:
            return f(*args, **kwargs)  # No key configured = open access
        provided = request.headers.get("X-API-Key") or request.args.get("api_key") or ""
        if provided != api_key:
            return jsonify({"error": "Invalid or missing API key."}), 401
        return f(*args, **kwargs)
    return decorated


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
                "model": services.llm.model if services else None,
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


@bp.post("/api/stream_prepared")
def api_stream_prepared():
    """Stream a response from Ollama using pre-built messages from /api/prepare endpoints.

    This is the production-safe alternative to calling Ollama directly from the browser.
    The frontend calls /api/prepare or /api/prepare_free first to build the prompt with
    RAG context, then sends the resulting messages here for streaming.

    Request JSON:
        {
            "messages": [...],  // from prepare endpoint's history_messages
            "model": "gemma3:1b",
            "options": {...}    // from prepare endpoint
        }

    Response: SSE stream with JSON events:
        data: {"token": "Hello", "type": "token"}
        data: {"type": "done"}
    """
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    messages = payload.get("messages") or payload.get("history_messages")
    model = payload.get("model")
    options = payload.get("options") or {}

    if not messages:
        return jsonify({"error": "messages is required."}), 400

    services = current_app.extensions.get("services")
    if not services:
        return jsonify({"error": "Service unavailable."}), 503

    # Use the LLM service's public API
    llm = services.llm
    if not llm.client:
        return jsonify({"error": "Ollama is not available."}), 503

    target_model = model or llm.model
    merged_options = {**llm._options, **options}

    def generate():
        try:
            for token in llm.stream_chat(messages, options_override=options):
                yield f"data: {json.dumps({'token': token, 'type': 'token'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            current_app.logger.exception("Error in stream_prepared")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


import re

# Greeting patterns - simple greetings that don't need RAG
GREETING_PATTERNS = [
    r"^(hi|hello|hey|hola|namaste|good\s*(morning|afternoon|evening|day))[\s!.,?]*$",
    r"^(hi|hello|hey)\s+(there|bot|psk|buddy|friend)[\s!.,?]*$",
    r"^(what'?s\s*up|howdy|greetings|sup|yo)[\s!.,?]*$",
    r"^(thanks|thank\s*you|thx|ty)[\s!.,?]*$",
]

GREETING_RESPONSES = [
    "Hello! I'm PSK Bot. How can I assist you today?",
    "Hi there. I'm ready to help — feel free to ask your question.",
    "Welcome! Let me know what you'd like to know.",
]

THANK_RESPONSES = [
    "You're welcome. Let me know if there's anything else.",
    "Glad I could help. Feel free to ask anytime.",
    "Happy to assist. I'm here if you need anything else.",
]

def is_greeting(text: str) -> bool:
    """Check if the text is a simple greeting or thank you."""
    text_lower = text.lower().strip()
    for pattern in GREETING_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def is_thank_you(text: str) -> bool:
    """Check if the text is a thank you message."""
    text_lower = text.lower().strip()
    return bool(re.match(r"^(thanks|thank\s*you|thx|ty|cheers)[\s!.,?]*$", text_lower, re.IGNORECASE))


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
        if is_thank_you(question):
            resp = random.choice(THANK_RESPONSES)
        else:
            resp = random.choice(GREETING_RESPONSES)
        return jsonify({
            "is_greeting": True,
            "response": resp,
            "model": services.llm.model,
        })

    # Get RAG context and build prompt
    rag = services.rag_service
    
    # Use document-specific vector store
    documents = []
    from psk_bot.services.vector_store import VectorStoreService
    from psk_bot.services.document_manager import get_document_manager
    
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
        documents = doc_vector_store.search(search_query, k=5)

    # Always build a RAG prompt from the selected document — never fall back to general LLM
    current_prompt = rag._prompt_builder.build(question, documents, [])
    
    # Build messages array for Ollama with conversation history
    # Format: system message (optional) + history + current question with RAG context
    history_messages = []
    
    # Add system message for consistent behavior
    system_message = (
        "You are PSK Bot, a professional AI assistant.\n"
        "Guidelines:\n"
        "- Answer ONLY from the provided document context. Do not use outside knowledge.\n"
        "- If the answer is not in the context, clearly state: 'This information is not available in the selected document.'\n"
        "- Be precise and to the point. Avoid long paragraphs — use bullet points or short statements.\n"
        "- Maintain a professional, clear tone. No excessive emojis or filler language.\n"
        "- Never reference document internals (no 'Section X', 'Page Y', 'Document 1').\n"
        "- For follow-up questions, use conversation history for continuity.\n"
        "- Do not fabricate or infer information beyond what is explicitly stated in the context."
    )
    
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
        "model": services.llm.model,
        "options": rag._config.ollama_options,
        "history_messages": history_messages,
        "document_id": document_id
    })


@bp.post("/api/prepare_free")
def api_prepare_free():
    """Prepare a prompt for free-form chat without requiring a document.
    Uses direct LLM conversation for general knowledge."""
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = str(payload.get("question") or payload.get("message") or "").strip()
    history: List[Dict[str, str]] = payload.get("history") or []

    if not question:
        return jsonify({"error": "Question is required."}), 400

    services = current_app.extensions.get("services")
    if not services:
        return jsonify({"error": "Service unavailable."}), 503

    # Check if it's a greeting
    if is_greeting(question):
        import random
        if is_thank_you(question):
            resp = random.choice(THANK_RESPONSES)
        else:
            resp = random.choice(GREETING_RESPONSES)
        return jsonify({
            "is_greeting": True,
            "response": resp,
            "model": services.llm.model,
        })

    # Build prompt — direct LLM conversation (no web search)
    rag = services.rag_service
    current_prompt = question

    system_message = (
        "You are PSK Bot, a professional AI assistant.\n"
        "Guidelines:\n"
        "- Use your general knowledge to answer the question.\n"
        "- Be precise and direct. Avoid filler or essay-length responses.\n"
        "- Use bullet points or numbered lists when presenting multiple items.\n"
        "- Maintain a professional, clear tone throughout.\n"
        "- If you're uncertain about something, state it clearly."
    )

    history_messages = [{"role": "system", "content": system_message}]

    max_history = 20
    recent_history = history[-max_history:] if len(history) > max_history else history
    for msg in recent_history:
        if msg.get("role") in ["user", "assistant"]:
            history_messages.append({"role": msg["role"], "content": msg["content"]})

    history_messages.append({"role": "user", "content": current_prompt})

    return jsonify({
        "prompt": current_prompt,
        "has_context": False,
        "model": services.llm.model,
        "options": rag._config.ollama_options,
        "history_messages": history_messages,
    })


# ═══════════════════════════════════════════════════════════════════════
# ROBOT / HARDWARE API — low-latency, direct response endpoints
# ═══════════════════════════════════════════════════════════════════════

@bp.post("/api/v1/chat")
@require_api_key
def robot_chat():
    """Direct chat endpoint optimized for robot hardware.
    
    Accepts a question and returns a complete response in one call.
    Supports both document-based RAG and free-form direct LLM queries.
    Designed for low-latency, single-request/response pattern.
    
    Request JSON:
        {
            "message": "What is the leave policy?",
            "document_id": "optional_doc_id",
            "session_id": "robot_01",
            "history": [...]  // optional
        }
    
    Response JSON:
        {
            "response": "...",
            "latency_ms": 1234,
            "source": "document" | "llm" | "greeting",
            "session_id": "robot_01"
        }
    """
    from psk_bot.settings import settings as app_settings

    # Rate limiting
    client_id = request.headers.get("X-Client-ID", request.remote_addr or "unknown")
    if not _check_rate_limit(client_id, app_settings.api_rate_limit):
        return jsonify({"error": "Rate limit exceeded. Please wait."}), 429

    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = str(payload.get("message") or payload.get("question") or "").strip()
    document_id = payload.get("document_id")
    session_id = str(payload.get("session_id", client_id))
    history: List[Dict[str, str]] = payload.get("history") or []

    if not question:
        return jsonify({"error": "Message is required."}), 400

    services = current_app.extensions.get("services")
    if not services:
        return jsonify({"error": "Service unavailable."}), 503

    start = time.perf_counter()

    # Handle greetings instantly
    if is_greeting(question):
        import random
        resp = random.choice(THANK_RESPONSES if is_thank_you(question) else GREETING_RESPONSES)
        return jsonify({
            "response": resp,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "source": "greeting",
            "session_id": session_id,
        })

    rag = services.rag_service
    source = "llm"

    # If document_id is provided, do document-specific RAG
    if document_id:
        from psk_bot.services.vector_store import VectorStoreService
        from psk_bot.services.document_manager import get_document_manager

        doc_manager = get_document_manager()
        doc_info = doc_manager.get_document(document_id)
        if not doc_info:
            return jsonify({"error": "Document not found."}), 404
        if doc_info.status != "ready":
            return jsonify({"error": f"Document is still {doc_info.status}."}), 400

        doc_vector_store = VectorStoreService.for_document(document_id)
        documents = []
        if doc_vector_store.ensure_ready():
            search_query = extract_search_terms(question)
            documents = doc_vector_store.search(search_query, k=5)
        source = "document"
        # Always answer from the selected document — no LLM fallback
        prompt = rag._prompt_builder.build(question, documents, history)
    else:
        # Free-form: direct LLM conversation
        source = "llm"
        prompt = question

    # Stream internally and collect full response
    tokens: List[str] = []
    for token in services.llm.stream_response(prompt):
        tokens.append(token)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return jsonify({
        "response": "".join(tokens),
        "latency_ms": elapsed_ms,
        "source": source,
        "session_id": session_id,
    })


@bp.post("/api/v1/chat/stream")
@require_api_key
def robot_chat_stream():
    """SSE streaming endpoint for robot hardware.
    
    Same as /api/v1/chat but streams tokens via Server-Sent Events.
    Use this when the robot needs to display text as it generates.
    
    SSE format:
        data: {"token": "Hello", "type": "token"}
        data: {"type": "done", "latency_ms": 1234, "source": "document"}
    """
    from psk_bot.settings import settings as app_settings

    client_id = request.headers.get("X-Client-ID", request.remote_addr or "unknown")
    if not _check_rate_limit(client_id, app_settings.api_rate_limit):
        return jsonify({"error": "Rate limit exceeded."}), 429

    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = str(payload.get("message") or payload.get("question") or "").strip()
    document_id = payload.get("document_id")
    session_id = str(payload.get("session_id", client_id))
    history: List[Dict[str, str]] = payload.get("history") or []

    if not question:
        return jsonify({"error": "Message is required."}), 400

    services = current_app.extensions.get("services")
    if not services:
        return jsonify({"error": "Service unavailable."}), 503

    rag = services.rag_service

    def generate():
        start = time.perf_counter()
        source = "llm"

        # Greetings — instant
        if is_greeting(question):
            import random
            resp = random.choice(THANK_RESPONSES if is_thank_you(question) else GREETING_RESPONSES)
            yield f"data: {json.dumps({'token': resp, 'type': 'token'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'latency_ms': int((time.perf_counter() - start) * 1000), 'source': 'greeting', 'session_id': session_id})}\n\n"
            return

        # Build prompt
        if document_id:
            from psk_bot.services.vector_store import VectorStoreService
            from psk_bot.services.document_manager import get_document_manager
            doc_manager = get_document_manager()
            doc_info = doc_manager.get_document(document_id)
            documents = []
            if doc_info and doc_info.status == "ready":
                doc_vs = VectorStoreService.for_document(document_id)
                if doc_vs.ensure_ready():
                    documents = doc_vs.search(extract_search_terms(question), k=5)
            source = "document"
            # Always answer from the selected document — no LLM fallback
            prompt = rag._prompt_builder.build(question, documents, history)
        else:
            # Free-form: direct LLM conversation
            source = "llm"
            prompt = question

        # Stream tokens
        try:
            for token in services.llm.stream_response(prompt):
                yield f"data: {json.dumps({'token': token, 'type': 'token'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error: {str(e)}', 'type': 'error'})}\n\n"

        elapsed = int((time.perf_counter() - start) * 1000)
        yield f"data: {json.dumps({'type': 'done', 'latency_ms': elapsed, 'source': source, 'session_id': session_id})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@bp.get("/api/v1/health")
@require_api_key
def robot_health():
    """Lightweight health check for robot hardware monitoring."""
    services = current_app.extensions.get("services")
    rag_ready = bool(services and services.rag_service.ready)
    return jsonify({
        "status": "ok" if rag_ready else "degraded",
        "model": services.llm.model if services else None,
        "timestamp": time.time(),
    }), 200 if rag_ready else 503


@bp.get("/api/v1/documents")
@require_api_key
def robot_list_documents():
    """List available documents the robot can query."""
    from psk_bot.services.document_manager import get_document_manager
    doc_manager = get_document_manager()
    docs = []
    for doc_id, doc in doc_manager.get_all_documents().items():
        docs.append({
            "id": doc_id,
            "name": doc.original_filename,
            "status": doc.status,
        })
    return jsonify({"documents": docs})
