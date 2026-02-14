"""Application-level service container to avoid accidental global state."""

from dataclasses import dataclass

from psk_bot.core.conversation import ConversationStore
from psk_bot.services.ollama import OllamaService
from psk_bot.services.rag import RAGService
from psk_bot.services.vector_store import VectorStoreService
from psk_bot.services.web_search import WebSearchService
from psk_bot.settings import AppSettings, settings


@dataclass
class ServiceContainer:
    settings: AppSettings
    vector_store: VectorStoreService
    llm: OllamaService
    web_search: WebSearchService
    rag_service: RAGService
    conversation_store: ConversationStore


def build_container(config: AppSettings = settings) -> ServiceContainer:
    """Wire up shared services so they are created only once."""
    vector_store = VectorStoreService(config=config)
    llm = OllamaService(config=config)
    web_search = WebSearchService(config=config)
    rag_service = RAGService(config=config, vector_store=vector_store, llm=llm, web_search=web_search)
    conversation_store = ConversationStore(config.max_conversation_history)
    return ServiceContainer(
        settings=config,
        vector_store=vector_store,
        llm=llm,
        web_search=web_search,
        rag_service=rag_service,
        conversation_store=conversation_store,
    )
