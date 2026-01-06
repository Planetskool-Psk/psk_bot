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


@bp.post("/api/prepare")
def api_prepare():
    """Prepare RAG context and return the prompt for direct Ollama call."""
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = str(payload.get("question") or payload.get("message") or "").strip()
    
    if not question:
        return jsonify({"error": "Question is required."}), 400

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
    documents = rag._retrieve_documents(question)
    
    if not documents:
        return jsonify({
            "prompt": question,
            "has_context": False,
            "model": services.llm._model,
            "options": rag._config.ollama_options
        })
    
    # Build prompt with context
    prompt = rag._prompt_builder.build(question, documents, [])
    
    return jsonify({
        "prompt": prompt,
        "has_context": True,
        "model": services.llm._model,
        "options": rag._config.ollama_options
    })
