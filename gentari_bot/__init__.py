"""Gentari Bot application factory."""

from pathlib import Path
from typing import TYPE_CHECKING

from gentari_bot.logging import configure_logging, get_logger
from gentari_bot.settings import settings
from gentari_bot.web import bp as web_bp
from gentari_bot.web.admin import admin_bp

if TYPE_CHECKING:
    from flask import Flask

try:
    from gentari_bot.extensions import socketio
except Exception:  # pragma: no cover - allows ingestion without web deps installed
    socketio = None  # type: ignore[assignment]

configure_logging()
logger = get_logger(__name__)


def create_app() -> "Flask":
    """Create and configure the Flask application."""
    from flask import Flask  # Local import to avoid hard dependency during non-web tasks
    from gentari_bot.container import build_container
    from gentari_bot.extensions import socketio as ext_socketio

    template_folder = Path(__file__).resolve().parent / "templates"
    app = Flask(__name__, template_folder=str(template_folder))
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["APP_SETTINGS"] = settings

    ext_socketio.init_app(app, async_mode="gevent")
    app.register_blueprint(web_bp)
    app.register_blueprint(admin_bp)  # Admin routes for document management

    # Initialise long-lived services once at startup
    services = build_container(settings)
    app.extensions["services"] = services
    app.extensions["rag_service"] = services.rag_service  # Backwards compatibility
    app.extensions["conversation_store"] = services.conversation_store
    if services.rag_service.ready:
        logger.info("RAG service initialised and ready")
    else:
        logger.warning("RAG service initialised but not ready")

    # Import socket event handlers after socketio initialisation
    from gentari_bot.websocket import events  # noqa: F401

    return app


__all__ = ["create_app", "socketio"]
