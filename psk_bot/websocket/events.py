"""Socket.IO event handlers."""

from collections import defaultdict
from threading import Lock
from typing import Any, Dict, List, Optional

from flask import current_app, request

from psk_bot.core.conversation import ConversationStore
from psk_bot.extensions import socketio
from psk_bot.logging import get_logger
from psk_bot.settings import settings

logger = get_logger(__name__)

# Session-level locks prevent concurrent requests from overwhelming low-resource hosts
_session_locks: Dict[str, Lock] = defaultdict(Lock)
_fallback_store = ConversationStore(max_length=settings.max_conversation_history)


def _get_conversation_store() -> ConversationStore:
    services = current_app.extensions.get("services")
    if services:
        return services.conversation_store
    return current_app.extensions.get("conversation_store", _fallback_store)


def _get_rag_service():
    services = current_app.extensions.get("services")
    if services:
        return services.rag_service
    return current_app.extensions.get("rag_service")


def _process_message(session_id: str, message: str, lock: Lock, rag_service, store: ConversationStore) -> None:
    history = store.get_history(session_id)
    response_buffer: List[str] = []
    try:
        for token in rag_service.get_response_stream(message, history):
            response_buffer.append(token)
            socketio.emit("stream_response", {"token": token}, to=session_id)
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled error during chat message handling")
        socketio.emit(
            "stream_response",
            {"token": "Oops! Something went wrong on my end. Please try again! 😅"},
            to=session_id,
        )
    else:
        store.append_turn(session_id, user=message, bot="".join(response_buffer))
    finally:
        socketio.emit("stream_end", to=session_id)
        lock.release()


@socketio.on("connect")
def handle_connect() -> None:
    session_id = request.sid
    store = _get_conversation_store()
    store.start_session(session_id)
    logger.info("Client connected: %s", session_id)
    socketio.emit("connection_success", {"sid": session_id}, to=session_id)


@socketio.on("disconnect")
def handle_disconnect(*args) -> None:  # Accept optional disconnect reason argument
    session_id = request.sid
    store = _get_conversation_store()
    store.end_session(session_id)
    _session_locks.pop(session_id, None)
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

    rag_service = _get_rag_service()
    if rag_service is None:
        logger.error("RAG service not initialised")
        socketio.emit(
            "stream_response",
            {"token": "Service unavailable. Please try again later."},
            to=session_id,
        )
        socketio.emit("stream_end", to=session_id)
        return

    lock: Optional[Lock] = _session_locks.get(session_id)
    if lock is None:
        lock = Lock()
        _session_locks[session_id] = lock

    if not lock.acquire(blocking=False):
        socketio.emit(
            "stream_response",
            {"token": "Still processing your previous question. Please wait..."},
            to=session_id,
        )
        socketio.emit("stream_end", to=session_id)
        return

    logger.info("Processing query from %s: %s", session_id, message)
    store = _get_conversation_store()
    socketio.start_background_task(_process_message, session_id, message, lock, rag_service, store)


@socketio.on_error_default
def default_error_handler(_: Exception) -> None:
    logger.exception("Unhandled Socket.IO error")
