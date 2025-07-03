# /rag-chatbot-ollama/run.py

import eventlet

# Monkey patch the standard library for eventlet compatibility
eventlet.monkey_patch()

from app import create_app, socketio
from utils.logger import log

app = create_app()

if __name__ == "__main__":
    log.info("Starting Flask-SocketIO server with Eventlet...")
    # Use socketio.run for integrated server with WebSocket support
    socketio.run(app, host="0.0.0.0", port=5101, debug=True)
