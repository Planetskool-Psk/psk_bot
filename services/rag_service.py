# /rag-chatbot-ollama/services/rag_service.py

from .vector_store_service import VectorStoreService
from .ollama_service import OllamaService
from utils.logger import log
import config


class RAGService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.ollama_service = OllamaService()
        self.is_ready = self.vector_store.load_store()
        if not self.is_ready:
            log.warning("RAG service is not ready. Please run the ingestion script.")

    def _format_history(self, history):
        """Formats conversation history for the prompt."""
        if not history:
            return "No previous conversation."

        formatted = []
        for turn in history:
            formatted.append(f"User: {turn['user']}\nAssistant: {turn['bot']}")
        return "\n\n".join(formatted)

    def _create_prompt(self, query, context_docs, history):
        """Creates the final prompt for the LLM."""
        context = "\n---\n".join([doc["content"] for doc in context_docs])
        formatted_history = self._format_history(history)

        return config.PROMPT_TEMPLATE.format(
            context=context, history=formatted_history, question=query
        )

    def get_response_stream(self, query, history):
        """Gets a streamed response from the RAG pipeline."""
        if not self.is_ready:
            yield "Error: The document knowledge base is not loaded. Please run the ingestion script."
            return

        log.info(f"Performing semantic search for query: '{query}'")
        retrieved_docs = self.vector_store.search(query)

        if not retrieved_docs:
            log.warning("No relevant documents found for the query.")
            yield "I could not find any relevant information in the document to answer your question."
            return

        prompt = self._create_prompt(query, retrieved_docs, history)

        log.info("Streaming response from Ollama...")
        yield from self.ollama_service.stream_response(prompt)
