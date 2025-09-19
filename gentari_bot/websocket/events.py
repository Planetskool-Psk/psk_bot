"""Socket.IO event handlers."""

from typing import Any, Dict, List

from flask import current_app, request

from gentari_bot.core.conversation import ConversationStore
from gentari_bot.extensions import socketio
from gentari_bot.logging import get_logger
from gentari_bot.settings import settings

logger = get_logger(__name__)
conversation_store = ConversationStore(settings.max_conversation_history)


@socketio.on("connect")
def handle_connect() -> None:
    session_id = request.sid
    conversation_store.start_session(session_id)
    logger.info("Client connected: %s", session_id)
    socketio.emit("connection_success", {"sid": session_id}, to=session_id)


@socketio.on("disconnect")
def handle_disconnect() -> None:
    session_id = request.sid
    conversation_store.end_session(session_id)
    logger.info("Client disconnected: %s", session_id)


@socketio.on("chat_message")
def handle_chat_message(payload: Dict[str, Any]) -> None:
    session_id = request.sid
    message = str(payload.get("message", "")).strip()
    if not message:
        logger.warning("Empty message received from %s", session_id)
        socketio.emit("stream_response", {"token": "Please provide a question."}, to=session_id)
        socketio.emit("stream_end", to=session_id)
        return

    rag_service = current_app.extensions.get("rag_service")
    if rag_service is None:
        logger.error("RAG service not initialised")
        socketio.emit(
            "stream_response",
            {"token": "Service unavailable. Please try again later."},
            to=session_id,
        )
        socketio.emit("stream_end", to=session_id)
        return

    history = conversation_store.get_history(session_id)
    logger.info("Processing query from %s: %s", session_id, message)

    response_buffer: List[str] = []
    try:
        for token in rag_service.get_response_stream(message, history):
            response_buffer.append(token)
            socketio.emit("stream_response", {"token": token}, to=session_id)
        socketio.emit("stream_end", to=session_id)
    except Exception:  # noqa: BLE001 - we need to catch stream failures
        logger.exception("Unhandled error during chat message handling")
        socketio.emit(
            "stream_response",
            {"token": "An error occurred while processing your request."},
            to=session_id,
        )
        socketio.emit("stream_end", to=session_id)
        return

    conversation_store.append_turn(session_id, user=message, bot="".join(response_buffer))


@socketio.on_error_default
def default_error_handler(_: Exception) -> None:
    logger.exception("Unhandled Socket.IO error")
