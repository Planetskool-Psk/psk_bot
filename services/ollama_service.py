# /rag-chatbot-ollama/services/ollama_service.py

import ollama
from utils.logger import log
import config


class OllamaService:
    def __init__(self):
        try:
            self.client = ollama.Client(host=config.OLLAMA_BASE_URL)
            log.info("Ollama client initialized.")
            # Check connection
            self.client.list()
            log.info("Successfully connected to Ollama.")
        except Exception as e:
            log.error(
                f"Failed to connect to Ollama at {config.OLLAMA_BASE_URL}. "
                f"Please ensure Ollama is running. Error: {e}"
            )
            self.client = None

    def stream_response(self, prompt):
        """Streams a response from the Ollama model."""
        if not self.client:
            yield "Error: Ollama service is not available."
            return

        try:
            stream = self.client.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in stream:
                if "content" in chunk["message"]:
                    yield chunk["message"]["content"]
        except Exception as e:
            log.error(f"Error streaming from Ollama: {e}")
            yield "Error: Could not get a response from the language model."
