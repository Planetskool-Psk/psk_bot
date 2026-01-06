"""Retrieval augmented generation orchestration."""

import time
from collections import OrderedDict
from typing import Dict, Generator, Iterable, List, Optional, Tuple

from gentari_bot.logging import get_logger
from gentari_bot.settings import AppSettings, settings

from .ollama import OllamaService
from .vector_store import VectorStoreService

logger = get_logger(__name__)

_STOP_WORDS = {
    "what",
    "how",
    "when",
    "where",
    "why",
    "who",
    "is",
    "are",
    "can",
    "could",
    "would",
    "should",
}


class PromptBuilder:
    """Responsible for shaping RAG prompts consistently."""

    def __init__(self, config: AppSettings) -> None:
        self._config = config

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        # Try to truncate at a sentence boundary
        truncated = text[:limit]
        last_period = truncated.rfind('.')
        if last_period > limit * 0.7:  # If we can keep at least 70% of content
            return truncated[:last_period + 1] + "\n[Content truncated for brevity]"
        return truncated + "..."

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        if not history:
            return "No previous conversation in this session."
        turns = history[-self._config.prompt_history_turns:]
        formatted = []
        for turn in turns:
            user_msg = turn.get('user', '').strip()
            bot_msg = turn.get('bot', '').strip()
            # Truncate long previous responses to save context
            if len(bot_msg) > 200:
                bot_msg = bot_msg[:200] + "..."
            formatted.append(f"User: {user_msg}\nAssistant: {bot_msg}")
        return "\n---\n".join(formatted)

    def _select_context(self, documents: List[Dict[str, object]]) -> str:
        if not documents:
            return "No relevant documents found for this query."

        selected = []
        seen_content = set()
        
        for idx, doc in enumerate(documents[:self._config.max_context_documents], start=1):
            content = str(doc.get("content", "")).strip()
            if not content:
                continue
            
            # Deduplicate based on content similarity
            content_key = content[:150].lower().replace(" ", "")
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            
            # Clean up the content
            content = " ".join(content.split())  # Normalize whitespace
            
            score = float(doc.get("relevance", doc.get("similarity", doc.get("score", 0.0))))
            
            # Only include documents with reasonable relevance
            if score < 0.3 and idx > 2:
                continue
            
            # Add content without source labels - LLM will synthesize the info
            selected.append(content)

        if not selected:
            return "No sufficiently relevant documents found."
            
        combined = "\\n\\n".join(selected)
        return self._truncate(combined, self._config.max_context_chars)

    def build(self, query: str, documents: List[Dict[str, object]], history: List[Dict[str, str]]) -> str:
        context = self._select_context(documents)
        formatted_history = self._format_history(history)
        return self._config.prompt_template.format(context=context, history=formatted_history, question=query)


class RAGService:
    """High level coordinator for retrieval augmented responses."""

    def __init__(
        self,
        *,
        config: AppSettings = settings,
        vector_store: Optional[VectorStoreService] = None,
        llm: Optional[OllamaService] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        cache_size: int = 16,
    ) -> None:
        self._config = config
        self._vector_store = vector_store or VectorStoreService(config=config)
        self._llm = llm or OllamaService(config=config)
        self._prompt_builder = prompt_builder or PromptBuilder(config)
        self._ready = self._vector_store.ensure_ready()
        self._response_cache: OrderedDict[Tuple[str, Tuple[Tuple[str, str], ...]], str] = OrderedDict()
        self._cache_size = cache_size
        if not self._ready:
            logger.warning("Vector store not ready; run ingestion before serving requests")

    @property
    def ready(self) -> bool:
        return self._ready

    def _preprocess_query(self, query: str) -> str:
        tokens = [word for word in query.lower().split() if word not in _STOP_WORDS and len(word) > 2]
        if len(tokens) < 2:
            return query
        enhanced = " ".join(tokens)
        logger.debug("Query '%s' enhanced to '%s'", query, enhanced)
        return enhanced

    def _cache_key(self, query: str, history: List[Dict[str, str]]) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
        trimmed_history = history[-self._config.prompt_history_turns :]
        history_signature = tuple((turn.get("user", ""), turn.get("bot", "")) for turn in trimmed_history)
        return (query.strip().lower(), history_signature)

    def _cache_lookup(self, key: Tuple[str, Tuple[Tuple[str, str], ...]]) -> Optional[str]:
        if key in self._response_cache:
            self._response_cache.move_to_end(key)
            return self._response_cache[key]
        return None

    def _cache_store(self, key: Tuple[str, Tuple[Tuple[str, str], ...]], response: str) -> None:
        self._response_cache[key] = response
        if len(self._response_cache) > self._cache_size:
            self._response_cache.popitem(last=False)

    def _retrieve_documents(self, query: str) -> List[Dict[str, object]]:
        enhanced_query = self._preprocess_query(query)
        logger.info("Retrieving documents for query: '%s' (enhanced: '%s')", query, enhanced_query)
        candidates = self._vector_store.search(enhanced_query, k=self._config.max_context_documents)
        if not candidates:
            logger.info("Enhanced query produced no results; retrying with original query")
            candidates = self._vector_store.search(query, k=self._config.max_context_documents)
        return candidates

    def _yield_cached(self, cached_response: str) -> Generator[str, None, None]:
        chunk_size = 120
        for start in range(0, len(cached_response), chunk_size):
            yield cached_response[start : start + chunk_size]

    def get_response_stream(self, query: str, history: Iterable[Dict[str, str]]) -> Generator[str, None, None]:
        """Yield streamed response tokens for the provided query and history."""
        if not self._ready:
            self._ready = self._vector_store.ensure_ready()
        if not self._ready:
            yield "Error: The document knowledge base is not loaded. Please run the ingestion script."
            return

        try:
            history_list = list(history)
            cleaned_query = query.strip()
            cache_key = self._cache_key(cleaned_query, history_list)
            cached = self._cache_lookup(cache_key)
            if cached:
                logger.info("Returning cached response for query '%s'", cleaned_query)
                yield from self._yield_cached(cached)
                return

            start_time = time.perf_counter()
            documents = self._retrieve_documents(cleaned_query)
            if not documents:
                logger.warning("No relevant documents found for query '%s'", cleaned_query)
                fallback = (
                    "I appreciate your question, but I couldn't find relevant information in my knowledge base "
                    "to provide an accurate answer. For assistance with this topic, please reach out to the "
                    "HR team at hr@gentari.com or contact your HR business partner directly."
                )
                self._cache_store(cache_key, fallback)
                yield fallback
                return

            prompt = self._prompt_builder.build(cleaned_query, documents, history_list)
            retrieval_time = time.perf_counter() - start_time
            logger.info(
                "Prompt prepared in %.2fs after retrieval (context chars=%s)",
                retrieval_time,
                len(prompt),
            )

            llm_start = time.perf_counter()
            response_chunks: List[str] = []
            for token in self._llm.stream_response(prompt):
                response_chunks.append(token)
                yield token

            total_time = time.perf_counter() - start_time
            llm_time = time.perf_counter() - llm_start
            logger.info(
                "RAG response generated in %.2fs (retrieval %.2fs, generation %.2fs)",
                total_time,
                retrieval_time,
                llm_time,
            )

            full_response = "".join(response_chunks)
            self._cache_store(cache_key, full_response)
            best_score = float(documents[0].get("score", documents[0].get("relevance", 0.0)))
            if "contact the hr team" in full_response.lower() and best_score > 0.7:
                logger.warning("Potentially low quality response; best score %.3f", best_score)
        except Exception:  # noqa: BLE001 - capture unexpected runtime errors
            logger.exception("Unexpected error during RAG pipeline")
            yield (
                "I apologize for the inconvenience. I encountered a technical issue while processing your request. "
                "Please try again in a moment, or feel free to rephrase your question. If the issue persists, "
                "please contact the HR team directly for assistance."
            )
