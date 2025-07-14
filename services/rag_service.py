# /rag-chatbot-ollama/services/rag_service.py

from .vector_store_service import VectorStoreService
from .ollama_service import OllamaService
from utils.logger import log
import config



from typing import List, Dict, Generator, Any

class RAGService:
    def __init__(self) -> None:
        self.vector_store = VectorStoreService()
        self.ollama_service = OllamaService()
        self.is_ready = self.vector_store.load_store()
        if not self.is_ready:
            log.warning("RAG service is not ready. Please run the ingestion script.")

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        """Formats conversation history for the prompt."""
        if not history:
            return "No previous conversation."
        formatted = []
        for turn in history:
            formatted.append(f"User: {turn['user']}\nAssistant: {turn['bot']}")
        return "\n\n".join(formatted)

    def _create_prompt(self, query: str, context_docs: List[Dict[str, Any]], history: List[Dict[str, str]]) -> str:
        """Creates the final prompt for the LLM."""
        context = "\n---\n".join([doc["content"] for doc in context_docs])
        formatted_history = self._format_history(history)
        return config.PROMPT_TEMPLATE.format(
            context=context, history=formatted_history, question=query
        )

    def get_response_stream(self, query: str, history: List[Dict[str, str]]) -> Generator[str, None, None]:
        """Gets a streamed response from the RAG pipeline, with timing and performance logging."""
        import time
        if not self.is_ready:
            yield "Error: The document knowledge base is not loaded. Please run the ingestion script."
            return
        try:
            t0 = time.perf_counter()
            log.info(f"Performing semantic search for query: '{query}'")
            # Limit history and docs for speed
            limited_history = history[-3:] if history else []
            retrieved_docs = self.vector_store.search(query, k=3)
            t1 = time.perf_counter()
            search_time = t1 - t0
            if not retrieved_docs:
                log.warning("No relevant documents found for the query.")
                yield "I could not find any relevant information in the document to answer your question."
                return
            prompt = self._create_prompt(query, retrieved_docs, limited_history)
            t2 = time.perf_counter()
            prompt_time = t2 - t1
            log.info(f"Prompt created in {prompt_time:.2f} seconds. Search took {search_time:.2f} seconds.")
            if search_time > 5:
                log.warning(f"Semantic search took longer than 5 seconds: {search_time:.2f}s")
            if prompt_time > 5:
                log.warning(f"Prompt creation took longer than 5 seconds: {prompt_time:.2f}s")
            log.info("Streaming response from Ollama...")
            t3 = time.perf_counter()
            for token in self.ollama_service.stream_response(prompt):
                yield token
            t4 = time.perf_counter()
            llm_time = t4 - t3
            total_time = t4 - t0
            log.info(f"LLM streaming took {llm_time:.2f} seconds. Total response time: {total_time:.2f} seconds.")
            if llm_time > 5:
                log.warning(f"LLM response took longer than 5 seconds: {llm_time:.2f}s")
            if total_time > 5:
                log.warning(f"Total RAG response time exceeded 5 seconds: {total_time:.2f}s")
        except Exception as e:
            log.error(f"RAGService error: {e}")
            yield "An error occurred while processing your request."
