# main_app.py

import gradio as gr

# Import high-level ingestion functions
from ingestion.pdf_ingestion import process_uploaded_pdf
from ingestion.url_ingestion import process_url_for_rag
from ingestion.sqlite_ingestion import ingest_sqlite_data_to_pinecone
from ingestion.postgres_ingestion import ingest_postgresql_data_to_pinecone
from ingestion.mongodb_ingestion import ingest_mongodb_data_to_pinecone

# Import the query engine function
from rag_query.query_engine import answer_question_about_ingested_data # Renamed for clarity

# Import config (needed for default values like batch size)
from config import *

# --- Gradio UI using Blocks ---
print("Building Gradio UI...")

# Update the title to reflect multiple data sources
with gr.Blocks(theme="soft", title="📄 Data Source RAG Q&A") as data_qa_ui:
    gr.Markdown(
        """
        # 📄 Data Source RAG Q&A
        Upload a PDF, Provide URL, or Ingest from SQLite/PostgreSQL.
        Get a summary and suggested questions, then ask anything about its content!
        Powered by Pinecone + LangChain + Gemini Model.
        Note: Indexing from any source clears the previous index data in the namespace.
        """
    )

    # --- Upload PDF Section ---
    with gr.Tab("📄 Upload and Process PDF"):
        gr.Markdown("### Upload Your PDF")
        file_input = gr.File(label="Choose a PDF file", file_types=[".pdf"])
        process_pdf_button = gr.Button("Process PDF")
        pdf_status_output = gr.Textbox(label="Processing Status", interactive=False, lines=3)
        pdf_summary_output = gr.Textbox(label="Document Summary", interactive=False, lines=5)
        pdf_suggested_questions_output = gr.Textbox(label="Suggested Questions", interactive=False, lines=5)

        # Link button click to processing function
        process_pdf_button.click(
            fn=process_uploaded_pdf,
            inputs=file_input,
            outputs=[pdf_status_output, pdf_summary_output, pdf_suggested_questions_output]
        )

    # --- URL Section ---
    with gr.Tab("🔍 Process URL Content"):
        gr.Markdown("### Enter URL to Analyze")
        url_input = gr.Textbox(label="Enter a Web URL", placeholder="https://...")
        url_process_button = gr.Button("Process URL")
        url_status_output = gr.Textbox(label="Status", interactive=False)
        url_summary_output = gr.Textbox(label="Summary", interactive=False, lines=5)
        url_suggested_questions_output = gr.Textbox(label="Suggested Questions", interactive=False, lines=5)

        # Link button click to processing function
        url_process_button.click(
            fn=process_url_for_rag,
            inputs=url_input,
            outputs=[url_status_output, url_summary_output, url_suggested_questions_output]
        )

    # --- SQLite Section ---
    with gr.Tab("📦 SQLite Ingestion"):
        gr.Markdown("### Upload Your SQLite DB file")
        sqlite_file = gr.File(label="Upload SQLite DB (.db)", file_types=[".db"])
        sqlite_table_name  = gr.Textbox(label="Enter Table Name (e.g., faqs)", placeholder="faqs", value="faqs") # Added default
        process_sqlite_button = gr.Button("Process DB file")
        sqlite_status_output = gr.Textbox(label="Processing Status", interactive=False, lines=3)
        sqlite_summary_output = gr.Textbox(label="Generated Summary", interactive=False, lines=5)
        sqlite_suggested_questions_output = gr.Textbox(label="Suggested Questions", interactive=False, lines=5)

        # Link button click to processing function
        process_sqlite_button.click(
            fn=ingest_sqlite_data_to_pinecone,
            inputs=[sqlite_file, sqlite_table_name],
            outputs=[sqlite_status_output, sqlite_summary_output, sqlite_suggested_questions_output]
        )

    # --- PostgreSQL Section ---
    with gr.Tab("🐘 PostgreSQL Ingestion"):
        gr.Markdown("### Enter PostgreSQL Connection Details and Batch Size")
        pg_host_input = gr.Textbox(label="Host", placeholder="localhost", value="127.0.0.1") # Changed default to 127.0.0.1 based on previous debugging
        pg_port_input = gr.Textbox(label="Port", placeholder="5432", value="5432")
        pg_database_input = gr.Textbox(label="Database Name", placeholder="mydatabase")
        pg_user_input = gr.Textbox(label="User", placeholder="myuser")
        # Using type="password" is more secure for passwords in UI
        pg_password_input = gr.Textbox(label="Password", placeholder="mypassword", type="password")
        pg_table_name_input  = gr.Textbox(label="Table Name (e.g., faqs)", placeholder="faqs")
        # Add the batch size input, defaulting to PG_DEFAULT_BATCH_SIZE from config
        pg_batch_size_input = gr.Number(label="Batch Size (Records)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1)

        process_pg_button = gr.Button("Ingest Data from PostgreSQL (Batched)")

        pg_status_output = gr.Textbox(label="Processing Status", interactive=False, lines=3)
        pg_summary_output = gr.Textbox(label="Generated Summary", interactive=False, lines=5)
        pg_suggested_questions_output = gr.Textbox(label="Suggested Questions", interactive=False, lines=5)

        # Link button click to processing function
        process_pg_button.click(
            fn=ingest_postgresql_data_to_pinecone,
            inputs=[pg_host_input, pg_port_input, pg_database_input, pg_user_input, pg_password_input,
                    pg_table_name_input, pg_batch_size_input], # Add batch size input
            outputs=[pg_status_output, pg_summary_output, pg_suggested_questions_output]
        )

    # --- MongoDB Section ---
    with gr.Tab("🍃 MongoDB Ingestion"): # Using a leaf icon for MongoDB
        gr.Markdown("### Enter MongoDB Connection Details and Batch Size")
        mongo_host_input = gr.Textbox(label="Host", placeholder="localhost", value="localhost") # Docker hostname often 'localhost'
        mongo_port_input = gr.Textbox(label="Port", placeholder="27017", value="27017")
        mongo_database_input = gr.Textbox(label="Database Name", placeholder="mydatabase", value="rag_app_db") # Default from Docker setup
        mongo_collection_input = gr.Textbox(label="Collection Name", placeholder="mycollection", value="system_design_faqs") # Default from mongoimport
        mongo_user_input = gr.Textbox(label="User", placeholder="myuser", value="rag_app_user") # Default from Docker setup
        mongo_password_input = gr.Textbox(label="Password", placeholder="mypassword", type="password", value="rag_app_pwd_@123") # Default from Docker setup
        mongo_batch_size_input = gr.Number(label="Batch Size (Documents)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Reuse config default

        process_mongo_button = gr.Button("Ingest Data from MongoDB (Batched)")

        mongo_status_output = gr.Textbox(label="Processing Status", interactive=False, lines=3)
        mongo_summary_output = gr.Textbox(label="Generated Summary", interactive=False, lines=5)
        mongo_suggested_questions_output = gr.Textbox(label="Suggested Questions", interactive=False, lines=5)

        process_mongo_button.click(
            fn=ingest_mongodb_data_to_pinecone,
            inputs=[mongo_host_input, mongo_port_input, mongo_database_input, mongo_collection_input,
                    mongo_user_input, mongo_password_input, mongo_batch_size_input],
            outputs=[mongo_status_output, mongo_summary_output, mongo_suggested_questions_output]
        )

    # --- Ask Questions Section ---
    with gr.Tab("🧠 Ask Questions"):
        gr.Markdown("### Ask Questions About the Ingested Data")
        gr.Markdown("*(Make sure you have successfully processed data from one of the tabs above)*")
        question_input = gr.Textbox(label="Your Question", placeholder="e.g. What is your return policy?")
        ask_button = gr.Button("Get Answer")
        context_output = gr.Textbox(label="Retrieved Context", interactive=False, lines=10)
        answer_output = gr.Textbox(label="Answer", interactive=False, lines=5)

        # Link button click to answering function (now imported)
        ask_button.click(
            fn=answer_question_about_ingested_data, # Use the imported function
            inputs=question_input,
            outputs=[context_output, answer_output]
        )

print("Gradio UI built. Launching...")

# Launch the Gradio App
data_qa_ui.launch()