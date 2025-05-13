# services/initializer.py

from pinecone import Pinecone
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore # Needed for Retriever init

# import config.py
from config import *

def initialize_pinecone_client():
    """Initializes Pinecone client."""
    # print("Initializing Pinecone client...") # Avoid spamming logs
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        # print("✅ Pinecone client initialized.")
        return pc
    except Exception as e:
        print(f"❌ Failed to initialize Pinecone client: {e}")
        # sys.exit() # Exiting here might be too aggressive for a web app, better to handle None later
        return None

def initialize_llm():
    """Initializes and returns LLM."""
    # print(f"Initializing Google LLM ({GOOGLE_LLM_MODEL})...") # Avoid spamming logs
    try:
        llm = ChatGoogleGenerativeAI(model=GOOGLE_LLM_MODEL, google_api_key=GOOGLE_API_KEY, temperature=0.3)
        # print(f"✅ Google LLM ({GOOGLE_LLM_MODEL}) initialized.")
        return llm
    except Exception as e:
        print(f"❌ Failed to initialize LLM due to exception: {e}")
        return None

def initialize_embeddings():
    """Initializes and returns Embeddings model."""
    # print(f"Initializing Google Embeddings model ({GOOGLE_EMBEDDING_MODEL})...") # Avoid spamming logs
    try:
        embeddings = GoogleGenerativeAIEmbeddings(model=GOOGLE_EMBEDDING_MODEL, google_api_key=GOOGLE_API_KEY)
        # print(f"✅ Google Embeddings model ({GOOGLE_EMBEDDING_MODEL}) initialized.")
        return embeddings
    except Exception as e:
        print(f"❌ Failed to initialize Embeddings due to exception: {e}")
        return None # Return None on failure

def initialize_retriever():
    """Initializes and returns a Pinecone VectorStore retriever."""
    try:
        embeddings = initialize_embeddings()
        if embeddings is None:
             print("❌ Failed to initialize embeddings for retriever.")
             return None

        # Retriever through which we extract vector from index with similarity score
        # Assumes the index and namespace exist and have data
        vectorstore = PineconeVectorStore.from_existing_index(
            index_name=PINECONE_INDEX_NAME,
            embedding=embeddings,
            namespace=PINECONE_NAMESPACE,
        )
        retriever = vectorstore.as_retriever(search_kwargs={'k': TOP_K_RESULTS})
        print(f"✅ Retriever configured to fetch top {TOP_K_RESULTS} results from namespace '{PINECONE_NAMESPACE}'.")
        return retriever

    except Exception as e:
        print(f"❌ Failed to initialize Retriever due to exception: {e}")
        return None # Return None on failure

# Helper to clear namespace - centralizing this
def clear_pinecone_namespace():
    """Clears all data from the configured Pinecone index and namespace."""
    pc = initialize_pinecone_client()
    if pc:
        try:
            index = pc.Index(PINECONE_INDEX_NAME)
            index.delete(delete_all=True, namespace=PINECONE_NAMESPACE)
            print(f"✅ Cleared namespace '{PINECONE_NAMESPACE}' in index '{PINECONE_INDEX_NAME}'.")
            return f"✅ Cleared Pinecone namespace '{PINECONE_NAMESPACE}'."
        except Exception as e:
            print(f"❌ Failed to clear Pinecone namespace: {e}")
            return f"❌ Failed to clear Pinecone namespace: {e}"
    else:
         print("⚠️ Could not initialize Pinecone client to clear namespace.")
         return "⚠️ Could not initialize Pinecone client to clear namespace."