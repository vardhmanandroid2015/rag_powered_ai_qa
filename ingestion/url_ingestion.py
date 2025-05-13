# ingestion/url_ingestion.py

from langchain_community.document_loaders import WebBaseLoader
from langchain.schema import Document # Needed for Document type hint

# Import services
from services.embedding_utils import get_text_splitter, embed_and_index_documents
from services.summary_questions import get_full_text_from_docs, generate_document_summary, generate_suggested_questions_list

def process_url_for_rag(url: str):
    """
    Loads content from a URL, splits it into chunks, embeds and indexes it.
    Also generates a summary and suggested questions.
    """
    if not url:
        return "❌ Please enter a valid URL.", "", ""

    try:
        print(f"Loading content from URL: {url}")
        loader = WebBaseLoader(url)
        docs = loader.load() # List of Documents
        if not docs:
             return f"❌ Failed to load any content from URL: {url}", "", ""
        print(f"✅ Loaded {len(docs)} documents/pages from URL.")

        # Get splitter and split for chunking
        splitter = get_text_splitter()
        chunks = splitter.split_documents(docs) # Split Documents into smaller Document chunks
        print(f"✅ Split into {len(chunks)} chunks for indexing.")

        # Embed and index chunks (using the helper which clears namespace)
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
        error_msg = f"❌ Error processing URL: {e}"
        print(error_msg)
        return error_msg, "Nothing to Show..Contact Admin...", "Nothing to Show..Contact Admin..."