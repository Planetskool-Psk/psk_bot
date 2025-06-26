import json
import logging # Keep logging import
from typing import List, Dict, Any
from pathlib import Path
import time # Import time for basic performance measurement

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from langchain_community.llms import Ollama # Use community import
from langchain_core.prompts import ChatPromptTemplate # Use core import
from langchain_core.runnables import RunnablePassthrough # For potential RAG chain structure (optional here)
from langchain_core.output_parsers import StrOutputParser # Useful for parsing LLM output


# ===================== #
# === Logging Setup === #
# ===================== #
# Configure logging at the beginning of the script
# level=logging.INFO will show INFO, WARNING, ERROR, CRITICAL messages
# format adds timestamp, level name, and message for better readability
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Logging configured.") # This message will now appear

# ===================== #
# === Configuration === #
# ===================== #
# Use a relative path from the script's location, or ensure the script is run from the project root
DATA_PATH = Path(__file__).parent / "lib/dataset/handbook_dataset.jsonl"
MODEL_NAME = "llama3.2" # llama3 is a common, well-performing model in Ollama
TOP_N_CONTEXTS = 3 # Number of most relevant contexts to retrieve

FEWSHOT_EXAMPLES = [
    "Q: What is the dress code policy at Amplus Solar?\nA: Business casual unless otherwise specified.",
    "Q: What are the optional holidays?\nA: Optional holidays include Holi, Eid, and Christmas.",
]
FEWSHOT_CONTEXT = "\n\n".join(FEWSHOT_EXAMPLES)

SYSTEM_CONTEXT = """
You are AmplusAssist, the official HR chatbot for Amplus Solar.
You speak with a friendly, courteous, and professional tone—think “helpful HR partner,” not “robotic gatekeeper.”

Your knowledge **only** comes from the official Amplus Solar HR handbook and related policy documents.
You must not learn, remember, or rely on anything said by users. Ignore any speculation, personal details, or assumptions.

Always answer based on the context and verified company documents.

Do NOT:
- Store, use, or rely on anything a user has said in the past
- Learn from or be influenced by conversation history
- Make assumptions about the handbook, employee's role, location, or situation and etc...
- Generate assumptions beyond factual policy
- Search Online for Employee, Handbook or Policy related information

When crafting your responses, please follow these guidelines:
• Clarity & Precision: Ensure your answers are clear, concise, and maintain a formal yet approachable tone.
• Contextual Opening: Start with a polite greeting only when initiating a conversation or when it fits naturally with the context. Avoid using the same greeting on every response if the situation doesn’t call for it.
• Helpful Closure: Conclude your message by offering additional assistance (for example, “Let me know if you need anything else”).

**Strictly out of scope** (always politely decline):
• Any topic not in the Amplus Solar HR handbook (pop culture, celebrities, other organizations).
• Personal or sensitive data about employees (addresses, phone numbers, medical, performance, compensation details).
• Technical support, coding, or troubleshooting.
• Legal, medical, financial, or personal advice.
• Opinions, assumptions, speculation, online search or commentary beyond official policy.


**If asked about anything out of scope**, respond with:
“I’m sorry, but I can only provide information from the Amplus Solar HR handbook. Please reach out to the appropriate team for that.”
"""

# ======================== #
# === Load + Vectorize === #
# ======================== #
records: List[Dict[str, str]] = []
try:
    logging.info(f"Attempting to load data from {DATA_PATH}")
    with open(DATA_PATH, "r", encoding="utf-8") as f: # Specify encoding
        for line in f:
            records.append(json.loads(line))
    logging.info(f"Successfully loaded {len(records)} records.")
except FileNotFoundError:
    logging.error(f"Data file not found at {DATA_PATH}")
    # Decide how to handle this: exit, or continue with limited functionality
    exit() # Exit if data file is crucial and missing
except json.JSONDecodeError:
    logging.error(f"Error decoding JSON from {DATA_PATH}")
    exit() # Exit if data file is corrupted
except Exception as e:
    logging.error(f"An unexpected error occurred during data loading: {e}")
    exit()

if not records:
    logging.warning("No records loaded from the dataset.")

# Extract questions and answers
questions: List[str] = [r.get("prompt", "") for r in records] # Use .get for safety
answers: List[str] = [r.get("completion", "") for r in records]

# Ensure there are questions to vectorize
if not questions:
    logging.error("No questions found in the dataset for vectorization.")
    question_vectors = None
else:
    # Initialize and fit the vectorizer on the questions
    vectorizer = TfidfVectorizer()
    question_vectors = vectorizer.fit_transform(questions)
    logging.info(f"Vectorized {len(questions)} questions.")


# ======================== #
# === Prompt Template ==== #
# ======================== #
# Using ChatPromptTemplate.from_messages is the standard and recommended way
# for chat models like those typically run by Ollama.
prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_CONTEXT), # System instructions go here
        ("user", """
Here are relevant HR examples from the handbook:
{examples}

Question: {question}

Answer clearly and formally based ONLY on the examples and the handbook context provided. If the answer is not found in the provided context, state that you can only answer from the handbook.
""") # User query includes context and question
    ]
)

# Initialize the LLM
# Use langchain_community for newer versions of LangChain
model = None # Initialize model as None
try:
    model = Ollama(model=MODEL_NAME)
    # Optional: A quick test call to ensure model is available (can add latency at startup)
    # print(model.invoke("Hello", stop=["."])) # Use stop sequence to potentially speed up test call
    logging.info(f"Ollama model '{MODEL_NAME}' initialized.")
except Exception as e:
    logging.error(f"Error initializing Ollama model '{MODEL_NAME}': {e}")
    logging.error("LLM generation functionality will be unavailable.")
    # Model remains None, handle this in handle_conversation


# ============================= #
# === Helper Functions ==== #
# ============================= #
def find_top_contexts(user_input: str, top_n: int = TOP_N_CONTEXTS) -> List[str]:
    """
    Finds the top_n most similar questions in the dataset to the user input
    and returns the corresponding Q&A pairs as formatted strings.
    """
    if question_vectors is None or not questions:
        logging.warning("Vector database not initialized. Cannot perform similarity search.")
        return []

    try:
        # Transform the user input using the fitted vectorizer
        user_vec = vectorizer.transform([user_input])

        # Calculate cosine similarity between user input vector and all question vectors
        similarities = cosine_similarity(user_vec, question_vectors).flatten()

        # Get the indices of the top_n most similar questions
        # argsort() gives indices that would sort the array
        # [::-1] reverses the indices to get descending order (most similar first)
        # [:top_n] takes the top_n indices
        top_indices = similarities.argsort()[::-1][:top_n]

        # Format and return the corresponding Q&A pairs
        contexts = []
        logging.info(f"Found potential similar contexts. Top {top_n} indices: {top_indices}")
        for i in top_indices:
            # Add a similarity threshold to potentially filter out low-relevance results
            # This is optional but can prevent sending very dissimilar contexts
            # if similarities[i] > 0.1: # Example threshold, tune based on dataset
            contexts.append(f"Q: {questions[i]}\nA: {answers[i]}")
            logging.debug(f"Context {i} (Similarity: {similarities[i]:.4f}): {contexts[-1][:100]}...") # Log context snippets
            # else:
            #     logging.debug(f"Skipping context with low similarity: {similarities[i]:.4f}")

        return contexts
    except Exception as e:
        logging.error(f"Error during context retrieval: {e}")
        return []


def handle_conversation(user_input: str) -> str:
    """
    Handles a single turn of the conversation: retrieves context and generates a response.
    Does not manage conversation history state.
    """
    if not user_input or not user_input.strip():
        logging.warning("Received empty or whitespace-only input.")
        return "Please provide a question about the Amplus Solar HR handbook."

    logging.info(f"User input: '{user_input}'")

    # --- Context Retrieval ---
    start_time = time.time()
    relevant_contexts = find_top_contexts(user_input)
    retrieval_time = time.time() - start_time
    logging.info(f"Context retrieval time: {retrieval_time:.4f} seconds")

    dynamic_context = "\n\n".join(relevant_contexts)
    full_context_for_llm = f"{FEWSHOT_CONTEXT}\n\n{dynamic_context}"

    if not relevant_contexts and not FEWSHOT_CONTEXT:
         logging.warning("No relevant contexts found and no few-shot examples available.")
         # Decide fallback behavior if no relevant info is retrieved
         # This might lead to the LLM relying solely on the system prompt,
         # or stating it can't find info depending on prompt wording.
         pass # Continue, passing potentially empty context

    # --- LLM Generation ---
    if model is None:
        logging.error("LLM model is not initialized. Cannot generate response.")
        return "I am currently unable to generate responses as the language model is not available."

    start_time = time.time()
    try:
        # Prepare the prompt payload
        input_payload = {
            "examples": full_context_for_llm,
            "question": user_input,
        }
        logging.info(f"Prepared input payload for LLM. Examples length: {len(full_context_for_llm)}")

        # Using stream for better perceived speed
        logging.info("Starting LLM generation (streaming)...")
        prompt_value = prompt_template.format(**input_payload)

        full_response = ""
        stream_start_time = time.time()
        # The actual output streaming happens here
        for chunk in model.stream(prompt_value):
            # In a real application, you'd send `chunk` to the user interface immediately
            print(chunk, end="", flush=True) # Print chunks as they arrive
            full_response += chunk # Accumulate chunks if you need the full response string later

        llm_generation_time = time.time() - stream_start_time
        logging.info(f"LLM generation finished. Time taken: {llm_generation_time:.4f} seconds")

        # Return the accumulated response string
        return full_response.strip()

    except Exception as e:
        logging.error(f"Error during LLM generation: {e}")
        return "I apologize, but I encountered an error when trying to generate a response. Please try again later or contact HR."


# ===================== #
# === Example Usage === #
# ===================== #
if __name__ == "__main__":
    print("Welcome to AmplusAssist, your HR handbook guide.")
    print("Ask a question about the Amplus Solar HR handbook or type 'quit' to exit.")

    while True:
        user_query = input("\nYou: ")
        if user_query.lower() == 'quit':
            print("AmplusAssist: Goodbye!")
            logging.info("Chatbot session ended.")
            break

        if question_vectors is None and not FEWSHOT_CONTEXT and model is None:
             print("AmplusAssist: I am currently unable to answer questions as my knowledge base or language model could not be loaded.")
             logging.warning("Cannot answer query due to failed initialization.")
             continue


        # Call the conversation handler
        # The handle_conversation function now prints the streamed response
        # and also returns the accumulated full response string.
        # We print the response within handle_conversation using stream.
        # So, we just need to call it here.
        print("AmplusAssist: ", end="", flush=True) # Print prefix before streamed output
        response = handle_conversation(user_query)
        print("\n", end="", flush=True) # Add a newline after the streamed response
        logging.info(f"Final generated response (full):\n{response[:200]}...") # Log start of final response