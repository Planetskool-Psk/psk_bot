"""Retrieval augmented generation orchestration with hybrid web search."""

import time
from collections import OrderedDict
from typing import Dict, Generator, Iterable, List, Optional, Tuple

from psk_bot.logging import get_logger
from psk_bot.settings import AppSettings, settings

from .ollama import OllamaService
from .vector_store import VectorStoreService
from .web_search import WebSearchService

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
        truncated = text[:limit]
        last_period = truncated.rfind('.')
        if last_period > limit * 0.7:
            return truncated[:last_period + 1] + "\n[Content truncated for brevity]"
        return truncated + "..."

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        if not history:
            return ""
        turns = history[-self._config.prompt_history_turns:]
        formatted = []
        for turn in turns:
            user_msg = turn.get('user', '').strip()
            bot_msg = turn.get('bot', '').strip()
            if len(bot_msg) > 200:
                bot_msg = bot_msg[:200] + "..."
            formatted.append(f"User: {user_msg}\nAssistant: {bot_msg}")
        return "\n---\n".join(formatted)

    def _select_context(self, documents: List[Dict[str, object]], web_context: str = "") -> str:
        parts = []

        if documents:
            seen_content = set()
            doc_parts = []
            for idx, doc in enumerate(documents[:self._config.max_context_documents], start=1):
                content = str(doc.get("content", "")).strip()
                if not content:
                    continue
                content_key = content[:200].lower().replace(" ", "")
                if content_key in seen_content:
                    continue
                seen_content.add(content_key)
                content = " ".join(content.split())
                score = float(doc.get("relevance", doc.get("similarity", doc.get("score", 0.0))))
                if score < 0.2 and idx > 3:
                    continue
                doc_parts.append(f"[Document Section {idx}]: {content}")
            if doc_parts:
                parts.append("📄 FROM YOUR DOCUMENTS:\n" + "\n\n".join(doc_parts))

        if web_context:
            parts.append("🌐 FROM THE WEB:\n" + web_context)

        if not parts:
            return "No relevant information found from documents or web search."

        combined = "\n\n---\n\n".join(parts)
        return self._truncate(combined, self._config.max_context_chars)

    def build(self, query: str, documents: List[Dict[str, object]], history: List[Dict[str, str]], web_context: str = "") -> str:
        context = self._select_context(documents, web_context)
        formatted_history = self._format_history(history)
        prompt = self._config.prompt_template.format(context=context, history=formatted_history, question=query)
        return prompt


class RAGService:
    """High level coordinator for retrieval augmented responses with hybrid web search."""

    def __init__(
        self,
        *,
        config: AppSettings = settings,
        vector_store: Optional[VectorStoreService] = None,
        llm: Optional[OllamaService] = None,
        web_search: Optional[WebSearchService] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        cache_size: int = 16,
    ) -> None:
        self._config = config
        self._vector_store = vector_store or VectorStoreService(config=config)
        self._llm = llm or OllamaService(config=config)
        self._web_search = web_search or WebSearchService(config=config)
        self._prompt_builder = prompt_builder or PromptBuilder(config)
        self._ready = self._vector_store.ensure_ready()
        self._response_cache: OrderedDict[Tuple[str, Tuple[Tuple[str, str], ...]], str] = OrderedDict()
        self._cache_size = cache_size
        if not self._ready:
            logger.warning("Vector store not ready; run ingestion before serving requests")

    @property
    def ready(self) -> bool:
        # Always ready now — we can fall back to web search
        return True

    @property
    def web_search(self) -> WebSearchService:
        return self._web_search

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
        """Yield streamed response tokens — uses documents first, falls back to web search."""
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

            # Step 1: Try document retrieval
            documents = []
            if self._vector_store.ensure_ready():
                documents = self._retrieve_documents(cleaned_query)

            # Step 2: If documents are weak or missing, try web search
            web_context = ""
            best_doc_score = 0.0
            if documents:
                best_doc_score = float(documents[0].get("relevance", documents[0].get("similarity", 0.0)))

            if (not documents or best_doc_score < 0.4) and self._web_search.enabled:
                logger.info("Documents insufficient (score=%.3f), searching the web...", best_doc_score)
                web_context = self._web_search.search_and_summarize(cleaned_query)

            if not documents and not web_context:
                fallback = (
                    "Hmm, I couldn't find anything specific about that from my documents or the web. 🤔 "
                    "Could you try rephrasing your question? Or if you'd like, I can help with something else!"
                )
                self._cache_store(cache_key, fallback)
                yield fallback
                return

            prompt = self._prompt_builder.build(cleaned_query, documents, history_list, web_context)
            retrieval_time = time.perf_counter() - start_time
            logger.info(
                "Prompt prepared in %.2fs (docs=%d, web=%s, context chars=%d)",
                retrieval_time,
                len(documents),
                bool(web_context),
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
                "Response generated in %.2fs (retrieval %.2fs, generation %.2fs)",
                total_time,
                retrieval_time,
                llm_time,
            )

            full_response = "".join(response_chunks)
            self._cache_store(cache_key, full_response)
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error during RAG pipeline")
            yield (
                "Oops! Something went wrong on my end. 😅 "
                "Please try again in a moment, or rephrase your question!"
            )
