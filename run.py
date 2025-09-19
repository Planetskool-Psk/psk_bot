"""Development entrypoint."""

import os

import eventlet

from gentari_bot import create_app, socketio
from gentari_bot.logging import get_logger

eventlet.monkey_patch()

logger = get_logger(__name__)
app = create_app()


def main() -> None:
    port = int(os.environ.get("PORT", "5173"))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    logger.info("Starting Flask-SocketIO server on port %s (debug=%s)", port, debug)
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
