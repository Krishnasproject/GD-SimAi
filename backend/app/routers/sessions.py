# =============================================================================
# backend/app/routers/sessions.py
#
# PURPOSE: REST API routes for creating, fetching, and updating GD sessions.
#
# HOW IT WORKS:
#   Route handlers are thin — they validate input (Pydantic), call service
#   logic, write to Firestore, and return a response. No business logic here.
#
# ENDPOINTS:
#   POST   /api/sessions/create          → Start a new GD session
#   GET    /api/sessions/{session_id}    → Get session details
#   PATCH  /api/sessions/{session_id}    → Mark session completed/abandoned
#   GET    /api/sessions/{session_id}/transcript → Full turn-by-turn transcript
#   GET    /api/sessions/user/{user_id}  → List all sessions for a user
# =============================================================================

import uuid
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from google.cloud import firestore

from app.dependencies import get_firestore, get_current_user
from app.models.session import (
    CreateSessionRequest,
    SessionResponse,
    UpdateSessionRequest,
    SessionSettings,
)
from app.models.transcript import TranscriptResponse, Turn
from app.services.firebase import COL_SESSIONS, COL_TURNS, COL_ANALYTICS
from app.config import settings

router = APIRouter()

# ── Hard-coded topic pool (will be replaced by ChromaDB in Week 4) ─────────────
# Keyed by company so Select_Random_Topic can filter.
TOPIC_POOL: dict[str, list[str]] = {
    "General":   ["Should AI replace human jobs?",
                  "Is remote work the future?",
                  "Social media: boon or bane?"],
    "TCS":       ["Digital transformation in India",
                  "Cloud adoption challenges for SMEs"],
    "Infosys":   ["Ethics in AI development",
                  "Upskilling the Indian workforce"],
    "Deloitte":  ["Sustainability as a business strategy",
                  "ESG reporting: necessity or burden?"],
    "Accenture": ["Generative AI in enterprise consulting",
                  "Future of work post-pandemic"],
}

AGENT_IDS = ["aggressor", "logical", "diplomat"]


def _assert_owner(data: dict, current_user: dict):
    uid = current_user.get("uid")
    if data.get("userId") != uid:
        raise HTTPException(status_code=403, detail="Not authorized for this session")


# ── POST /api/sessions/create ─────────────────────────────────────────────────
@router.post("/create", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    db: firestore.Client = Depends(get_firestore),
    current_user: dict = Depends(get_current_user),
):
    """
    Creates a new GD session.

    Steps:
      1. Pick a random topic for the target company.
      2. Randomly decide who initiates (user or one of 3 AI agents).
      3. Write session document to Firestore.
      4. Return session details so frontend can open the WS connection.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Step 1: Pick topic ── will query ChromaDB in Week 4
    company = body.target_company
    topics = TOPIC_POOL.get(company, TOPIC_POOL["General"])
    topic = random.choice(topics)

    # Step 2: Random initiator (25% chance it's the user)
    initiator = random.choice(["user"] + AGENT_IDS)

    uid = current_user.get("uid")

    session_data = {
        "sessionId":     session_id,
        "userId":        uid,
        "topic":         topic,
        "targetCompany": company,
        "initiator":     initiator,
        "status":        "in_progress",
        "agents":        AGENT_IDS,
        "durationSeconds": None,
        "createdAt":     now,
        "completedAt":   None,
        "settings":      body.settings.model_dump(),
    }

    # Step 3: Write to Firestore
    db.collection(COL_SESSIONS).document(session_id).set(session_data)

    return SessionResponse(
        session_id=session_id,
        user_id=uid,
        topic=topic,
        target_company=company,
        initiator=initiator,
        status="in_progress",
        created_at=now,
        settings=body.settings,
    )


# ── GET /api/sessions/{session_id} ────────────────────────────────────────────
@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: firestore.Client = Depends(get_firestore),
    current_user: dict = Depends(get_current_user),
):
    """Fetch a single session by ID. Used on page refresh / reconnect."""
    doc = db.collection(COL_SESSIONS).document(session_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    data = doc.to_dict()
    _assert_owner(data, current_user)
    return SessionResponse(
        session_id=data["sessionId"],
        user_id=data["userId"],
        topic=data["topic"],
        target_company=data["targetCompany"],
        initiator=data["initiator"],
        status=data["status"],
        duration_seconds=data.get("durationSeconds"),
        created_at=data["createdAt"],
        completed_at=data.get("completedAt"),
        settings=SessionSettings(**data["settings"]),
    )


# ── PATCH /api/sessions/{session_id} ─────────────────────────────────────────
@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    db: firestore.Client = Depends(get_firestore),
    current_user: dict = Depends(get_current_user),
):
    """Mark a session as completed or abandoned. Called when GD ends."""
    doc = db.collection(COL_SESSIONS).document(session_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    _assert_owner(doc.to_dict(), current_user)

    db.collection(COL_SESSIONS).document(session_id).update({
        "status":          body.status,
        "durationSeconds": body.duration_seconds,
        "completedAt":     datetime.now(timezone.utc),
    })
    return {"message": f"Session {session_id} marked as {body.status}"}


# ── GET /api/sessions/{session_id}/transcript ─────────────────────────────────
@router.get("/{session_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    session_id: str,
    db: firestore.Client = Depends(get_firestore),
    current_user: dict = Depends(get_current_user),
):
    """
    Returns all turns for a session in order.
    Used by the analytics engine and post-GD review screen.
    """
    session_doc = db.collection(COL_SESSIONS).document(session_id).get()
    if not session_doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    _assert_owner(session_doc.to_dict(), current_user)

    turns_ref = (
        db.collection(COL_SESSIONS)
          .document(session_id)
          .collection(COL_TURNS)
          .order_by("sequenceIndex")   # chronological order
    )
    docs = turns_ref.stream()
    turns = [Turn(**doc.to_dict()) for doc in docs]

    return TranscriptResponse(
        session_id=session_id,
        turns=turns,
        total_turns=len(turns),
    )


# ── GET /api/sessions/user/{user_id} ─────────────────────────────────────────
@router.get("/user/{user_id}")
async def list_user_sessions(
    user_id: str,
    db: firestore.Client = Depends(get_firestore),
    current_user: dict = Depends(get_current_user),
):
    """List all sessions for a user (newest first). For the user dashboard."""
    if current_user.get("uid") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this user")

    # Avoid composite-index dependency (userId + createdAt) by fetching filtered
    # docs and sorting in memory. This keeps local/dev setup friction low.
    docs = (
        db.collection(COL_SESSIONS)
          .where("userId", "==", user_id)
          .limit(100)
          .stream()
    )

    sessions = [doc.to_dict() for doc in docs]
    sessions.sort(
        key=lambda item: item.get("createdAt") or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    return sessions[:20]
