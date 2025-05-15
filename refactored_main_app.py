# rag_app/main_app.py

import gradio as gr
import os

# Import all ingestion functions
from ingestion.pdf_ingestion import ingest_pdf_data_to_pinecone
from ingestion.url_ingestion import ingest_url_data_to_pinecone
from ingestion.sqlite_ingestion import ingest_sqlite_data_to_pinecone
from ingestion.postgres_ingestion import ingest_postgresql_data_to_pinecone
from ingestion.mongodb_ingestion import ingest_mongodb_data_to_pinecone
from ingestion.csv_ingestion import ingest_csv_data_to_pinecone
from ingestion.api_ingestion import ingest_api_data_to_pinecone # Import the new API ingestion

# Import the query engine function
from rag_query.query_engine import answer_question_about_ingested_data # Renamed for clarity

# Import config
from config import (
    PINECONE_NAMESPACE,
    PG_DEFAULT_BATCH_SIZE,
    API_DEFAULT_NUM_QUESTIONS,
    API_DEFAULT_CATEGORY_ID,
    # Add any other defaults needed for UI inputs from config
)

# --- Gradio UI Building Blocks ---
print("Building Gradio UI...")

# Define a single backend function to handle processing based on selected source
def process_selected_source(
    source_type,
    # Include ALL potential inputs from ALL sources here, in a defined order
    # This is necessary because the .click() event passes values in order.
    # We'll use only the relevant ones inside the function.
    pdf_file_obj,
    url_text,
    sqlite_db_path,
    pg_host, pg_port, pg_database, pg_user, pg_password, pg_table,
    mongo_host, mongo_port, mongo_database, mongo_collection, mongo_user, mongo_password,
    csv_file_obj,
    api_num_questions, api_category_id,
    global_batch_size # Use one global batch size input
):
    """
    Delegates the ingestion task to the appropriate function based on source_type.
    Receives all possible inputs, but only uses those relevant to the selected source.
    """
    print(f"Selected source for processing: {source_type}")
    status, summary, suggested_questions = "", "", "" # Initialize outputs

    try:
        # Pass the global batch size to all ingestion functions that use it
        batch_size_for_source = int(global_batch_size) if global_batch_size is not None else PG_DEFAULT_BATCH_SIZE # Fallback to default if None

        if source_type == "PDF":
            status, summary, suggested_questions = ingest_pdf_data_to_pinecone(
                 pdf_file_obj,
                 batch_size=batch_size_for_source # Pass global batch size
            )
        elif source_type == "URL":
             status, summary, suggested_questions = ingest_url_data_to_pinecone(
                  url_text,
                  batch_size=batch_size_for_source # Pass global batch size
             )
        elif source_type == "SQLite3":
            status, summary, suggested_questions = ingest_sqlite_data_to_pinecone(
                 sqlite_db_path,
                 batch_size=batch_size_for_source # Pass global batch size
            )
        elif source_type == "PostgreSQL":
            status, summary, suggested_questions = ingest_postgresql_data_to_pinecone(
                 pg_host, pg_port, pg_database, pg_user, pg_password, pg_table,
                 batch_size=batch_size_for_source # Pass global batch size
            )
        elif source_type == "MongoDB":
            status, summary, suggested_questions = ingest_mongodb_data_to_pinecone(
                 mongo_host, mongo_port, mongo_database, mongo_collection, mongo_user, mongo_password,
                 batch_size=batch_size_for_source # Pass global batch size
            )
        elif source_type == "CSV":
            status, summary, suggested_questions = ingest_csv_data_to_pinecone(
                 csv_file_obj,
                 batch_size=batch_size_for_source # Pass global batch size
             )
        elif source_type == "API (OpenTDB)":
             status, summary, suggested_questions = ingest_api_data_to_pinecone(
                 api_num_questions, api_category_id,
                 batch_size=batch_size_for_source # Pass global batch size
             )
        else:
            status = "❌ Please select a data source type."

    except Exception as e:
        status = f"❌ An unexpected error occurred during processing: {e}"
        print(f"Error in process_selected_source: {e}")
        summary = "Error during processing."
        suggested_questions = "Error during processing."


    return status, summary, suggested_questions # Return the outputs


# Define the chat function (assuming this is already working)
def chat_with_ai(question, history):
    """Handles the chat interaction."""
    # Your existing chat logic using answer_question_about_ingested_data
    # Make sure answer_question_about_ingested_data retrieves from the global Pinecone namespace
    response = answer_question_about_ingested_data(question)
    # Format response and history as required by Gradio Chatbot
    # Assuming answer_question_about_ingested_data returns the answer string
    history.append((question, response))
    return "", history # Clear input and return updated history


with gr.Blocks(theme=gr.themes.Base()) as demo: # Added a simple theme
    gr.Markdown("# RAG Powered AI Application with Multiple Knowledge Bases")
    gr.Markdown(f"Upload PDF, Provide URL, or Ingest from SQLite/Postgres/MongoDB/CSV/API. Get a summary and suggested questions, then ask anything about its content! Powered by Pinecone (Namespace: `{PINECONE_NAMESPACE}`), LangChain + Gemini Model, Reranking. Indexing from any source clears the previous index data in the namespace.")


    with gr.Tab("💬 Chat with AI"):
        # Existing Chatbot interface
        chatbot = gr.Chatbot(label="AI Chatbot")
        msg = gr.Textbox(label="Your Question", placeholder="e.g., What is your return policy?")
        clear = gr.Button("Clear Chat")

        msg.submit(chat_with_ai, inputs=[msg, chatbot], outputs=[msg, chatbot])
        clear.click(lambda: None, None, chatbot, queue=False) # Clear chat history

    with gr.Tab("⬆️ Data Ingestion"): # Single tab for all ingestion
        gr.Markdown("### Select Data Source and Ingest Data")

        source_type_dropdown = gr.Dropdown(
            label="Select Data Source Type",
            choices=["PDF", "URL", "SQLite3", "PostgreSQL", "MongoDB", "CSV", "API (OpenTDB)"],
            value="PDF" # Set a default value
        )

        # Use a single input for batch size, used by multiple sources
        global_batch_size_input = gr.Number(
             label="Batch Size (for processing documents/rows/items)",
             value=PG_DEFAULT_BATCH_SIZE, # Default value
             precision=0,
             minimum=1
        )


        # --- Input Groups for Each Data Source ---
        # Wrap inputs for each source in a gr.Group, initially hidden
        pdf_inputs = gr.Group(visible=True) # PDF is default, so visible initially
        with pdf_inputs:
            gr.Markdown("#### Upload and Process PDF")
            pdf_file_input = gr.File(label="Upload PDF File", file_types=[".pdf"], type="file")
            # pdf_batch_size_input = gr.Number(label="Batch Size (Chunks)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Use global batch size
            # Keep this placeholder input in the group for the delegate function
            pdf_placeholder_input = gr.Textbox(visible=False) # Placeholder to match expected inputs in delegate

        url_inputs = gr.Group(visible=False)
        with url_inputs:
            gr.Markdown("#### Process URL Content")
            url_text_input = gr.Textbox(label="Enter URL to Analyze", placeholder="https://...")
            # url_batch_size_input = gr.Number(label="Batch Size (Chunks)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Use global batch size
             # Keep this placeholder input in the group for the delegate function
            url_placeholder_input = gr.Textbox(visible=False)

        sqlite_inputs = gr.Group(visible=False)
        with sqlite_inputs:
            gr.Markdown("#### SQLite3 Ingestion")
            sqlite_db_path_input = gr.Textbox(label="SQLite Database Path", placeholder="e.g., ./knowledge_base/my_db.sqlite")
            # sqlite_batch_size_input = gr.Number(label="Batch Size (Rows)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Use global batch size
             # Keep this placeholder input in the group for the delegate function
            sqlite_placeholder_input = gr.Textbox(visible=False)


        postgresql_inputs = gr.Group(visible=False)
        with postgresql_inputs:
            gr.Markdown("#### PostgreSQL Ingestion")
            pg_host_input = gr.Textbox(label="Host", placeholder="localhost", value="localhost")
            pg_port_input = gr.Textbox(label="Port", placeholder="5432", value="5432")
            pg_database_input = gr.Textbox(label="Database Name", placeholder="mydatabase", value="rag_app_db")
            pg_user_input = gr.Textbox(label="User", placeholder="myuser", value="rag_app_user")
            pg_password_input = gr.Textbox(label="Password", placeholder="mypassword", type="password", value="rag_app_pwd_@123")
            pg_table_input = gr.Textbox(label="Table Name (e.g., faqs)", placeholder="my_table", value="system_design_faqs")
            # pg_batch_size_input = gr.Number(label="Batch Size (Records)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Use global batch size
             # Keep this placeholder input in the group for the delegate function
            pg_placeholder_input = gr.Textbox(visible=False)


        mongodb_inputs = gr.Group(visible=False)
        with mongodb_inputs:
            gr.Markdown("#### MongoDB Ingestion")
            mongo_host_input = gr.Textbox(label="Host", placeholder="localhost", value="localhost")
            mongo_port_input = gr.Textbox(label="Port", placeholder="27017", value="27017")
            mongo_database_input = gr.Textbox(label="Database Name", placeholder="mydatabase", value="rag_app_db")
            mongo_collection_input = gr.Textbox(label="Collection Name", placeholder="mycollection", value="system_design_faqs")
            mongo_user_input = gr.Textbox(label="User", placeholder="myuser", value="rag_app_user")
            mongo_password_input = gr.Textbox(label="Password", placeholder="mypassword", type="password", value="rag_app_pwd_@123")
            # mongo_batch_size_input = gr.Number(label="Batch Size (Documents)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Use global batch size
             # Keep this placeholder input in the group for the delegate function
            mongo_placeholder_input = gr.Textbox(visible=False)

        csv_inputs = gr.Group(visible=False)
        with csv_inputs:
            gr.Markdown("#### CSV Ingestion")
            csv_file_input = gr.File(label="Upload CSV File", file_types=[".csv"], type="file")
            # csv_batch_size_input = gr.Number(label="Batch Size (Rows)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Use global batch size
             # Keep this placeholder input in the group for the delegate function
            csv_placeholder_input = gr.Textbox(visible=False)


        api_inputs = gr.Group(visible=False)
        with api_inputs:
             gr.Markdown("#### API Ingestion (OpenTDB Example)")
             api_num_questions_input = gr.Number(
                 label="Number of Questions to Fetch",
                 value=API_DEFAULT_NUM_QUESTIONS,
                 precision=0,
                 minimum=1
             )
             api_category_id_input = gr.Number(
                  label="Optional Category ID (e.g., 9 for General Knowledge)",
                  value=API_DEFAULT_CATEGORY_ID,
                  precision=0,
                  minimum=1,
             )
             # api_batch_size_input = gr.Number(label="Batch Size (Documents)", value=PG_DEFAULT_BATCH_SIZE, precision=0, minimum=1) # Use global batch size
              # Keep this placeholder input in the group for the delegate function
             api_placeholder_input = gr.Textbox(visible=False)


        # Define outputs once for all sources
        process_button = gr.Button("Ingest Data")
        status_output = gr.Textbox(label="Processing Status", interactive=False, lines=3)
        summary_output = gr.Textbox(label="Generated Summary", interactive=False, lines=5)
        suggested_questions_output = gr.Textbox(label="Suggested Questions", interactive=False, lines=5)


        # --- Event Handlers ---

        # Function to show/hide input groups based on dropdown selection
        def update_inputs_visibility(source_type):
            """Returns updates to visibility for all input groups."""
            # Create a list of updates, one for each group
            updates = [
                gr.update(visible=source_type == "PDF"),
                gr.update(visible=source_type == "URL"),
                gr.update(visible=source_type == "SQLite3"),
                gr.update(visible=source_type == "PostgreSQL"),
                gr.update(visible=source_type == "MongoDB"),
                gr.update(visible=source_type == "CSV"),
                gr.update(visible=source_type == "API (OpenTDB)")
            ]
            # Return the updates corresponding to the groups
            return updates

        # Link dropdown change event to update visibility
        source_type_dropdown.change(
            fn=update_inputs_visibility,
            inputs=[source_type_dropdown],
            outputs=[pdf_inputs, url_inputs, sqlite_inputs, postgresql_inputs, mongodb_inputs, csv_inputs, api_inputs]
        )

        # Link process button click event to the delegate function
        # Pass ALL potential inputs, including the dropdown value
        # The order here MUST match the function signature of process_selected_source
        process_button.click(
            fn=process_selected_source,
            inputs=[
                source_type_dropdown, # This is the first input
                # PDF inputs (keep placeholders for consistent signature)
                pdf_file_input,
                # URL inputs (keep placeholders)
                url_text_input,
                # SQLite inputs (keep placeholders)
                sqlite_db_path_input,
                # PostgreSQL inputs (keep placeholders)
                pg_host_input, pg_port_input, pg_database_input, pg_user_input, pg_password_input, pg_table_input,
                # MongoDB inputs (keep placeholders)
                mongo_host_input, mongo_port_input, mongo_database_input, mongo_collection_input, mongo_user_input, mongo_password_input,
                # CSV inputs (keep placeholders)
                csv_file_input,
                # API inputs (keep placeholders)
                api_num_questions_input, api_category_id_input,
                # Global batch size
                global_batch_size_input, # This is the last input
            ],
            outputs=[status_output, summary_output, suggested_questions_output]
        )


# Launch the Gradio App
data_qa_ui = demo # Keep the variable name consistent if used elsewhere
data_qa_ui.launch(share=True) # share=True for a public link (useful for demo)