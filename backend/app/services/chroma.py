# =============================================================================
# backend/app/services/chroma.py
#
# PURPOSE: ChromaDB client + RAG helpers for topic retrieval.
#
# HOW IT WORKS:
#   ChromaDB is a local vector database. We store GD topics (and eventually
#   YouTube transcript chunks) as embeddings. At session start, we query for
#   the most relevant topic given the target company.
#
#   Week 1: Returns topics from a hard-coded list (no embeddings yet).
#   Week 4: Fully wired with YouTube transcript chunks + company filtering.
# =============================================================================

try:
    import chromadb  # type: ignore
    from chromadb.config import Settings as ChromaSettings  # type: ignore
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    chromadb = None  # type: ignore

import logging
from typing import Any

from app.config import settings  # type: ignore

logger = logging.getLogger(__name__)


def init_chroma() -> Any:
    """
    Creates and returns a persistent ChromaDB client.
    Data is stored in backend/chroma_data/ — survives server restarts.
    """
    if not HAS_CHROMA:
        logger.warning("ChromaDB is not installed (missing C++ tools). Running in MOCKED mode.")
        return None
        
    client = chromadb.PersistentClient(  # type: ignore
        path=settings.CHROMA_PERSIST_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),  # type: ignore
    )
    logger.info(f"✅ ChromaDB ready at {settings.CHROMA_PERSIST_DIR}")
    return client


def get_or_create_collection(client: Any):
    """
    Gets (or creates) the GD topics collection.
    """
    if not HAS_CHROMA or not client:
        return None
        
    return client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},    # cosine similarity for semantic search
    )


def query_topics(client: Any, company: str, n_results: int = 3) -> list[str]:
    """
    Query ChromaDB for GD topics relevant to the target company.
    """
    if not HAS_CHROMA or not client:
        return []
        
    collection = get_or_create_collection(client)
    if collection is None or collection.count() == 0:
        logger.warning("ChromaDB collection is empty. Seed it with ingest_yt_transcripts.py")
        return []

    results = collection.query(  # type: ignore
        query_texts=[f"GD topic for {company} placement round"],
        n_results=n_results,
        where={"company": company},        # filter by company tag
    )
    return results.get("documents", [[]])[0]
