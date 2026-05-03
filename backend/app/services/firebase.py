# =============================================================================
# backend/app/services/firebase.py
#
# PURPOSE: Initialise the Firebase Admin SDK and expose Firestore helpers.
#
# HOW IT WORKS:
#   Firebase Admin SDK lets our Python backend talk to:
#     - Firestore (NoSQL database for sessions, turns, analytics)
#     - Firebase Auth (verify user JWT tokens on protected routes)
#
#   We initialise it ONCE using a service account JSON file downloaded from
#   Firebase Console → Project Settings → Service Accounts.
#
# IMPORTANT: Never commit serviceAccountKey.json to Git!
#   It's already in .gitignore. Share it with teammates via a secure channel.
# =============================================================================

import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud.firestore_v1 import Client
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# ── Firestore Collection Names ────────────────────────────────────────────────
# Centralise these constants so a typo in one place doesn't break everything.
COL_USERS = "users"
COL_SESSIONS = "sessions"
COL_TURNS = "turns"          # subcollection: sessions/{id}/turns/{id}
COL_ANALYTICS = "analytics"


def init_firebase() -> Client:
    """
    Initialise Firebase Admin SDK and return a Firestore client.
    Called once at startup via dependencies.py (lru_cache).

    Returns:
        firestore.Client — use this to read/write to Firestore.
    """
    # Guard: don't initialise twice (would raise an error)
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred, {
            "projectId": settings.FIREBASE_PROJECT_ID,
        })
        logger.info("✅ Firebase Admin SDK initialised")

    return firestore.client()


# ── Helper: Verify Firebase Auth Token ────────────────────────────────────────
def verify_token(id_token: str) -> dict:
    """
    Verify a Firebase ID token from the frontend.

    The React frontend calls Firebase Auth → gets a JWT id_token.
    It sends this token in the Authorization header:
        Authorization: Bearer <id_token>

    We verify it here. If invalid/expired, raises firebase_admin.auth.AuthError.

    Returns:
        dict — decoded token payload, including uid, email, name.
    """
    decoded = auth.verify_id_token(id_token)
    return decoded


# ── Helper: Get Session Document ──────────────────────────────────────────────
def get_session(db: Client, session_id: str) -> dict | None:
    """Fetch a session document by ID. Returns None if not found."""
    doc = db.collection(COL_SESSIONS).document(session_id).get()
    return doc.to_dict() if doc.exists else None


# ── Helper: Add Turn to Session ────────────────────────────────────────────────
def add_turn(db: Client, session_id: str, turn_data: dict) -> str:
    """
    Append a turn to sessions/{session_id}/turns subcollection.
    Returns the auto-generated turn document ID.
    """
    _, ref = db.collection(COL_SESSIONS)\
               .document(session_id)\
               .collection(COL_TURNS)\
               .add(turn_data)
    return ref.id
