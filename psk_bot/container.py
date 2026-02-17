"""Application-level service container to avoid accidental global state."""

from dataclasses import dataclass
from typing import Optional

from psk_bot.core.conversation import ConversationStore
from psk_bot.services.ollama import OllamaService
from psk_bot.services.rag import RAGService
from psk_bot.services.tts import TTSService
from psk_bot.services.vector_store import VectorStoreService
from psk_bot.settings import AppSettings, settings


@dataclass
class ServiceContainer:
    settings: AppSettings
    vector_store: VectorStoreService
    llm: OllamaService
    rag_service: RAGService
    conversation_store: ConversationStore
    tts: Optional[TTSService]


def build_container(config: AppSettings = settings) -> ServiceContainer:
    """Wire up shared services so they are created only once."""
    vector_store = VectorStoreService(config=config)
    llm = OllamaService(config=config)
    rag_service = RAGService(config=config, vector_store=vector_store, llm=llm)
    conversation_store = ConversationStore(config.max_conversation_history)

    # TTS via ElevenLabs (optional — only active when API key is set)
    tts: Optional[TTSService] = None
    if config.tts_enabled and config.elevenlabs_api_key:
        tts = TTSService(
            api_key=config.elevenlabs_api_key,
            voice_id=config.elevenlabs_voice,
            model_id=config.elevenlabs_model,
        )

    return ServiceContainer(
        settings=config,
        vector_store=vector_store,
        llm=llm,
        rag_service=rag_service,
        conversation_store=conversation_store,
        tts=tts,
    )
