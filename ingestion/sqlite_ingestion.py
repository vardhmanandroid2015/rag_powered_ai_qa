# ingestion/sqlite_ingestion.py

import sqlite3
import os # Needed for os.path.basename
from langchain.schema import Document # Needed for Document type hint

# Import services
from services.embedding_utils import get_text_splitter, embed_and_index_documents
from services.summary_questions import get_full_text_from_docs, generate_document_summary, generate_suggested_questions_list


def ingest_sqlite_data_to_pinecone(db_path: str, table: str = "faqs"):
    """
    Reads data from SQLite (assumes 'id', 'question', 'answer'),
    embeds it, and adds it to Pinecone.
    """
    if not db_path:
        return "❌ Please upload a SQLite DB file.", "", ""

    conn = None # Initialize connection variable
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Attempt to fetch rows from the specified table, expecting 'id', 'question' and 'answer'
        try:
            # SQLite doesn't natively support server-side cursors like PostgreSQL,
            # so fetchall is typically used here. For very large SQLite files,
            # you'd need a custom iteration logic if fetchall is too slow/memory intensive.
            cursor.execute(f"SELECT id, question, answer FROM {table}")
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
             return f"❌ Error querying table '{table}': {e}. Does the table exist and have 'id', 'question', and 'answer' columns?", "", ""


        if not rows:
            return f"❌ No data found in table '{table}' in the database.", "", ""

        # Prepare documents (for SQLite, we process all together as fetchall is used)
        docs = []
        for row in rows:
            faq_id, question, answer = row
            content = f"Q: {str(question)}\nA: {str(answer)}"
            # print(content) # Verbose, maybe remove for large data
            metadata = {"source": "sqlite", "db_file": os.path.basename(db_path), "table": table, "faq_id": str(faq_id)} # Use basename
            docs.append(Document(page_content=content, metadata=metadata))

        print(f"✅ Retrieved {len(docs)} records from SQLite database table '{table}'.")

        # Get splitter and split into chunks (all at once for SQLite flow)
        splitter = get_text_splitter()
        chunks = splitter.split_documents(docs)
        print(f"✅ Split into {len(chunks)} chunks for indexing.")

        # Embed and upsert (using existing helper which clears namespace once)
        indexing_status = embed_and_index_documents(chunks, clear_namespace=True)
        # Continue even if indexing had a minor issue

        # Get full text from original documents for summary/questions
        full_text = get_full_text_from_docs(docs)
        if full_text is None:
            summary = "❌ Could not extract text for summary/questions."
            suggested_questions = ""
            return indexing_status + "\n" + summary, summary, suggested_questions


        summary = generate_document_summary(full_text)
        suggested_questions = generate_suggested_questions_list(full_text)

        final_status = indexing_status
        # Append summary/question errors only if they actually happened
        if "❌" in summary or "❌" in suggested_questions:
             additional_note = "\n\n⚠️ Note: There were issues generating summary or questions."
             if summary == "❌ No text available to summarize." or suggested_questions == "❌ No text available to generate questions.":
                  additional_note = "\n\n⚠️ Note: Could not extract sufficient text for summary or questions."
             final_status += additional_note


        return final_status, summary, suggested_questions

    except Exception as e:
        error_msg = f"❌ Error during SQLite ingestion: {e}"
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."
    finally:
        if 'conn' in locals() and conn:
            conn.close()