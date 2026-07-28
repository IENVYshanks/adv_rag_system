import time

import logfire
from flashrank import Ranker, RerankRequest


_ranker = None


def _get_ranker() -> Ranker:
    """Initialize the local FlashRank engine lazily."""
    global _ranker
    if _ranker is None:
        logfire.info("Initializing FlashRank model locally")
        try:
            _ranker = Ranker(cache_dir="/tmp/flashrank")
        except Exception:
            _ranker = Ranker()
    return _ranker


def rerank_documents(
    query: str,
    documents: list[str],
    top_n: int = 5,
) -> list[str]:
    """Rerank retrieved documents with the local FlashRank cross-encoder."""
    if not documents:
        return []

    started = time.time()
    try:
        ranker = _get_ranker()
        passages = [
            {"id": index, "text": document}
            for index, document in enumerate(documents)
        ]
        results = ranker.rerank(
            RerankRequest(query=query, passages=passages)
        )
        reranked = [result["text"] for result in results[:top_n]]
        logfire.info(
            "FlashRank reranking completed",
            duration=round(time.time() - started, 3),
            candidates=len(documents),
            selected=len(reranked),
        )
        return reranked
    except Exception as exc:
        logfire.error(f"FlashRank reranking failed: {exc}")
        return documents[:top_n]
