# =============================================================================
# backend/app/dependencies.py
#
# PURPOSE: Shared "dependencies" that FastAPI injects into route handlers.
#
# HOW IT WORKS (FastAPI Dependency Injection):
#   Instead of creating a Firebase client inside every route, we define it ONCE
#   here. FastAPI reads the function signature of each route, sees it needs
#   `db: firestore.Client = Depends(get_firestore)`, and automatically calls
#   get_firestore() before running the route. This means:
#     ✅ One connection pool, not N connections
#     ✅ Easy to mock in tests (swap Depends(...) with a fake)
#     ✅ Clean route handlers — no boilerplate
#
# USAGE in a router:
#   from fastapi import Depends
#   from app.dependencies import get_firestore, get_chroma
#
#   @router.get("/")
#   async def my_route(db = Depends(get_firestore)):
#       doc = db.collection("sessions").document("abc").get()
# =============================================================================

from functools import lru_cache
from google.cloud import firestore
from typing import Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.services.firebase import init_firebase, verify_token
from app.services.chroma import init_chroma


auth_scheme = HTTPBearer(auto_error=False)


# ── Firebase / Firestore ──────────────────────────────────────────────────────
# @lru_cache means the Firebase app is only initialized ONCE for the lifetime
# of the server process. Subsequent calls return the cached client.
@lru_cache(maxsize=1)
def _get_firebase_client() -> firestore.Client:
    return init_firebase()


def get_firestore() -> firestore.Client:
    """
    FastAPI dependency → injects a Firestore client into route handlers.
    Thread-safe because Firestore client is stateless between requests.
    """
    return _get_firebase_client()


# ── ChromaDB ──────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _get_chroma_client() -> Any:
    return init_chroma()


def get_chroma() -> Any:
    """
    FastAPI dependency → injects a ChromaDB client for RAG queries.
    """
    return _get_chroma_client()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
) -> dict:
    """
    Verify Firebase bearer token and return decoded claims.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
        )

    try:
        return verify_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )
