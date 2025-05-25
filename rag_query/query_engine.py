# rag_query/query_engine.py

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import Document  # Needed for Document type hint

# Import services
from services.initializer import initialize_llm, initialize_retriever, \
    initialize_pinecone_client  # Need client for reranking
from config import *  # Needs TOP_K_RESULTS, PINECONE_RERANK_MODEL, TOP_K_RERANKED, etc.

from services.time_series_handler import is_aiops_time_series_query, handle_time_series_query


def rerank_with_pinecone(query: str, docs: list[Document], top_n: int = 3) -> list[Document]:
    """Reranks retrieved docs using Pinecone’s configured rerank model."""
    if not docs:
        return []  # Return empty list if no docs were passed

    try:
        pc = initialize_pinecone_client()
        if pc is None:
            print("⚠️ Reranking skipped: Could not initialize Pinecone client.")
            return docs

        if not PINECONE_RERANK_MODEL:
            print("⚠️ Reranking skipped: PINECONE_RERANK_MODEL not configured.")
            return docs

        doc_texts = [doc.page_content for doc in docs]
        # print(f"Reranking {len(doc_texts)} documents with query: {query[:50]}...")
        response = pc.inference.rerank(
            model=PINECONE_RERANK_MODEL,
            query=query,
            documents=doc_texts,
            top_n=top_n,
            return_documents=True
        )

        reranked_docs = [docs[r.index] for r in
                         response.results]  # Adjusted based on typical Pinecone rerank client v3+

        print(f"✅ Reranking successful. Returned top {len(reranked_docs)} documents.")
        return reranked_docs
    except Exception as e:
        print(f"❌ Error during reranking: {e}")
        print("⚠️ Falling back to original retrieved documents.")
        return docs


def prompt_creator():
    template = """
    You are an assistant knowledgeable about the provided context.
    Answer the user's question using ONLY the following context. If the answer is not found in the context, state that clearly.
    Do not make up information not present in the context.
    If the context is time-series data, summarize the key findings relevant to the question.
    If the context indicates an error in retrieving data, explain that to the user.

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
    Answers a question based on ingested data.
    Prioritizes AIOps time-series queries if detected (querying InfluxDB).
    Otherwise, uses content indexed in Pinecone (PDF, URL, DBs, etc.).
    Returns the retrieved context and the generated answer.
    """
    if not question:
        return "Please enter a question.", "Please enter a question."

    context_text = ""
    answer = ""  # Default answer if error occurs early

    # Initialize LLM once
    llm = initialize_llm()
    if llm is None:
        # This is a critical failure, return immediately
        return "❌ LLM not initialized. Cannot generate answer.", "❌ LLM not initialized. Cannot generate answer."

    try:
        # --- Step 1: Check if it's an AIOps Time-Series Query ---
        print(f"Checking if '{question[:50]}...' is an AIOps time-series query.")
        if is_aiops_time_series_query(question):
            print(f"✅ Query identified as AIOps time-series. Handling with InfluxDB.")

            # formatted_ts_data will contain the data, a "no data" message, or an error message.
            # data_retrieved_successfully is True if query executed (even if no data), False on fundamental error.
            formatted_ts_data, data_retrieved_successfully = handle_time_series_query(question)
            context_text = formatted_ts_data  # This becomes the context for the LLM

            if not data_retrieved_successfully:
                # If handle_time_series_query indicated a fundamental failure (e.g., can't connect, bad query build)
                # The formatted_ts_data likely already contains an error message.
                print(f"⚠️ AIOps query handling reported an issue. Context passed to LLM: {context_text}")
                # The LLM will attempt to formulate an answer based on this error context.
            elif not context_text or "no time-series data was retrieved" in context_text.lower() or "no relevant time-series data found" in context_text.lower():
                print(f"⚠️ AIOps query returned no data or a 'no data' message. Context passed to LLM: {context_text}")
                # The LLM will be informed that no specific data was found.
            else:
                print("✅ AIOps data retrieved successfully.")

            # Proceed to LLM with AIOps context (or error/no-data message as context)
            prompt = prompt_creator()
            rag_chain = prompt | llm | StrOutputParser()
            print("Invoking RAG chain with AIOps context...")
            answer = rag_chain.invoke({"context": context_text, "question": question})
            print("✅ Generated answer based on AIOps context.")
            return context_text, answer

        else:
            print(f"ℹ️ Query not identified as AIOps. Proceeding with Pinecone RAG.")
            # --- Step 2: Standard RAG from Pinecone (if not AIOps) ---
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
            if PINECONE_RERANK_MODEL and TOP_K_RERANKED > 0:
                reranked_docs = rerank_with_pinecone(question, initial_docs, top_n=TOP_K_RERANKED)
                # Use the reranked docs for context, fallback to initial if reranking failed or returned empty
                context_docs = reranked_docs if reranked_docs else initial_docs
            else:
                context_docs = initial_docs
                print(
                    f"⚠️ Reranking is not configured or TOP_K_RERANKED is 0. Using initial {len(context_docs)} documents.")

            if not context_docs:
                print(f"⚠️ Retrieval resulted in no docs after potential reranking.")
                return "No relevant context found in the indexed documents.", "I could not find information related to your question in the uploaded/ingested data."

            context_text = format_docs(context_docs)
            prompt = prompt_creator()
            rag_chain = prompt | llm | StrOutputParser()
            print("Invoking RAG chain with Pinecone context...")
            answer = rag_chain.invoke({"context": context_text, "question": question})
            print("✅ Generated answer based on Pinecone context.")
            return context_text, answer

    except Exception as e:
        error_message = f"❌ Error generating answer: {e}"
        print(error_message)
        # Return the partially formed context_text (if any) and the error
        # Ensure answer is set to the error message if it wasn't already generated.
        return context_text if context_text else "Error occurred before context retrieval.", error_message