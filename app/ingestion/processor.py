import uuid
import logfire
import argparse
import json
import os

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings
from app.services.retrieval.embeddings import embed_texts, get_embeddings_dim
from app.ingestion.loaders.pdf import parse_pdf
from app.ingestion.loaders.text import parse_text
from app.ingestion.loaders.html import parse_html
# from app.ingestion.loaders.docx import parse_docx
from app.ingestion.chunking.splitter import chunk_text

logfire.configure(
    service_name="enterprise-ingestion-service",
    token=os.getenv("LOGFIRE_TOKEN"),
    send_to_logfire="if-token-present",
    console=False,
)

PROCESSED_DATA_DIR = 'processed_data'

qdrant_client = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY,
    check_compatibility=False,
)

def save_processed_locally(data:dict, source_type :str, filename:str) -> str:
    """save parsed chunk metadata as json in processed_data /<source_type>/."""
    folder = os.path.join(PROCESSED_DATA_DIR, source_type)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"{filename}.json")
    with open(dest, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return dest

def process_file(
    file_path: str, filename: str, source_type: str
) -> tuple[int, int, int]:
    """parse -> chunk -> save locally -> embed -> index to qdrant"""
    files_parsed = 0
    chunks_created = 0
    points_created = 0

    with logfire.span("Processing file", file= filename, source=source_type):
        try:
            logfire.info(f"Parsing {filename}")
            # parse the file based on its extension
            ext = filename.lower().rsplit(".",1)[-1]
            if ext == "pdf":
                full_text = parse_pdf(file_path)
            elif ext == "txt":
                full_text = parse_text(file_path)
            elif ext in ("html", "htm"):
                full_text = parse_html(file_path)
            elif ext in ("docx", "pptx"):
                from app.ingestion.loaders.office import parse_office
                full_text = parse_office(file_path)
            else:
                logfire.warning(f"skipping unsupported file type: {filename}")
                return files_parsed, chunks_created, points_created
            if not full_text or not full_text.strip():
                logfire.warning(f"no text extracted from file: {filename} -- skipping")
                return files_parsed, chunks_created, points_created

            files_parsed = 1
            #chunk the text into smaller pieces
            chunks = chunk_text(full_text)
            if not chunks:
                return files_parsed, chunks_created, points_created
            chunks_created = len(chunks)
            # save the processed metadata locally

            processed_data = {
                "filename": filename,
                "source_type": source_type,
                "chunks": chunks,
            }
            local_path = save_processed_locally(processed_data, source_type, filename)
            logfire.info(f"Processed data saved locally at: {local_path}")

            # embed the chunks and index to Qdrant
            logfire.info(f"Embedding {len(chunks)} chunks from {filename}")
            with logfire.span("vectorizing and indexing"):
                embeddings = embed_texts(chunks)
                points = [
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "text" : chunk,
                            "source": filename,
                            "source_type": source_type
                        }
                    )
                    for chunk, vector in zip(chunks, embeddings)
                ]
                qdrant_client.upsert(
                    collection_name=settings.QDRANT_COLLECTION,
                    points=points
                ) 
            points_created = len(points)
            logfire.info(f"Finished {filename}: indexed {len(points)} chunks")
            return files_parsed, chunks_created, points_created

        except Exception as e:
            logfire.error(f"Error parsing file {filename}: {e}")
            return files_parsed, chunks_created, points_created
                

def process_directory(dir_path: str, source_type: str) -> tuple[int, int, int]:
    """process all files in a directory"""
    totals = [0, 0, 0]
    with logfire.span("Processing directory", path=dir_path, source=source_type):
        files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
        logfire.info(f"Found {len(files)} files in directory: {dir_path}")
        for filename in files:
            file_path = os.path.join(dir_path, filename)
            result = process_file(file_path, filename, source_type)
            totals = [total + value for total, value in zip(totals, result)]
    return tuple(totals)
        
    

def run_universal_ingestion(base_dir: str, explicit_source_type: str = None, wipe : bool = False):
    """"scan base_dir , map_subfolders to source_type, and ingest all documents
        pass -- wipe to drop and recreate qdrant collection before ingestion
    """
    totals = [0, 0, 0]
    with logfire.span("Universal ingestion started", base_directory=base_dir):
        collection_exists = qdrant_client.collection_exists(
            settings.QDRANT_COLLECTION
        )
        if wipe and collection_exists:
            qdrant_client.delete_collection(settings.QDRANT_COLLECTION)
            collection_exists = False
            logfire.info(
                f"Deleted Qdrant collection '{settings.QDRANT_COLLECTION}'"
            )

        if not collection_exists:
            dim = get_embeddings_dim()
            qdrant_client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=models.VectorParams(
                    size=dim,
                    distance=models.Distance.COSINE
                ),
            )
            logfire.info(
                f"Qdrant collection '{settings.QDRANT_COLLECTION}'"
                f"created with dimension {dim} and COSINE distance"
            )
        subdirs =[
            d for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
        ]
        if not subdirs:
            if explicit_source_type:
                source_type = explicit_source_type
            else:
                base_name = os.path.basename(os.path.normpath(base_dir)).lower()
                source_type = (
                    "true" if "true" in base_name
                    else "noisy" if "noisy" in base_name
                    else "general"
                )

            logfire.info(f"no sub-folder found - processing '{base_dir}' as '{source_type}'")
            result = process_directory(base_dir, source_type)
            totals = [total + value for total, value in zip(totals, result)]

        else:
            for subdir in subdirs:
                source_type = (
                    "true" if "true" in subdir.lower()
                    else "noisy" if "noisy" in subdir.lower()
                    else subdir
                )
                result = process_directory(
                    os.path.join(base_dir, subdir), source_type
                )
                totals = [total + value for total, value in zip(totals, result)]

        files_parsed, chunks_created, points_created = totals
        logfire.info(
            "Ingestion job completed: "
            f"{files_parsed} files parsed, "
            f"{chunks_created} chunks added, "
            f"{points_created} Qdrant points created",
            files_parsed=files_parsed,
            chunks_created=chunks_created,
            points_created=points_created,
        )
        return tuple(totals)


def main():
    parser = argparse.ArgumentParser(description="Parse, embed, and index documents.")
    parser.add_argument("base_dir", help="Directory containing documents to ingest.")
    parser.add_argument(
        "source_type",
        nargs="?",
        help="Source label used when base_dir contains files directly.",
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Drop and recreate the Qdrant collection before ingestion.",
    )
    args = parser.parse_args()
    if not os.path.isdir(args.base_dir):
        parser.error(f"Directory does not exist: {args.base_dir}")

    try:
        run_universal_ingestion(args.base_dir, args.source_type, args.wipe)
    except KeyboardInterrupt:
        logfire.warning("Ingestion interrupted by user")
    finally:
        qdrant_client.close()
        # qdrant-client 1.18.0 calls close() again from __del__, which emits a
        # spurious warning after the HTTP client has already closed cleanly.
        if hasattr(qdrant_client, "_client"):
            del qdrant_client._client


if __name__ == "__main__":
    main()
