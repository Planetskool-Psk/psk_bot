# /rag-chatbot-ollama/app/__init__.py

from flask import Flask, render_template  # <-- ADD render_template HERE
from flask_socketio import SocketIO
from utils.logger import log
from services.rag_service import RAGService

socketio = SocketIO()


def create_app():
    """Creates and configures the Flask application."""
    # The template_folder path is relative to the app's root, so it should be correct
    app = Flask(__name__, template_folder="../templates")
    app.config["SECRET_KEY"] = "a_very_secret_key"

    # +++ START OF ADDED CODE +++
    # This route will serve your main chat page
    @app.route("/")
    def index():
        return render_template("index.html")

    # +++ END OF ADDED CODE +++

    log.info("Initializing SocketIO...")
    socketio.init_app(app, async_mode="eventlet")

    with app.app_context():
        # Initialize services
        log.info("Initializing RAG Service...")
        app.rag_service = RAGService()

        # Import and register SocketIO event handlers
        from . import routes

    return app
