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
            # Optimized parameters for 2-core VM with 8GB RAM
            stream = self.client.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options={
                    "temperature": 0.6,      # Reduced for faster, more focused responses
                    "top_p": 0.8,           # Reduced for faster token selection
                    "top_k": 20,            # Reduced for less computation
                    "num_ctx": 2048,        # Reduced context window to save memory
                    "num_predict": 512,     # Limit response length for speed
                    "repeat_penalty": 1.05, # Slight reduction for faster processing
                    "repeat_last_n": 32,    # Reduced for less memory usage
                    "num_thread": 2,        # Match your VM's core count
                    "num_gpu": 0,           # Ensure CPU-only for consistency
                    "low_vram": True,       # Enable low memory mode
                }
            )
            for chunk in stream:
                if "content" in chunk["message"]:
                    yield chunk["message"]["content"]
        except Exception as e:
            log.error(f"Error streaming from Ollama: {e}")
            yield "Error: Could not get a response from the language model."
