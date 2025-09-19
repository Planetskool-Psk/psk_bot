"""Gentari Bot application factory."""

from pathlib import Path
from flask import Flask

from gentari_bot.extensions import socketio
from gentari_bot.logging import configure_logging, get_logger
from gentari_bot.services import RAGService
from gentari_bot.settings import settings
from gentari_bot.web import bp as web_bp

configure_logging()
logger = get_logger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    template_folder = Path(__file__).resolve().parent / "templates"
    app = Flask(__name__, template_folder=str(template_folder))
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["APP_SETTINGS"] = settings

    socketio.init_app(app, async_mode="eventlet")
    app.register_blueprint(web_bp)

    # Initialise long-lived services once at startup
    rag_service = RAGService()
    app.extensions["rag_service"] = rag_service
    if rag_service.ready:
        logger.info("RAG service initialised and ready")
    else:
        logger.warning("RAG service initialised but not ready")

    # Import socket event handlers after socketio initialisation
    from gentari_bot.websocket import events  # noqa: F401

    return app


__all__ = ["create_app", "socketio"]
