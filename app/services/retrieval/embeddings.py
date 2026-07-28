import time

import logfire
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings


BATCH_SIZE = 50
_GEMINI_DIM = 3072
_FALLBACK_DIM = 768

_active_model = None
_model_type: str | None = None


def _probe_gemini():
    """Try one embedding to see if Gemini is available."""
    try:
        model = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embeddings-2-preview",
            google_api_key=settings.GEMINI_API_KEY,
        )
        model.embed_query("probe")
        logfire.info(
            "Gemini embeddings available "
            "(models/gemini-embeddings-2-preview)"
        )
        return model
    except Exception as exc:
        logfire.warning(
            f"Gemini embeddings not available: {exc} | falling back to "
            "all-mpnet-base-v2 / sentence-transformers"
        )
        return None


def _load_fallback():
    from sentence_transformers import SentenceTransformer

    logfire.info(
        "Loading fallback model: "
        "(all-mpnet-base-v2 / sentence-transformers, dim = 768)"
    )
    return SentenceTransformer("all-mpnet-base-v2")


def _init():
    global _active_model, _model_type

    if _active_model:
        return

    gemini = _probe_gemini()
    if gemini:
        _active_model = gemini
        _model_type = "gemini"
    else:
        _active_model = _load_fallback()
        _model_type = "fallback"


def get_embeddings_dim() -> int:
    """Return vector dimensions for the active embedding model."""
    _init()
    return _GEMINI_DIM if _model_type == "gemini" else _FALLBACK_DIM


def _embed_batch(batch: list[str]) -> list[list[float]]:
    """Embed a batch of texts using the active model."""
    if _model_type == "gemini":
        for attempt in range(4):
            try:
                return _active_model.embed_documents(batch)
            except Exception as exc:
                error = str(exc).lower()
                is_rate_limit = any(
                    value in error
                    for value in (
                        "rate",
                        "quota",
                        "429",
                        "resource_exhausted",
                    )
                )
                if is_rate_limit and attempt < 3:
                    wait = 2**attempt
                    logfire.warning(
                        f"Gemini rate limit hit - retrying in {wait}s "
                        f"(attempt {attempt + 1}/4)"
                    )
                    time.sleep(wait)
                else:
                    logfire.error(f"Gemini embeddings failed: {exc}")
                    raise
        raise RuntimeError("Gemini rate limit persisted after four attempts.")

    return _active_model.encode(batch, show_progress_bar=False).tolist()


def embed_query(query: str) -> list[float]:
    """Embed a single query using the active model."""
    _init()
    if _model_type == "gemini":
        return _active_model.embed_query(query)
    return _active_model.encode([query], show_progress_bar=False)[0].tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using the active model."""
    _init()
    all_embeddings: list[list[float]] = []
    for index in range(0, len(texts), BATCH_SIZE):
        batch = texts[index : index + BATCH_SIZE]
        with logfire.span(
            "embedding_batch",
            model=_model_type,
            start=index,
            size=len(batch),
        ):
            all_embeddings.extend(_embed_batch(batch))
    return all_embeddings
