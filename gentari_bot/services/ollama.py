"""Wrapper around the Ollama client with guarded streaming."""

from typing import Dict, Generator, Optional, Union

import ollama

from gentari_bot.logging import get_logger
from gentari_bot.settings import settings

logger = get_logger(__name__)

DEFAULT_GENERATION_OPTIONS: Dict[str, Union[int, float]] = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 30,
    "num_ctx": 3072,
    "num_predict": 800,
    "repeat_penalty": 1.1,
    "repeat_last_n": 64,
    "num_thread": 2,
    "num_gpu": 0,
}


class OllamaService:
    """Small helper that abstracts Ollama client lifecycle and streaming."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 180,
    ) -> None:
        self._base_url = base_url or settings.ollama_base_url
        self._model = model or settings.ollama_model
        self._timeout = timeout
        self._client: Optional[ollama.Client] = None
        self._initialise_client()

    def _initialise_client(self) -> None:
        try:
            self._client = ollama.Client(host=self._base_url, timeout=self._timeout)
            self._client.list()
            logger.info("Connected to Ollama at %s", self._base_url)
        except Exception as exc:  # noqa: BLE001 - surface full error details
            logger.error("Failed to initialise Ollama client: %s", exc)
            self._client = None

    def stream_response(self, prompt: str) -> Generator[str, None, None]:
        """Yield response chunks from the configured Ollama model."""
        if not self._client:
            logger.warning("Attempted to stream without an active Ollama client")
            yield "Error: Ollama service is not available."
            return

        try:
            stream = self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options=DEFAULT_GENERATION_OPTIONS,
            )
            for chunk in stream:
                content = chunk.get("message", {}).get("content")
                if content:
                    yield content
        except Exception:  # noqa: BLE001 - we need to surface all client failures
            logger.exception("Error streaming from Ollama")
            yield "Error: Could not get a response from the language model."
