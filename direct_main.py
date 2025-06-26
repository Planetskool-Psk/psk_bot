# ✅ Always do this FIRST
import eventlet

eventlet.monkey_patch()

from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from lib.app.direct_model_app import handle_conversation

# ========== Flask App & SocketIO Setup ==========
app = Flask(__name__)
CORS(app)
socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*",
    logger=True,  # Enable for debugging
    engineio_logger=True,
)
# Dictionary to track history per client session
session_histories = {}  # key = request.sid, value = list of messages


# ========== SocketIO Events ==========


@socketio.on("connect")
def on_connect():
    sid = request.sid
    session_histories[sid] = []  # Initialize history for this client
    print(f"🟢 Client connected: {sid}")
    emit("connected", {"msg": "You're connected to AmplusAssist!"})


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    session_histories.pop(sid, None)  # Clean up history
    print(f"🔴 Client disconnected: {sid}")


@socketio.on("message")
def handle_message(data):
    sid = request.sid
    history = session_histories.get(sid, [])

    # Get the user message
    if isinstance(data, dict):
        user_msg = data.get("message", "").strip()
    else:
        user_msg = str(data).strip()

    if not user_msg:
        emit("message", {"msg": "⚠️ Empty message received."})
        return

    print(f"📨 [{sid}] Message received: {user_msg}")

    try:
        # Pass conversation history to handler
        # history_text = "\n".join(history)
        response = handle_conversation(user_msg)

        # Save to session-specific history
        history.append(f"User: {user_msg}")
        history.append(f"AmplusAssist: {response}")
        session_histories[sid] = history

        print(f"🤖 [{sid}] Responding: {response}")
        emit("message", response)

    except Exception as e:
        print(f"❌ [{sid}] Error: {e}")
        emit("message", "⚠️ Sorry, something went wrong processing your message.")


# ========== Main App Runner ==========
if __name__ == "__main__":
    
    print("🚀 Server running at http://localhost:5173")
    socketio.run(app, host="localhost", port=5173, debug=True)
