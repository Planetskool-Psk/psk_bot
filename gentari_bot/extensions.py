"""Flask extension instances."""

from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*")
