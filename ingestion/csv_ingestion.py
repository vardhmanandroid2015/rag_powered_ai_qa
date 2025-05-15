import pandas as pd
from langchain.schema import Document
from langchain_pinecone import PineconeVectorStore

# Import services
from services.initializer import initialize_embeddings, initialize_pinecone_client, clear_pinecone_namespace
from services.embedding_utils import get_text_splitter
from services.summary_questions import get_full_text_from_docs, generate_document_summary, generate_suggested_questions_list

# import config.py
from config import * # Needs CHUNK_SIZE, CHUNK_OVERLAP, PINECONE_*, PG_DEFAULT_BATCH_SIZE (reused for batching)

import os # Needed to check file existence

def ingest_csv_data_to_pinecone(csv_file_obj, batch_size=PG_DEFAULT_BATCH_SIZE):
    """
    Reads data from a CSV file (provided as a file object from Gradio upload),
    embeds it, and adds it to Pinecone.
    Assumes the CSV has 'Question' and 'Answer' columns.
    Clears the Pinecone namespace ONCE before starting ingestion (follows existing pattern).
    """
    # Gradio File component provides a temporary file path as csv_file_obj.name
    csv_file_path = csv_file_obj.name if csv_file_obj else None

    # Convert batch_size to integer
    try:
        batch_size = int(batch_size)
    except (ValueError, TypeError):
        return "❌ Invalid batch size provided.", "", ""

    if not csv_file_path or not os.path.exists(csv_file_path) or batch_size <= 0:
        return "❌ Please upload a valid CSV file and provide a valid batch size (> 0).", "", ""

    try:
        print(f"Attempting to read CSV file from: {csv_file_path}")
        # Read the CSV file into a pandas DataFrame
        df = pd.read_csv(csv_file_path)
        print(f"✅ Successfully read CSV. Found {len(df)} rows.")

        # Validate required columns
        if 'Question' not in df.columns or 'Answer' not in df.columns:
            return "❌ CSV must contain 'Question' and 'Answer' columns.", "", ""

        # Initialize Embeddings and Pinecone Vector Store outside the loop
        embeddings = initialize_embeddings()
        if embeddings is None:
            return "❌ Failed to initialize embeddings. Cannot index.", "", ""

        # Clear the namespace ONCE before starting batch ingestion
        # NOTE: This clears the *entire* namespace defined in config.py,
        # removing previously indexed data from other sources (PDFs, URLs, DBs).
        # If you want to *add* CSV data without removing others, remove this call
        # and manage namespace clearing externally or use different namespaces.
        clear_status = clear_pinecone_namespace()
        if "❌" in clear_status:
             # Decide if this is a fatal error. For ingestion, probably is.
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

        rows_processed = 0
        chunks_indexed = 0
        all_docs_for_summary = [] # Collect first batch docs for summary/questions
        is_first_batch = True

        print(f"Starting batch processing from CSV file '{os.path.basename(csv_file_path)}'...")

        batch_docs = []
        # Iterate through DataFrame rows
        for index, row in df.iterrows():
            try:
                question = row.get("Question")
                answer = row.get("Answer")

                # Ensure question and answer are not NaN and are treated as strings
                # Use .notna() and .astype(str) for robustness
                if pd.notna(question) and pd.notna(answer):
                    content = f"Q: {str(question)}\nA: {str(answer)}"
                    metadata = {
                        "source": "csv",
                        "filename": os.path.basename(csv_file_path),
                        "row_index": int(index) # Keep track of original row number
                    }
                    batch_docs.append(Document(page_content=content, metadata=metadata))
                else:
                    print(f"⚠️ Skipping row {index}: Missing 'Question' or 'Answer' field.")
                    continue

                # Check if batch size is reached
                if len(batch_docs) == batch_size:
                     # Process and upsert the current batch
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
                          rows_processed += len(batch_docs)
                          print(f"⚠️ Processed {rows_processed} records, but batch generated no chunks.")


                     batch_docs = [] # Reset batch

            except Exception as e:
                print(f"❌ Error processing CSV row {index}: {e}")
                # Log error and continue with next row

        # --- Process any remaining documents in the last batch ---
        if batch_docs:
             batch_chunks = text_splitter.split_documents(batch_docs)

             # If there was only one batch processed (or less), ensure we capture it
             if is_first_batch:
                  all_docs_for_summary = batch_docs[:]
                  is_first_batch = False # Should already be False if any docs processed

             if batch_chunks:
                vectorstore.add_documents(batch_chunks)
                rows_processed += len(batch_docs)
                chunks_indexed += len(batch_chunks)
                print(f"✅ Processed {rows_processed} total records, Indexed {chunks_indexed} total chunks (including final batch).")
             else:
                 rows_processed += len(batch_docs)
                 print(f"⚠️ Processed {rows_processed} total records, but final batch generated no chunks.")


        # --- Final Steps After Batching ---
        final_status = f"✅ Successfully ingested {rows_processed} records ({chunks_indexed} chunks) from CSV file '{os.path.basename(csv_file_path)}' into Pinecone namespace '{PINECONE_NAMESPACE}' using batch size {batch_size}."
        print(final_status)

        # Generate summary and questions from the first batch's documents (or indicate skipped)
        summary_text = "Summary/Suggestions generated from a sample (first batch) of the data."
        suggested_questions_text = "Suggestions generated from a sample (first batch) of the data."
        if all_docs_for_summary: # Check if we actually captured a first batch
            sample_full_text = get_full_text_from_docs(all_docs_for_summary)
            if sample_full_text:
                summary_text = generate_document_summary(sample_full_text)
                suggested_questions_text = generate_suggested_questions_list(sample_full_text)
            else:
                 summary_text = "❌ Could not extract text from sample for summary/questions."
                 suggested_questions_text = "❌ Could not extract text from sample for summary/questions."
        else:
             summary_text = "⚠️ No data processed from CSV. Summary/Suggestions not generated."
             suggested_questions_text = "⚠️ No data processed from CSV. Summary/Suggestions not generated."


        # Append notes about summary/questions being from sample if needed
        # A simple check: if total rows processed > batch_size (meaning there were more than one batch processed or a partial second batch)
        if rows_processed > batch_size:
             summary_text += "\n\n*Note: Generated from a sample (first batch) of data.*"
             suggested_questions_text += "\n\n*Note: Generated from a sample (first batch) of data.*"

        return final_status, summary_text, suggested_questions_text

    except FileNotFoundError:
        error_msg = f"❌ CSV file not found at {csv_file_path}."
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    except pd.errors.EmptyDataError:
        error_msg = f"❌ The CSV file {csv_file_path} is empty."
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    except pd.errors.ParserError as e:
         error_msg = f"❌ Error parsing CSV file {csv_file_path}: {e}"
         print(error_msg)
         return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    except Exception as e:
        error_msg = f"❌ An unexpected error occurred during CSV ingestion: {e}"
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."