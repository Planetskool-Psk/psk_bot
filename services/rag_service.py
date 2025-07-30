# /rag-chatbot-ollama/services/rag_service.py

from .vector_store_service import VectorStoreService
from .ollama_service import OllamaService
from utils.logger import log
import config
import re
from typing import List, Dict, Generator, Any

class RAGService:
    def __init__(self) -> None:
        self.vector_store = VectorStoreService()
        self.ollama_service = OllamaService()
        self.is_ready = self.vector_store.load_store()
        if not self.is_ready:
            log.warning("RAG service is not ready. Please run the ingestion script.")

    def _preprocess_query(self, query: str) -> str:
        """Preprocess query to improve retrieval quality."""
        # Remove common stop words that don't help with retrieval
        stop_words = {'what', 'how', 'when', 'where', 'why', 'who', 'is', 'are', 'can', 'could', 'would', 'should'}
        words = query.lower().split()
        important_words = [word for word in words if word not in stop_words and len(word) > 2]
        
        # If we filtered too much, use original query
        if len(important_words) < 2:
            return query
        
        # Create enhanced query with key terms
        enhanced_query = ' '.join(important_words)
        log.info(f"Enhanced query for retrieval: '{enhanced_query}'")
        return enhanced_query

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        """Formats conversation history for the prompt with better context."""
        if not history:
            return "No previous conversation."
        
        # Take last 2 conversations for better context while keeping it optimized
        recent_history = history[-2:] if len(history) > 1 else history
        formatted = []
        for turn in recent_history:
            formatted.append(f"Human: {turn['user']}\nAssistant: {turn['bot']}")
        return "\n".join(formatted)

    def _select_best_context(self, context_docs: List[Dict[str, Any]], query: str) -> str:
        """Select and combine the most relevant context from retrieved documents."""
        if not context_docs:
            return ""
        
        # Get top 2 documents for better context while maintaining speed
        top_docs = context_docs[:2]
        
        # Combine contexts with relevance scoring
        combined_context = []
        for i, doc in enumerate(top_docs):
            content = doc["content"].strip()
            score = doc.get("score", 0)
            
            # Add document with relevance indicator
            context_header = f"[Document {i+1} - Relevance: {score:.3f}]"
            combined_context.append(f"{context_header}\n{content}")
        
        final_context = "\n\n".join(combined_context)
        
        # Limit context length for faster processing
        if len(final_context) > 1500:  # Increased from previous limit for better answers
            final_context = final_context[:1500] + "..."
            
        return final_context

    def _create_enhanced_prompt(self, query: str, context_docs: List[Dict[str, Any]], history: List[Dict[str, str]]) -> str:
        """Creates an enhanced prompt for better answer quality."""
        context = self._select_best_context(context_docs, query)
        formatted_history = self._format_history(history)
        
        # Enhanced prompt template for better answers
        enhanced_template = """You are Gia (Gentari Intelligence Assistant), a helpful and knowledgeable HR assistant. 

CONTEXT INFORMATION:
{context}

CONVERSATION HISTORY:
{history}

CURRENT QUESTION: {question}

INSTRUCTIONS:
- Provide a clear, comprehensive answer based ONLY on the context information above
- If the context contains relevant information, explain it thoroughly and helpfully
- Structure your response with clear points when appropriate
- If the context doesn't contain enough information to answer fully, say "Based on the available information, I can tell you [what you know], but for complete details, please contact the HR team."
- Be conversational and helpful while staying accurate to the source material
- Do not mention document numbers, relevance scores, or technical details
- Focus on being helpful and informative

ANSWER:"""

        return enhanced_template.format(
            context=context, 
            history=formatted_history, 
            question=query
        )

    def get_response_stream(self, query: str, history: List[Dict[str, str]]) -> Generator[str, None, None]:
        """Gets a streamed response from the enhanced RAG pipeline with better retrieval and answer quality."""
        import time
        if not self.is_ready:
            yield "Error: The document knowledge base is not loaded. Please run the ingestion script."
            return
        
        try:
            t0 = time.perf_counter()
            
            # Preprocess query for better retrieval
            enhanced_query = self._preprocess_query(query)
            
            log.info(f"Performing enhanced semantic search for: '{query}' -> '{enhanced_query}'")
            
            # Search with top 2 documents for better context
            retrieved_docs = self.vector_store.search(enhanced_query, k=2)
            
            # Also try original query if enhanced query doesn't return good results
            if not retrieved_docs or (retrieved_docs and retrieved_docs[0].get("score", 0) > 0.7):
                log.info("Trying original query for better results...")
                original_results = self.vector_store.search(query, k=2)
                if original_results and (not retrieved_docs or original_results[0].get("score", 0) < retrieved_docs[0].get("score", 1)):
                    retrieved_docs = original_results
            
            t1 = time.perf_counter()
            search_time = t1 - t0
            
            if not retrieved_docs:
                log.warning("No relevant documents found for the query.")
                yield "I could not find any relevant information in the document to answer your question. Please contact the HR team for assistance."
                return
            
            # Log retrieval quality
            best_score = retrieved_docs[0].get("score", 0)
            log.info(f"Retrieved {len(retrieved_docs)} documents. Best relevance score: {best_score:.3f}")
            
            # Create enhanced prompt with better context
            prompt = self._create_enhanced_prompt(query, retrieved_docs, history)
            
            t2 = time.perf_counter()
            prompt_time = t2 - t1
            
            log.info(f"Enhanced prompt created in {prompt_time:.2f}s. Search took {search_time:.2f}s.")
            
            # Stream response with better context
            log.info("Streaming enhanced response from Ollama...")
            t3 = time.perf_counter()
            
            response_chunks = []
            for token in self.ollama_service.stream_response(prompt):
                response_chunks.append(token)
                yield token
            
            t4 = time.perf_counter()
            llm_time = t4 - t3
            total_time = t4 - t0
            
            # Log performance metrics
            full_response = ''.join(response_chunks)
            response_length = len(full_response)
            log.info(f"Enhanced RAG completed: {response_length} chars in {total_time:.2f}s (Search: {search_time:.2f}s, LLM: {llm_time:.2f}s)")
            
            # Quality assessment
            if "contact the HR team" in full_response.lower() and best_score < 0.5:
                log.warning(f"Low quality response detected. Best doc score: {best_score:.3f}")
            
        except Exception as e:
            log.error(f"Enhanced RAGService error: {e}")
            yield "I apologize, but I encountered an error while processing your request. Please try rephrasing your question or contact the HR team for assistance."
