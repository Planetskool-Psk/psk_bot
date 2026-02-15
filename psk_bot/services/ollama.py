"""Wrapper around the Ollama client with guarded streaming."""

import os
import platform
from typing import Dict, Generator, List, Optional, Union

import ollama

from psk_bot.logging import get_logger
from psk_bot.settings import AppSettings, settings

logger = get_logger(__name__)


def _detect_thread_count() -> int:
    """Auto-detect optimal thread count for the current machine."""
    try:
        cpu_count = os.cpu_count() or 2
        # Use physical cores (not hyperthreads) for best LLM perf
        if platform.system() == "Darwin":
            # macOS: performance cores are better for LLM
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                perf_cores = int(result.stdout.strip())
                logger.info("Detected %d performance cores on macOS", perf_cores)
                return max(perf_cores, 2)
        return max(cpu_count - 1, 2)  # Leave 1 core for the OS
    except Exception:
        return 2


# Generation options tuned for speed
DEFAULT_GENERATION_OPTIONS: Dict[str, Union[int, float, bool]] = {
    "num_batch": 512,  # Larger batch = faster prompt processing
    "repeat_penalty": 1.1,
    "repeat_last_n": 64,
    "mirostat": 0,
    "seed": -1,
    "numa": False,
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
            # Warm up the model so first request is fast
            self._warmup()
        except Exception as exc:  # noqa: BLE001 - surface full error details
            logger.error("Failed to initialise Ollama client: %s", exc)
            self._client = None

    def _warmup(self) -> None:
        """Pre-load the model into memory so the first real request is fast."""
        if not self._client:
            return
        try:
            # A tiny generate call keeps the model loaded in RAM
            self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": "hi"}],
                stream=False,
                options={"num_predict": 1},
                keep_alive=self._keep_alive,
            )
            logger.info("Model '%s' warmed up and loaded in memory", self._model)
        except Exception:
            logger.debug("Model warmup skipped (non-critical)")

    def stream_response(self, prompt: str) -> Generator[str, None, None]:
        """Yield response chunks from the configured Ollama model (single prompt)."""
        yield from self.stream_chat([{"role": "user", "content": prompt}])

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        *,
        options_override: Optional[Dict[str, Union[int, float]]] = None,
    ) -> Generator[str, None, None]:
        """Yield response chunks for a multi-turn conversation.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            options_override: Per-call option overrides merged on top of defaults.
        """
        if not self._client:
            logger.warning("Attempted to stream without an active Ollama client")
            yield "Error: Ollama service is not available."
            return

        merged_options = {**self._options, **(options_override or {})}

        try:
            stream = self._client.chat(
                model=self._model,
                messages=messages,
                stream=True,
                options=merged_options,
                keep_alive=self._keep_alive,
            )
            for chunk in stream:
                content = chunk.get("message", {}).get("content")
                if content:
                    yield content
        except Exception:  # noqa: BLE001 - we need to surface all client failures
            logger.exception("Error streaming from Ollama")
            yield "Error: Could not get a response from the language model."

    @property
    def model(self) -> str:
        return self._model

    @property
    def client(self) -> Optional[ollama.Client]:
        return self._client
