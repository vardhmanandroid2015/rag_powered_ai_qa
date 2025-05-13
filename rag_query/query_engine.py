# rag_query/query_engine.py

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import Document # Needed for Document type hint

# Import services
from services.initializer import initialize_llm, initialize_retriever, initialize_pinecone_client # Need client for reranking

# import config.py
from config import * # Needs TOP_K_RESULTS, PINECONE_RERANK_MODEL, TOP_K_RERANKED


def rerank_with_pinecone(query: str, docs: list[Document], top_n: int = 3) -> list[Document]:
    """Reranks retrieved docs using Pinecone’s Cohere rerank model."""
    if not docs:
         return [] # Return empty list if no docs were passed

    try:
        # Initialize client inside function scope as needed
        pc = initialize_pinecone_client()
        if pc is None:
             print("⚠️ Reranking skipped: Could not initialize Pinecone client.")
             return docs # fallback to original if client fails

        # Ensure the rerank model is configured
        if not PINECONE_RERANK_MODEL:
             print("⚠️ Reranking skipped: PINECONE_RERANK_MODEL not configured.")
             return docs # fallback to original

        doc_texts = [doc.page_content for doc in docs]
        # print(f"Reranking {len(doc_texts)} documents with query: {query[:50]}...") # Verbose logging
        response = pc.inference.rerank(
            model=PINECONE_RERANK_MODEL,
            query=query,
            documents=doc_texts,
            top_n=top_n,
            return_documents=True # Request the original documents back in the response
        )
        # Reconstruct LangChain Document objects from the reranked results
        # The response.data contains RerankedDocument objects with original document content and score
        reranked = []
        # Pinecone rerank returns RerankedDocument with 'document' field which is the original text
        # Need to match this back to the original LangChain Document object to preserve metadata
        # A more robust way is to pass Document objects to rerank API if it supports it (check Pinecone docs)
        # Or, if the API only takes text, match based on content (risky with duplicates) or pass IDs if possible.
        # The provided example uses indices from the response. Let's stick to that but verify docs list is indexed correctly.
        # The response 'data' field is a list of RerankedDocument objects, each with an 'index' field
        # corresponding to the index in the input 'documents' list (doc_texts).
        reranked_docs = [docs[r.index] for r in response.data]

        print(f"✅ Reranking successful. Returned top {len(reranked_docs)} documents.")
        return reranked_docs
    except Exception as e:
        print(f"❌ Error during reranking: {e}")
        print("⚠️ Falling back to original retrieved documents.")
        return docs  # fallback to original if reranking fails


def prompt_creator():
    # Define the prompt template - Defines how the AI should answer questions (with instructions and placeholders).
    # Adjusted slightly to be less specific than "Distributed System Design" as data source can vary
    template = """
    You are an assistant knowledgeable about the provided context.
    Answer the user's question using ONLY the following context. If the answer is not found in the context, state that clearly.
    Do not make up information not present in the context.

    Context:
    {context}

    Question:
    {question}

    Answer:
    """
    prompt = ChatPromptTemplate.from_template(template)
    return prompt

def format_docs(docs: list[Document]) -> str:
    """Formats document chunks into a single string."""
    return "\n\n".join(doc.page_content for doc in docs)


def answer_question_about_ingested_data(question: str) -> tuple[str, str]:
    """
    Answers a question based on the content indexed in Pinecone
    (which could be from PDF, URL, SQLite, or PostgreSQL).
    Returns the retrieved context and the generated answer.
    """
    if not question:
        return "Please enter a question.", "Please enter a question."

    try:
        # Retrieve relevant documents from Pinecone
        retriever = initialize_retriever()
        if retriever is None:
            return "❌ Retriever not initialized. Cannot answer question.", "❌ Retriever not initialized. Cannot answer question."

        print(f"Retrieving initial documents for question: {question[:50]}...")
        initial_docs = retriever.invoke(question)
        print(f"✅ Retrieved {len(initial_docs)} initial documents.")


        if not initial_docs:
             print(f"⚠️ No relevant context found for question: {question}")
             return "No relevant context found in the indexed documents.", "I could not find information related to your question in the uploaded/ingested data."

        # Rerank the retrieved docs if reranking is configured
        # Ensure PINECONE_RERANK_MODEL and TOP_K_RERANKED are defined in config.py
        if 'PINECONE_RERANK_MODEL' in globals() and PINECONE_RERANK_MODEL and 'TOP_K_RERANKED' in globals() and TOP_K_RERANKED > 0:
             reranked_docs = rerank_with_pinecone(question, initial_docs, top_n=TOP_K_RERANKED)
             # Use the reranked docs for context, fallback to initial if reranking failed or returned empty
             context_docs = reranked_docs if reranked_docs else initial_docs
             # print(f"✅ Retrieved & Reranked {len(context_docs)} document chunks.") # Logged inside rerank_with_pinecone
        else:
             context_docs = initial_docs
             print(f"⚠️ Reranking is not configured (PINECONE_RERANK_MODEL/TOP_K_RERANKED missing or <= 0). Using initial {len(context_docs)} documents.")


        if not context_docs:
             print(f"⚠️ Retrieval resulted in no docs.")
             return "No relevant context found in the indexed documents.", "I could not find information related to your question in the uploaded/ingested data."


        context_text = format_docs(context_docs)


        # Get the prompt template
        prompt = prompt_creator()

        # Get the LLM
        llm = initialize_llm()
        if llm is None:
            return "❌ LLM not initialized. Cannot generate answer.", "❌ LLM not initialized. Cannot generate answer."

        # Create the RAG chain (Prompt + LLM + OutputParser)
        rag_chain = prompt | llm | StrOutputParser()

        print("Invoking RAG chain...")
        # Invoke the chain
        answer = rag_chain.invoke({"context": context_text, "question": question}) # Pass inputs as dict
        print("✅ Generated answer.")

        return context_text, answer

    except Exception as e:
        error_message = f"❌ Error generating answer: {e}"
        print(error_message)
        return "", error_message