import requests
import html # To decode HTML entities in API response
from langchain.schema import Document
from langchain_pinecone import PineconeVectorStore

# Import services
from services.initializer import initialize_embeddings, initialize_pinecone_client, clear_pinecone_namespace
from services.embedding_utils import get_text_splitter
from services.summary_questions import get_full_text_from_docs, generate_document_summary, generate_suggested_questions_list

# import config.py
from config import * # Needs CHUNK_SIZE, CHUNK_OVERLAP, PINECONE_*, OPENTDB_API_BASE_URL, API_DEFAULT_*, PG_DEFAULT_BATCH_SIZE (reused for batching)


def ingest_api_data_to_pinecone(num_questions=API_DEFAULT_NUM_QUESTIONS, category_id=API_DEFAULT_CATEGORY_ID, batch_size=PG_DEFAULT_BATCH_SIZE):
    """
    Fetches data from the OpenTDB API, embeds it, and adds it to Pinecone.
    Assumes API response contains question, correct_answer, etc.
    Clears the Pinecone namespace ONCE before starting ingestion.
    """
    # Convert inputs to appropriate types
    try:
        num_questions = int(num_questions)
        if category_id is not None and category_id != "":
            category_id = int(category_id)
        else:
            category_id = None # Ensure it's None if empty string
        batch_size = int(batch_size)

    except (ValueError, TypeError):
        return "❌ Invalid input for number of questions, category ID, or batch size.", "", ""

    if num_questions <= 0 or batch_size <= 0:
        return "❌ Number of questions and batch size must be greater than 0.", "", ""

    print(f"Attempting to fetch {num_questions} questions from OpenTDB API...")

    try:
        # Build API request parameters
        params = {
            "amount": num_questions,
            "type": "multiple", # Or "boolean" - multiple often gives richer answers
        }
        if category_id is not None:
            params["category"] = category_id
            print(f"Filtering by category ID: {category_id}")
        # You could add difficulty filter here too if implemented in UI

        # Make the API request
        response = requests.get(OPENTDB_API_BASE_URL, params=params)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        data = response.json()

        # Check OpenTDB specific response code
        # 0: Success, 1: No Results, 2: Invalid Parameter, 3: Token Not Found, 4: Token Empty
        if data["response_code"] != 0:
            error_messages = {
                1: "API returned 'No Results' for the specified criteria.",
                2: "API returned 'Invalid Parameter'. Check number of questions or category ID.",
                3: "API returned 'Token Not Found' (not expected for basic calls).",
                4: "API returned 'Token Empty' (not expected for basic calls).",
                # Add others if needed
            }
            error_msg = error_messages.get(data["response_code"], f"API returned error code: {data['response_code']}")
            print(f"❌ API Error: {error_msg}")
            return f"❌ API Error: {error_msg}", "", ""

        api_results = data.get("results", [])
        if not api_results:
            return "⚠️ API call was successful, but returned no results.", "", ""

        print(f"✅ Successfully fetched {len(api_results)} results from API.")

        # Initialize Embeddings and Pinecone Vector Store outside the loop
        embeddings = initialize_embeddings()
        if embeddings is None:
            return "❌ Failed to initialize embeddings. Cannot index.", "", ""

        # Clear the namespace ONCE before starting ingestion
        # NOTE: This clears the *entire* namespace defined in config.py.
        # Be mindful if you intend to keep data from other sources.
        clear_status = clear_pinecone_namespace()
        if "❌" in clear_status:
             return clear_status, "", ""

        # Initialize Pinecone VectorStore for incremental additions
        vectorstore = PineconeVectorStore(
            index_name=PINECONE_INDEX_NAME,
            embedding=embeddings,
            namespace=PINECONE_NAMESPACE
        )
        print("✅ Pinecone VectorStore initialized for incremental upserts.")

        # Initialize Text Splitter
        text_splitter = get_text_splitter()
        print("✅ Text Splitter initialized.")

        docs_to_process = []
        for item in api_results:
            try:
                # Decode HTML entities
                question = html.unescape(item.get("question", ""))
                correct_answer = html.unescape(item.get("correct_answer", ""))
                category = item.get("category", "General")
                difficulty = item.get("difficulty", "unknown")
                question_type = item.get("type", "multiple")

                if not question or not correct_answer:
                     print(f"⚠️ Skipping API item: Missing question or answer.")
                     continue # Skip incomplete items

                # Combine question and answer for page_content
                content = f"Question: {question}\nAnswer: {correct_answer}"

                # Add metadata
                metadata = {
                    "source": "api",
                    "api_source": "OpenTDB",
                    "category": category,
                    "difficulty": difficulty,
                    "type": question_type,
                    # Could add incorrect_answers to metadata if needed, but might make it too large
                    # "incorrect_answers": item.get("incorrect_answers", []) # This can be a list
                }

                docs_to_process.append(Document(page_content=content, metadata=metadata))

            except Exception as e:
                print(f"❌ Error processing API item: {e}")
                # Log error and continue with next item

        if not docs_to_process:
             return "⚠️ No valid documents could be created from the API response.", "", ""


        # --- Process documents in batches and upsert ---
        rows_processed = 0
        chunks_indexed = 0
        all_docs_for_summary = [] # Collect first batch docs for summary/questions
        is_first_batch = True

        print(f"Starting batch ingestion into Pinecone (batch size: {batch_size})...")

        # Manual batching loop
        for i in range(0, len(docs_to_process), batch_size):
            batch_docs = docs_to_process[i : i + batch_size]

            try:
                batch_chunks = text_splitter.split_documents(batch_docs)

                if is_first_batch:
                     # Capture a copy of the first batch of Langchain Documents
                     all_docs_for_summary = batch_docs[:]
                     is_first_batch = False

                if batch_chunks:
                    vectorstore.add_documents(batch_chunks)
                    rows_processed += len(batch_docs)
                    chunks_indexed += len(batch_chunks)
                    print(f"✅ Processed {rows_processed} records, Indexed {chunks_indexed} chunks so far...")
                else:
                    rows_processed += len(batch_docs) # Still count the source documents processed
                    print(f"⚠️ Processed {rows_processed} records, but batch generated no chunks.")

            except Exception as e:
                print(f"❌ Error processing batch starting at index {i}: {e}")
                # Continue processing remaining batches


        # --- Final Steps After Batching ---
        final_status = f"✅ Successfully ingested {rows_processed} records ({chunks_indexed} chunks) from OpenTDB API into Pinecone namespace '{PINECONE_NAMESPACE}' using batch size {batch_size}."
        print(final_status)

        # Generate summary and questions from the first batch's documents
        summary_text = "Summary/Suggestions generated from a sample (first batch) of the API data."
        suggested_questions_text = "Suggestions generated from a sample (first batch) of the API data."
        if all_docs_for_summary:
            sample_full_text = get_full_text_from_docs(all_docs_for_summary)
            if sample_full_text:
                summary_text = generate_document_summary(sample_full_text)
                suggested_questions_text = generate_suggested_questions_list(sample_full_text)
            else:
                 summary_text = "❌ Could not extract text from sample for summary/questions."
                 suggested_questions_text = "❌ Could not extract text from sample for summary/questions."
        else:
             summary_text = "⚠️ No data processed from API. Summary/Suggestions not generated."
             suggested_questions_text = "⚠️ No data processed from API. Summary/Suggestions not generated."


        # Append notes about summary/questions being from sample if needed
        if rows_processed > batch_size: # If there were more than one batch or a partial second batch
             summary_text += "\n\n*Note: Generated from a sample (first batch) of data.*"
             suggested_questions_text += "\n\n*Note: Generated from a sample (first batch) of data.*"


        return final_status, summary_text, suggested_questions_text


    except requests.exceptions.RequestException as e:
        error_msg = f"❌ HTTP/Network Error fetching data from API: {e}"
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    except Exception as e:
        error_msg = f"❌ An unexpected error occurred during API ingestion: {e}"
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."