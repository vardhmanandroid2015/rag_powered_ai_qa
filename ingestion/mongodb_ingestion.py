# rag_app/ingestion/mongodb_ingestion.py

import pymongo
from langchain.schema import Document # Needed for Document type hint
from langchain_pinecone import PineconeVectorStore # Needed for incremental upsert

# Import services
from services.initializer import initialize_embeddings, initialize_pinecone_client, clear_pinecone_namespace
from services.embedding_utils import get_text_splitter
from services.summary_questions import get_full_text_from_docs, generate_document_summary, generate_suggested_questions_list

# import config.py
from config import * # Needs CHUNK_SIZE, CHUNK_OVERLAP, PINECONE_*, PG_DEFAULT_BATCH_SIZE (reused for batching)


def ingest_mongodb_data_to_pinecone(host, port, database, collection, user, password, batch_size=PG_DEFAULT_BATCH_SIZE):
    """
    Reads data from MongoDB in batches, embeds it, and adds it to Pinecone.
    Assumes documents in MongoDB have 'question' and 'answer' fields.
    Clears the Pinecone namespace ONCE before starting ingestion.
    """
    # Convert batch_size to integer if it comes from Gradio Number input
    try:
        batch_size = int(batch_size)
    except (ValueError, TypeError):
        return "❌ Invalid batch size provided.", "", ""

    if not all([host, port, database, collection, user, password]) or batch_size <= 0:
        return "❌ Please provide all MongoDB connection details, collection name, and a valid batch size (> 0).", "", ""

    client = None
    try:
        # Establish MongoDB connection
        print(f"Attempting to connect to MongoDB DB '{database}' on {host}:{port} for batch ingestion...")
        # Authentication against the user's database ('authSource') is important
        client = pymongo.MongoClient(
            host=host,
            port=int(port), # Ensure port is integer
            username=user,
            password=password,
            authSource=database # Authenticate against the database the user was created in
        )
        # The ismaster command is cheap and does not require auth.
        # It raises AutoReconnect exception if connection is not possible.
        client.admin.command('ismaster') # Verify connection and auth
        print("✅ MongoDB connection established.")

        db = client[database] # Select the database
        coll = db[collection] # Select the collection

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
        vectorstore = PineconeVectorStore(
            index_name=PINECONE_INDEX_NAME,
            embedding=embeddings,
            namespace=PINECONE_NAMESPACE
        )
        print("✅ Pinecone VectorStore initialized for incremental upserts.")

        # Initialize Text Splitter
        text_splitter = get_text_splitter()
        print("✅ Text Splitter initialized.")

        # Fetch records using a cursor
        # PyMongo cursors fetch data in batches automatically
        mongo_cursor = coll.find({}) # find({}) gets all documents

        rows_processed = 0
        chunks_indexed = 0
        all_docs_for_summary = [] # Collect first batch docs for summary/questions (optional)
        is_first_batch = True

        print(f"Starting batch fetching from MongoDB collection '{collection}'...")

        # Iterate through the cursor, which fetches in batches
        batch_docs = []
        for mongo_doc in mongo_cursor:
            try:
                # Assuming document has 'question' and 'answer' fields
                # Add error handling in case a document is missing fields
                question = mongo_doc.get("question")
                answer = mongo_doc.get("answer")
                doc_id = mongo_doc.get("_id") # Capture MongoDB's _id

                if question is None or answer is None:
                    print(f"⚠️ Skipping document {doc_id}: Missing 'question' or 'answer' field.")
                    continue # Skip this document

                # Ensure question and answer are treated as strings
                content = f"Q: {str(question)}\nA: {str(answer)}"
                metadata = {
                    "source": "mongodb",
                    "db_name": database,
                    "collection": collection,
                    "mongo_id": str(doc_id) # Convert ObjectId to string
                }
                batch_docs.append(Document(page_content=content, metadata=metadata))

                # Check if batch size is reached
                if len(batch_docs) == batch_size:
                     # Process and upsert the current batch
                     batch_chunks = text_splitter.split_documents(batch_docs)

                     if is_first_batch:
                          all_docs_for_summary = batch_docs[:] # Capture a copy of the first batch
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
                print(f"❌ Error processing MongoDB document (ID: {mongo_doc.get('_id', 'N/A')}): {e}")
                # Log error and continue with next document

        # --- Process any remaining documents in the last batch ---
        if batch_docs:
             batch_chunks = text_splitter.split_documents(batch_docs)

             if is_first_batch: # If loop didn't even complete one full batch size
                  all_docs_for_summary = batch_docs[:]
                  is_first_batch = False # Should already be False if any docs were processed

             if batch_chunks:
                vectorstore.add_documents(batch_chunks)
                rows_processed += len(batch_docs)
                chunks_indexed += len(batch_chunks)
                print(f"✅ Processed {rows_processed} total records, Indexed {chunks_indexed} total chunks (including final batch).")
             else:
                rows_processed += len(batch_docs)
                print(f"⚠️ Processed {rows_processed} total records, but final batch generated no chunks.")


        # --- Final Steps After Batching ---
        final_status = f"✅ Successfully ingested {rows_processed} records ({chunks_indexed} chunks) from MongoDB collection '{collection}' into Pinecone namespace '{PINECONE_NAMESPACE}' using batch size {batch_size}."
        print(final_status)

        # Generate summary and questions from the first batch's documents (or indicate skipped)
        # Generating from a small sample might not be representative, but avoids loading all data.
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
             summary_text = "⚠️ No data processed. Summary/Suggestions not generated."
             suggested_questions_text = "⚠️ No data processed. Summary/Suggestions not generated."


        # Append notes about summary/questions being from sample if needed
        # A simple check: if total rows processed > batch_size (meaning there were more than one batch processed or a partial second batch)
        if rows_processed > batch_size:
             summary_text += "\n\n*Note: Generated from a sample (first batch) of data.*"
             suggested_questions_text += "\n\n*Note: Generated from a sample (first batch) of data.*"

        # Check if there were any errors logged during processing (heuristic)
        # A more robust way would be to count errors explicitly
        # if "❌" in final_status or "❌" in summary_text or "❌" in suggested_questions_text or "⚠️" in final_status:
        #      final_status += "\n\n⚠️ Review logs for potential errors or warnings during ingestion."
        # ^ Refactored to only append sample note

        return final_status, summary_text, suggested_questions_text

    except pymongo.errors.ConnectionFailure as e:
        error_msg = f"❌ MongoDB Connection Error: {e}. Please check host, port, username, password, and authSource '{database}'."
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    except pymongo.errors.AuthenticationFailed as e:
         error_msg = f"❌ MongoDB Authentication Failed: {e}. Please check username, password, and authSource '{database}'."
         print(error_msg)
         return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    except Exception as e:
        error_msg = f"❌ An unexpected error occurred during MongoDB ingestion: {e}"
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    finally:
        # Ensure the MongoDB client connection is closed
        if client:
            client.close()
            print("✅ MongoDB connection closed.")