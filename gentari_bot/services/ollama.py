"""Wrapper around the Ollama client with guarded streaming."""

from typing import Dict, Generator, Optional, Union

import ollama

from gentari_bot.logging import get_logger
from gentari_bot.settings import AppSettings, settings

logger = get_logger(__name__)

# Baseline generation options; tuned for maximum speed on CPU
DEFAULT_GENERATION_OPTIONS: Dict[str, Union[int, float, bool]] = {
    "num_gpu": 0,  # CPU only
    "num_batch": 128,  # Small batch for low RAM
    "repeat_penalty": 1.0,  # No penalty = fastest
    "repeat_last_n": 0,  # Disabled
    "mirostat": 0,  # Disabled
    "num_keep": 0,  # Don't cache
    "seed": 42,  # Fixed seed = faster, consistent
}


class OllamaService:
    """Small helper that abstracts Ollama client lifecycle and streaming."""

    def __init__(
        self,
        *,
        config: AppSettings = settings,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        options: Optional[Dict[str, Union[int, float]]] = None,
    ) -> None:
        self._config = config
        self._base_url = base_url or config.ollama_base_url
        self._model = model or config.ollama_model
        self._timeout = timeout or config.llm_timeout
        self._client: Optional[ollama.Client] = None
        self._options = {**DEFAULT_GENERATION_OPTIONS, **config.ollama_options}
        if options:
            self._options.update(options)
        self._keep_alive = config.ollama_keep_alive
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
                options=self._options,
                keep_alive=self._keep_alive,
            )
            for chunk in stream:
                content = chunk.get("message", {}).get("content")
                if content:
                    yield content
        except Exception:  # noqa: BLE001 - we need to surface all client failures
            logger.exception("Error streaming from Ollama")
            yield "Error: Could not get a response from the language model."
