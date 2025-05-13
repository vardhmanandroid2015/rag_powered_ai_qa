# services/embedding_utils.py

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document # Already imported via ingestion/rag_query
from langchain_pinecone import PineconeVectorStore

# Import initializers from services
from .initializer import initialize_embeddings, clear_pinecone_namespace

# import config.py
from config import *

def get_text_splitter():
    """Initializes and returns a RecursiveCharacterTextSplitter."""
    return RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def embed_and_index_documents(documents: list[Document], clear_namespace: bool = True):
    """
    Embeds a list of LangChain Documents and uploads them to Pinecone.
    Optionally clears the namespace before indexing.
    """
    if not documents:
        return "❌ No documents provided for indexing."

    try:
        embeddings = initialize_embeddings()
        if embeddings is None:
             return "❌ Failed to initialize embeddings. Cannot index."

        # Clear the namespace if requested (default for single-shot ingestion)
        if clear_namespace:
             clear_status = clear_pinecone_namespace()
             if "❌" in clear_status:
                  # Decide if this is a fatal error or just a warning
                  # For now, treat as warning and continue with indexing
                  print(f"⚠️ Warning during namespace clearing: {clear_status}")
                  # return clear_status # Uncomment to fail on clear error


        # Use PineconeVectorStore's from_documents which handles chunking internally
        # based on the splitter it uses internally or if chunks are pre-split
        # Re-checking LangChain's PineconeVectorStore.from_documents - it takes `documents` (list of Document)
        # and splits them using its internal splitter if needed, or takes pre-split documents.
        # The original code split first, then passed chunks. Let's stick to that.
        # So this function should take *chunks*, not *documents* as input.

        # Let's rename this function and update its parameter name for clarity
        # The splitting logic will live in the ingestion modules.

        # --- Refactoring: Renaming and updating logic for pre-split chunks ---

        # This function should not clear the namespace if used for batching (e.g., Postgres)
        # The previous version of embed_and_index_chunks *did* clear the namespace.
        # This is suitable for PDF/URL/SQLite where we replace the entire index content.
        # For Postgres batching, we will use vectorstore.add_documents directly in the loop.
        # So, keep this function for the non-batched ingestions.

        print(f"Embedding and indexing {len(documents)} chunks...") # Assuming 'documents' is actually 'chunks'


        # This method creates a *new* vectorstore instance and upserts the data
        # Use add_documents on an initialized vectorstore for batching
        PineconeVectorStore.from_documents( # This call clears the namespace internally if it doesn't exist, or just upserts
            documents, # Assuming this input is actually pre-split chunks
            index_name=PINECONE_INDEX_NAME,
            embedding=embeddings,
            namespace=PINECONE_NAMESPACE
        )


        status_msg = f"✅ Successfully indexed {len(documents)} chunks into Pinecone namespace '{PINECONE_NAMESPACE}'."
        print(status_msg)
        return status_msg

    except Exception as e:
        error_msg = f"❌ Error during embedding or indexing: {e}"
        print(error_msg)
        return error_msg