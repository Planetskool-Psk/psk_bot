# /rag-chatbot-ollama/services/ollama_service.py

import ollama
from utils.logger import log
import config


class OllamaService:
    def __init__(self):
        try:
            # Initialize with timeout for gemma3:1b
            self.client = ollama.Client(host=config.OLLAMA_BASE_URL, timeout=300)  # 5 min timeout
            log.info("Ollama client initialized with extended timeout for gemma3:1b.")
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
        """Streams a response from the Ollama model with optimizations for gemma3:1b."""
        if not self.client:
            yield "Error: Ollama service is not available."
            return

        try:
            # Optimized parameters for gemma3:1b model
            stream = self.client.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "num_ctx": 4096,  # Context window
                    "num_predict": -1,  # No limit on prediction length
                    "repeat_penalty": 1.1,
                    "repeat_last_n": 64,
                    "num_thread": 4,  # Use 4 threads for better performance
                }
            )
            for chunk in stream:
                if "content" in chunk["message"]:
                    yield chunk["message"]["content"]
        except Exception as e:
            log.error(f"Error streaming from Ollama: {e}")
            yield "Error: Could not get a response from the language model."
