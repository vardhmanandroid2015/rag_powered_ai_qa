# ingestion/postgres_ingestion.py

import psycopg2
from psycopg2 import sql # Import sql module for safe identifier formatting
from langchain.schema import Document # Needed for Document type hint
from langchain_pinecone import PineconeVectorStore # Needed for incremental upsert

# Import services
from services.initializer import initialize_embeddings, initialize_pinecone_client, clear_pinecone_namespace
from services.embedding_utils import get_text_splitter # Renamed splitter helper
from services.summary_questions import get_full_text_from_docs, generate_document_summary, generate_suggested_questions_list

# import config.py
from config import * # Needs CHUNK_SIZE, CHUNK_OVERLAP, PINECONE_*, PG_DEFAULT_BATCH_SIZE

def ingest_postgresql_data_to_pinecone(host, port, database, user, password, table, batch_size=PG_DEFAULT_BATCH_SIZE):
    """
    Reads data from PostgreSQL (assumes 'id', 'question', 'answer') in batches,
    embeds it, and adds it to Pinecone.
    Clears the Pinecone namespace ONCE before starting ingestion.
    """
    # Convert batch_size to integer if it comes from Gradio Number input
    try:
        batch_size = int(batch_size)
    except (ValueError, TypeError):
        return "❌ Invalid batch size provided.", "", ""

    if not all([host, port, database, user, password, table]) or batch_size <= 0:
        return "❌ Please provide all PostgreSQL connection details, table name, and a valid batch size (> 0).", "", ""

    conn = None
    cursor = None
    try:
        # Establish PostgreSQL connection
        print(f"Attempting to connect to PostgreSQL DB '{database}' on {host}:{port} for batch ingestion...")
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        # Use a server-side cursor for large results
        # This prevents fetching all results into client memory at once
        # Give cursor a name for server-side processing. Requires transaction isolation level > READ UNCOMMITTED
        # Default isolation is often fine, but be aware of potential issues with very long-running cursors.
        cursor = conn.cursor('server_side_cursor')
        print("✅ PostgreSQL connection established.")

        # Initialize Embeddings and Pinecone Vector Store outside the loop
        embeddings = initialize_embeddings()
        if embeddings is None:
            return "❌ Failed to initialize embeddings. Cannot index.", "", ""

        # Clear the namespace ONCE before starting batch ingestion
        clear_status = clear_pinecone_namespace()
        if "❌" in clear_status:
             # Decide if this is a fatal error. For ingestion, probably is.
             return clear_status, "", ""

        # Initialize Pinecone VectorStore for incremental additions
        # Note: This constructor *does not* upsert data, it prepares the object
        vectorstore = PineconeVectorStore(
            index_name=PINECONE_INDEX_NAME,
            embedding=embeddings,
            namespace=PINECONE_NAMESPACE
        )
        print("✅ Pinecone VectorStore initialized for incremental upserts.")

        # Initialize Text Splitter
        text_splitter = get_text_splitter()
        print("✅ Text Splitter initialized.")


        # Fetch records using a server-side cursor
        # Use sql.SQL and sql.Identifier for safely including the table name
        sql_query = sql.SQL("SELECT id, question, answer FROM {}").format(sql.Identifier(table))
        print(f"Executing query using server-side cursor for batching: {sql_query.as_string(conn)}") # as_string for logging
        try:
            cursor.execute(sql_query)
        except psycopg2.errors.UndefinedTable:
             return f"❌ Error: Table '{table}' not found in database '{database}'.", "", ""
        except psycopg2.ProgrammingError as e:
             return f"❌ Error querying table '{table}': {e}. Does the table have 'id', 'question', and 'answer' columns?", "", ""
        except Exception as e:
             return f"❌ An unexpected error occurred while executing query: {e}", "", ""


        rows_processed = 0
        chunks_indexed = 0
        all_docs_for_summary = [] # Collect first batch docs for summary/questions (optional)
        is_first_batch = True

        print(f"Starting batch fetching with fetchmany size: {batch_size}")

        while True:
            # Fetch a batch of rows from the server-side cursor
            rows = cursor.fetchmany(batch_size)

            # If no more rows, break the loop
            if not rows:
                print("✅ Finished fetching all batches.")
                break

            # --- Process the current batch ---
            batch_docs = []
            for row in rows:
                # Assuming row is (id, question, answer)
                # Ensure question and answer are treated as strings
                try:
                    faq_id, question, answer = row
                    content = f"Q: {str(question)}\nA: {str(answer)}"
                    metadata = {"source": "postgresql", "db_host": host, "db_name": database, "table": table, "faq_id": str(faq_id)}
                    batch_docs.append(Document(page_content=content, metadata=metadata))
                except Exception as e:
                    print(f"⚠️ Skipping row due to formatting error: {row}. Error: {e}")
                    continue # Skip this row and continue with the next


            # Collect docs from the first batch for summary/questions (if desired)
            if is_first_batch and batch_docs: # Only capture if it's the first batch AND it has docs
                 all_docs_for_summary = batch_docs
                 is_first_batch = False # Only capture the first batch


            # Split the batch documents into chunks
            batch_chunks = text_splitter.split_documents(batch_docs)

            # Embed and add chunks from this batch to Pinecone incrementally
            if batch_chunks:
                # add_documents handles internal batching to Pinecone API
                try:
                    vectorstore.add_documents(batch_chunks)
                    rows_processed += len(rows) # Count all rows from the fetchmany call
                    chunks_indexed += len(batch_chunks)
                    print(f"✅ Processed {rows_processed} records, Indexed {chunks_indexed} chunks so far...")
                except Exception as e:
                    print(f"❌ Error upserting batch (rows {rows_processed} to {rows_processed + len(rows)}): {e}")
                    # Decide how to handle upsert error: skip batch, retry, stop?
                    # For now, log and continue with next batch
                    rows_processed += len(rows) # Still count these rows as "processed" from DB fetch perspective
            else:
                rows_processed += len(rows) # Still count rows even if no chunks were generated (shouldn't happen usually)
                print(f"⚠️ Processed {rows_processed} records, but batch generated no chunks.")


        # --- Final Steps After Batching ---
        # Commit the transaction (important for server-side cursors)
        # It's good practice to commit explicitly.
        conn.commit()
        print("✅ Database transaction committed.")

        final_status = f"✅ Successfully ingested {rows_processed} records ({chunks_indexed} chunks) from PostgreSQL into Pinecone namespace '{PINECONE_NAMESPACE}' using batch size {batch_size}."
        print(final_status)

        # Generate summary and questions from the first batch's documents (or indicate skipped)
        # Generating from a small batch might not be representative, but it's better than nothing
        # or fetching all data just for this. Alternative: return placeholders.
        summary_text = "Summary/Suggestions generated from a sample (first batch) of the data."
        suggested_questions_text = "Suggestions generated from a sample (first batch) of the data."
        if all_docs_for_summary: # Check if we actually captured a first batch
            # Generate full text from the sample documents
            sample_full_text = get_full_text_from_docs(all_docs_for_summary)
            if sample_full_text:
                summary_text = generate_document_summary(sample_full_text)
                suggested_questions_text = generate_suggested_questions_list(sample_full_text)
            else:
                 summary_text = "❌ Could not extract text from sample for summary/questions."
                 suggested_questions_text = "❌ Could not extract text from sample for summary/questions."
        else:
             summary_text = "⚠️ No data processed. Summary/Suggestions not generated."
             suggested_questions_text = "⚠️ No data processed. Summary/Suggestions not generated."


        # Append notes about summary/questions being from sample if we processed more than one batch
        if rows_processed > batch_size:
             summary_text += "\n\n*Note: Generated from a sample (first batch) of data.*"
             suggested_questions_text += "\n\n*Note: Generated from a sample (first batch) of data.*"


        # Check if there were any errors logged during processing (heuristic)
        # A more robust way would be to count errors explicitly
        if "❌" in final_status or "❌" in summary_text or "❌" in suggested_questions_text or "⚠️" in final_status:
             final_status += "\n\n⚠️ Review logs for potential errors or warnings during ingestion."


        return final_status, summary_text, suggested_questions_text

    except psycopg2.OperationalError as e:
        error_msg = f"❌ PostgreSQL Connection Error during batch ingestion: {e}. Please check host, port, database name, user, and password."
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    except Exception as e:
        error_msg = f"❌ An unexpected error occurred during PostgreSQL ingestion: {e}"
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    finally:
        # Ensure the cursor and connection are closed
        if cursor:
            try:
                cursor.close()
            except psycopg2.ProgrammingError:
                # Handle case where server-side cursor might already be closed by error
                pass
        if conn:
            conn.close()
            print("✅ PostgreSQL connection closed.")