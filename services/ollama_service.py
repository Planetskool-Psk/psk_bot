# /rag-chatbot-ollama/services/ollama_service.py

import ollama
from utils.logger import log
import config


class OllamaService:
    def __init__(self):
        try:
            # Initialize with timeout optimized for 2-core VM
            self.client = ollama.Client(host=config.OLLAMA_BASE_URL, timeout=180)  # 3 min timeout for faster feedback
            log.info("Ollama client initialized with optimized timeout for 2-core VM.")
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
            # Optimized parameters for 2-core VM with better answer quality
            stream = self.client.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options={
                    "temperature": 0.7,      # Slightly increased for more natural responses
                    "top_p": 0.9,           # Increased for better response variety
                    "top_k": 30,            # Increased for better word selection
                    "num_ctx": 3072,        # Increased context window for better understanding
                    "num_predict": 800,     # Increased response length for more complete answers
                    "repeat_penalty": 1.1,  # Prevent repetition
                    "repeat_last_n": 64,    # Check more tokens for repetition
                    "num_thread": 2,        # Match your VM's core count
                    "num_gpu": 0,           # Ensure CPU-only for consistency
                }
            )
            for chunk in stream:
                if "content" in chunk["message"]:
                    yield chunk["message"]["content"]
        except Exception as e:
            log.error(f"Error streaming from Ollama: {e}")
            yield "Error: Could not get a response from the language model."
