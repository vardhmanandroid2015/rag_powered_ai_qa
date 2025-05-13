# ingestion/pdf_ingestion.py

from langchain_community.document_loaders import PyPDFLoader
from langchain.schema import Document # Needed for Document type hint

# Import services
from services.embedding_utils import get_text_splitter, embed_and_index_documents
from services.summary_questions import get_full_text_from_docs, generate_document_summary, generate_suggested_questions_list

def process_uploaded_pdf(file):
    """
    Handles PDF upload by orchestrating loading, splitting, indexing, summarization,
    and question generation using smaller helper functions.
    Returns status, summary, and suggested questions.
    """
    if file is None:
        return "Please upload a PDF first.", "", ""

    file_path = file.name # Gradio provides the path via .name

    # --- Step 1: Load and Split ---
    try:
        print(f"Loading document from: {file_path}")
        loader = PyPDFLoader(file_path)
        documents = loader.load() # List of Documents (one per page)
        if not documents:
            return "❌ Failed to load any content from the PDF.", "", ""
        print(f"✅ Loaded {len(documents)} pages.")

        # Get splitter and split into chunks
        text_splitter = get_text_splitter()
        index_chunks = text_splitter.split_documents(documents) # Split Documents into smaller Document chunks
        print(f"✅ Split into {len(index_chunks)} chunks for indexing.")

    except Exception as e:
        error_msg = f"❌ Error loading or splitting PDF: {e}"
        print(error_msg)
        return error_msg, "", "" # Stop if loading/splitting fails


    # --- Step 2: Embed and Index ---
    # Pass the pre-split chunks to the embedder. This function will clear namespace.
    indexing_status = embed_and_index_documents(index_chunks, clear_namespace=True)
    # Continue even if indexing had a minor issue, but indicate status

    # --- Step 3: Get Full Text for Summary/Questions ---
    # Use the original documents list (before splitting) for summary/questions
    full_text = get_full_text_from_docs(documents)
    if full_text is None:
        summary = "❌ Could not extract text for summary/questions."
        suggested_questions = ""
        # Return with indexing status, but indicate failure for summary/questions
        return indexing_status + "\n" + summary, summary, suggested_questions


    # --- Step 4: Generate Summary ---
    summary = generate_document_summary(full_text)
    # Note: generate_document_summary already includes its own error handling and returns messages

    # --- Step 5: Generate Suggested Questions ---
    suggested_questions = generate_suggested_questions_list(full_text)
    # Note: generate_suggested_questions_list already includes its own error handling and returns messages

    # --- Final Return ---
    # Combine indexing status with potential summary/question generation errors
    final_status = indexing_status
    # Append summary/question errors only if they actually happened
    if "❌" in summary or "❌" in suggested_questions:
         additional_note = "\n\n⚠️ Note: There were issues generating summary or questions."
         if summary == "❌ No text available to summarize." or suggested_questions == "❌ No text available to generate questions.":
              additional_note = "\n\n⚠️ Note: Could not extract sufficient text for summary or questions."
         final_status += additional_note


    return final_status, summary, suggested_questions