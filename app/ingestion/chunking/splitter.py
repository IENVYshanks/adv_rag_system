from typing import List
import logfire

def chunk_text(text: str, chunk_size: int = 1500) -> List[str]:
    """
    Splits the input text into chunks of specified size.
    """
    with logfire.span("Text chunking", text_length = len(text)):
        if not text.strip():
            return []
        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current_chunk = ""
        current_length = 0
        for para in paragraphs:
            if len(para) + len(current_chunk) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        valid_chunks = [chunk for chunk in chunks if chunk.strip()]
        logfire.info("Chunking completed", total_chunks=len(valid_chunks))
        return valid_chunks 

        

