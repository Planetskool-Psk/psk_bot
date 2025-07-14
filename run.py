# /rag-chatbot-ollama/run.py


import os
import eventlet
eventlet.monkey_patch()
from app import create_app, socketio
from utils.logger import log

app = create_app()

def main() -> None:
    port = int(os.environ.get("PORT", 5173))
    debug = os.environ.get("DEBUG", "False").lower() == "true"
    log.info(f"Starting Flask-SocketIO server with Eventlet on port {port} (debug={debug})...")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)

if __name__ == "__main__":
    main()
