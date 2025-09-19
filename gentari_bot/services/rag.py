"""Retrieval augmented generation orchestration."""

import time
from typing import Dict, Generator, Iterable, List, Optional

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


class RAGService:
    """High level coordinator for retrieval augmented responses."""

    def __init__(
        self,
        *,
        config: AppSettings = settings,
        vector_store: Optional[VectorStoreService] = None,
        llm: Optional[OllamaService] = None,
    ) -> None:
        self._config = config
        self._vector_store = vector_store or VectorStoreService(config=config)
        self._llm = llm or OllamaService()
        self._ready = self._vector_store.load_store()
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

    def _format_history(self, history: List[Dict[str, str]], limit: int = 2) -> str:
        if not history:
            return "No previous conversation."
        recent = history[-limit:]
        return "\n".join(f"Human: {turn['user']}\nAssistant: {turn['bot']}" for turn in recent)

    def _select_context(self, documents: List[Dict[str, object]], limit: int = 2) -> str:
        if not documents:
            return ""
        selected = []
        for idx, doc in enumerate(documents[:limit], start=1):
            content = str(doc.get("content", "")).strip()
            score = float(doc.get("score", 0))
            if content:
                selected.append(f"[Document {idx} - Relevance: {score:.3f}]\n{content}")
        combined = "\n\n".join(selected)
        return combined[:1500] + ("..." if len(combined) > 1500 else "")

    def _build_prompt(self, query: str, documents: List[Dict[str, object]], history: List[Dict[str, str]]) -> str:
        context = self._select_context(documents)
        formatted_history = self._format_history(history)
        return self._config.prompt_template.format(context=context, history=formatted_history, question=query)

    def _retrieve_documents(self, query: str) -> List[Dict[str, object]]:
        enhanced_query = self._preprocess_query(query)
        logger.info("Retrieving documents for query: '%s' (enhanced: '%s')", query, enhanced_query)
        candidates = self._vector_store.search(enhanced_query, k=self._config.top_k_results)
        if not candidates:
            logger.info("Enhanced query produced no results; retrying with original query")
            candidates = self._vector_store.search(query, k=self._config.top_k_results)
        return candidates

    def get_response_stream(self, query: str, history: Iterable[Dict[str, str]]) -> Generator[str, None, None]:
        """Yield streamed response tokens for the provided query and history."""
        if not self._ready:
            yield "Error: The document knowledge base is not loaded. Please run the ingestion script."
            return

        try:
            history_list = list(history)
            start_time = time.perf_counter()
            documents = self._retrieve_documents(query)
            if not documents:
                logger.warning("No relevant documents found for query '%s'", query)
                yield (
                    "I could not find any relevant information in the document to answer your question. "
                    "Please contact the HR team for assistance."
                )
                return

            prompt = self._build_prompt(query, documents, history_list)
            retrieval_time = time.perf_counter() - start_time
            logger.info("Prompt prepared in %.2fs after retrieval", retrieval_time)

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
            best_score = float(documents[0].get("score", 0.0))
            if "contact the hr team" in full_response.lower() and best_score > 0.7:
                logger.warning("Potentially low quality response; best score %.3f", best_score)
        except Exception:  # noqa: BLE001 - capture unexpected runtime errors
            logger.exception("Unexpected error during RAG pipeline")
            yield (
                "I apologize, but I encountered an error while processing your request. "
                "Please try rephrasing your question or contact the HR team for assistance."
            )
