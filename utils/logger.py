# /rag-chatbot-ollama/utils/logger.py

import logging
import sys


def setup_logger():
    """Sets up the application logger."""
    logger = logging.getLogger("RAG_Chatbot")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Add handler to the logger
    logger.addHandler(handler)

    return logger


log = setup_logger()
