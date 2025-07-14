# /rag-chatbot-ollama/app/routes.py


from flask import request, render_template, current_app
from . import socketio
from utils.logger import log
import config
from typing import Dict, List, Any
import threading

# In-memory store for session-based conversation history (thread-safe)
session_histories: Dict[str, List[Dict[str, str]]] = {}
session_lock = threading.Lock()



@socketio.on("connect")
def handle_connect() -> None:
    """Handles a new WebSocket connection."""
    sid = request.sid
    log.info(f"Client connected: {sid}")
    with session_lock:
        session_histories[sid] = []
    socketio.emit("connection_success", {"sid": sid}, room=sid)



@socketio.on("disconnect")
def handle_disconnect() -> None:
    """Handles a WebSocket disconnection."""
    sid = request.sid
    log.info(f"Client disconnected: {sid}")
    with session_lock:
        if sid in session_histories:
            del session_histories[sid]



@socketio.on("chat_message")
def handle_chat_message(data: Dict[str, Any]) -> None:
    """Handles an incoming chat message from a user."""
    sid = request.sid
    query = data.get("message")
    if not query:
        log.warning(f"Received empty message from {sid}")
        return
    log.info(f"Received message from {sid}: {query}")
    rag_service = current_app.rag_service
    with session_lock:
        history = session_histories.get(sid, []).copy()
    full_bot_response = ""
    try:
        # Stream the response back to the client
        for token in rag_service.get_response_stream(query, history):
            full_bot_response += token
            socketio.emit("stream_response", {"token": token}, room=sid)
        socketio.emit("stream_end", room=sid)  # Signal that the stream is complete
    except Exception as e:
        log.error(f"Error during RAG processing for {sid}: {e}")
        socketio.emit("stream_response", {"token": "An error occurred."}, room=sid)
        socketio.emit("stream_end", room=sid)
    # Update conversation history
    with session_lock:
        history.append({"user": query, "bot": full_bot_response})
        session_histories[sid] = history[-config.MAX_CONVERSATION_HISTORY :]



@socketio.on_error_default
def default_error_handler(e: Exception) -> None:
    log.error(f"An unhandled SocketIO error occurred: {e}")
