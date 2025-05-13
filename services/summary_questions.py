# services/summary_questions.py

from langchain.schema import Document # Needed for Document object type hint
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

# Import LLM initializer from services
from .initializer import initialize_llm

def get_full_text_from_docs(docs: list[Document]) -> str | None:
    """Extracts text from a list of LangChain Document objects."""
    if not docs:
        print("❌ No documents provided to extract text.")
        return None

    # Join the page contents into one long string
    full_text = "\n".join(doc.page_content for doc in docs)
    # print("✅ Extracted full text for summary/questions.") # Avoid spamming logs
    return full_text


def generate_document_summary(full_text: str) -> str:
    """Generates a summary of the document text using the LLM."""
    if not full_text:
        return "❌ No text available to summarize."

    try:
        llm = initialize_llm()
        if llm is None:
            return "❌ LLM not initialized. Cannot generate summary."

        summary_template = """
        Summarize the following document content concisely. Focus on the main topics and key points.

        Document Content:
        {document}

        Summary:
        """
        summary_prompt = PromptTemplate.from_template(summary_template)
        summary_chain = summary_prompt | llm | StrOutputParser()
        summary = summary_chain.invoke({"document": full_text})
        # print("✅ Generated summary.") # Avoid spamming logs
        return summary

    except Exception as e:
        error_msg = f"❌ Error generating summary: {e}"
        print(error_msg)
        return error_msg


def generate_suggested_questions_list(full_text: str) -> str:
    """Generates a list of suggested questions based on the document text using the LLM."""
    if not full_text:
        return "❌ No text available to generate questions."

    try:
        llm = initialize_llm()
        if llm is None:
            return "❌ LLM not initialized. Cannot generate questions."

        questions_template = """
        Based on the following document content, generate a list of exactly 5 distinct questions that a user could ask.
        These questions should cover different important aspects or topics from the document.
        Format the output as a numbered list.

        Document Content:
        {document}

        Suggested Questions (Numbered List):
        """
        questions_prompt = PromptTemplate.from_template(questions_template)
        questions_chain = questions_prompt | llm | StrOutputParser()
        suggested_questions = questions_chain.invoke({"document": full_text})
        # print("✅ Generated suggested questions.") # Avoid spamming logs
        return suggested_questions

    except Exception as e:
        error_msg = f"❌ Error generating suggested questions: {e}"
        print(error_msg)
        return error_msg