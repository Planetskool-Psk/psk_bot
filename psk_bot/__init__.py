"""PSK Bot application factory."""

from pathlib import Path
from typing import TYPE_CHECKING

from psk_bot.logging import configure_logging, get_logger
from psk_bot.settings import settings
from psk_bot.web import bp as web_bp
from psk_bot.web.admin import admin_bp

if TYPE_CHECKING:
    from flask import Flask

configure_logging()
logger = get_logger(__name__)


def create_app() -> "Flask":
    """Create and configure the Flask application."""
    from flask import Flask  # Local import to avoid hard dependency during non-web tasks
    from flask_cors import CORS
    from psk_bot.container import build_container

    template_folder = Path(__file__).resolve().parent / "templates"
    static_folder = Path(__file__).resolve().parent / "static"
    app = Flask(__name__, template_folder=str(template_folder), static_folder=str(static_folder))
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["APP_SETTINGS"] = settings

    # Enable CORS for API endpoints (allows chatbot widget on different origins)
    CORS(app, resources={r"/api/*": {"origins": "*"}, r"/admin/api/*": {"origins": "*"}})

    app.register_blueprint(web_bp)
    app.register_blueprint(admin_bp)  # Admin routes for document management

    # Swagger UI for API documentation
    from flask_swagger_ui import get_swaggerui_blueprint
    SWAGGER_URL = "/docs"
    API_SPEC_URL = "/static/swagger.json"
    swagger_bp = get_swaggerui_blueprint(
        SWAGGER_URL, API_SPEC_URL,
        config={"app_name": "PSK Bot API", "layout": "BaseLayout"}
    )
    app.register_blueprint(swagger_bp, url_prefix=SWAGGER_URL)

    # Initialise long-lived services once at startup
    services = build_container(settings)
    app.extensions["services"] = services
    app.extensions["rag_service"] = services.rag_service  # Backwards compatibility
    app.extensions["conversation_store"] = services.conversation_store
    if services.rag_service.ready:
        logger.info("RAG service initialised and ready")
    else:
        logger.warning("RAG service initialised but not ready")

    return app


__all__ = ["create_app"]
