# /rag-chatbot-ollama/app/__init__.py


from flask import Flask, render_template
from flask_socketio import SocketIO
from utils.logger import log
from services.rag_service import RAGService
from typing import Any

socketio = SocketIO()

def create_app() -> Any:
    """Creates and configures the Flask application."""
    app = Flask(__name__, template_folder="../templates")
    app.config["SECRET_KEY"] = "a_very_secret_key"  # TODO: Use env var in production

    @app.route("/")
    def index() -> str:
        return render_template("index.html")

    log.info("Initializing SocketIO...")
    # Use gevent or eventlet for async production
    socketio.init_app(app, async_mode="eventlet")

    with app.app_context():
        log.info("Initializing RAG Service and preloading models...")
        app.rag_service = RAGService()
        log.info("RAG Service initialization completed")
        from . import routes
    return app
