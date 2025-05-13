import os
from pathlib import Path
from dotenv import load_dotenv

# Pinecone Configuration
PINECONE_INDEX_NAME = "rag-regtech-data" # Your existing index name
PINECONE_NAMESPACE = "ns3-rag-regtech" # Use a distinct namespace for this RAG setup
PINECONE_DIMENSION = 768 # Dimension for Google's embedding-001 model
PINECONE_METRIC = "cosine"
PINECONE_CLOUD = "aws" # Or your specific cloud
PINECONE_REGION = "us-east-1" # Or your specific region
PINECONE_RERANK_MODEL = "bge-reranker-v2-m3" # Rerank model bge-reranker-v2-m3, cohere-rerank-3.5

# Google AI Configuration
GOOGLE_EMBEDDING_MODEL = "models/text-embedding-004"
# GOOGLE_LLM_MODEL = "gemini-1.5-pro-latest" # Changed from 2.5 as 1.5 is the current advanced model
GOOGLE_LLM_MODEL = "gemini-2.5-flash-preview-04-17"
TEMPRATURE       = 0.3

# Data Configuration
# !! IMPORTANT: Update this path to your PDF directory !!
PDF_DIRECTORY = Path(Path.cwd(), "pdf_files")

# LangChain Configuration
CHUNK_SIZE     = 300 # Text chunk size for splitting documents
CHUNK_OVERLAP  = 50  # Overlap between chunks
TOP_K_RESULTS  = 10  # Number of relevant documents to retrieve, initial vector search (wide net)
TOP_K_RERANKED = 3


# Load API keys from .env file
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Checks that the keys were successfully loaded.
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY not found in environment variables.")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables.")

# For PostgreSQL Ingestion defaults (can be overridden in UI)
PG_DEFAULT_BATCH_SIZE = 100