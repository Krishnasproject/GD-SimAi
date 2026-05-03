# =============================================================================
# backend/app/routers/analytics.py
#
# PURPOSE: REST endpoint to fetch post-GD analytics for a completed session.
#
# HOW IT WORKS:
#   1. Fetch analytics/{sessionId} from Firestore (metrics + Gemini verdict).
#   2. Fetch sessions/{sessionId} for topic, company, duration, timestamps.
#   3. Merge into a single flat response that the frontend can consume directly.
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore

from app.dependencies import get_firestore, get_current_user
from app.services.firebase import COL_ANALYTICS, COL_SESSIONS, COL_TURNS

router = APIRouter()


@router.get("/{session_id}")
async def get_analytics(
    session_id: str,
    db: firestore.Client = Depends(get_firestore),
    current_user: dict = Depends(get_current_user),
):
    """
    Returns the fully enriched post-GD analytics report for a completed session.

    Joins:
      - analytics/{sessionId}  → metrics + Gemini verdict
      - sessions/{sessionId}   → topic, company, duration, timestamps

    Returns 404 if the session hasn't been evaluated yet (still in progress).
    """
    # ── 1. Fetch analytics doc ────────────────────────────────────────────────
    analytics_doc = db.collection(COL_ANALYTICS).document(session_id).get()
    if not analytics_doc.exists:
        raise HTTPException(
            status_code=404,
            detail="Analytics not ready yet. Session may still be in progress.",
        )
    analytics = analytics_doc.to_dict() or {}

    # ── 2. Authorization check ────────────────────────────────────────────────
    if analytics.get("userId") != current_user.get("uid"):
        raise HTTPException(status_code=403, detail="Not authorized for this analytics report")

    # ── 3. Fetch session doc for enrichment ───────────────────────────────────
    session_doc = db.collection(COL_SESSIONS).document(session_id).get()
    session = session_doc.to_dict() if session_doc.exists else {}

    # ── 4. Fetch turn count from subcollection (lightweight: just count docs) ─
    turns_ref = (
        db.collection(COL_SESSIONS)
        .document(session_id)
        .collection(COL_TURNS)
    )
    all_turns = list(turns_ref.stream())
    turn_count = len(all_turns)
    user_turn_count = sum(
        1 for t in all_turns
        if (t.to_dict() or {}).get("speaker_id") == "user"
    )

    # ── 5. Build enriched response ────────────────────────────────────────────
    # Prefer metrics-computed counts; fall back to subcollection counts.

    # duration_seconds: prefer session doc, then analytics doc, then 0
    duration_seconds = int(
        session.get("durationSeconds")
        or analytics.get("durationSeconds")
        or 0
    )

    response = {
        # ── Session identity ──────────────────────────────────────────────────
        "session_id": session_id,
        "topic": session.get("topic") or analytics.get("topic", ""),
        "target_company": (
            session.get("targetCompany")
            or session.get("target_company")
            or analytics.get("target_company", "")
        ),
        "started_at": str(session.get("createdAt") or analytics.get("generatedAt", "")),

        # ── Core summary ──────────────────────────────────────────────────────
        "duration_seconds": duration_seconds,
        "turn_count": analytics.get("turnCount") or analytics.get("turn_count") or turn_count,
        "user_turn_count": analytics.get("userTurnCount") or analytics.get("user_turn_count") or user_turn_count,
        "score": analytics.get("placementScore") or analytics.get("placement_score"),  # 0-100

        # ── Speaking stats ────────────────────────────────────────────────────
        "avg_words_per_turn": analytics.get("avgWordsPerTurn") or analytics.get("avg_words_per_turn", 0),
        "speaking_pace_wpm": analytics.get("speakingPaceWpm") or analytics.get("speaking_pace_wpm", 0),
        "communication_archetype": (
            analytics.get("communicationArchetype")
            or analytics.get("communication_archetype", "")
        ),

        # ── Detailed metric scores ────────────────────────────────────────────
        "placement_score": analytics.get("placementScore") or analytics.get("placement_score", 0),
        "airtime_score": analytics.get("airtimeScore") or analytics.get("airtime_score", 0),
        "interruption_score": analytics.get("interruptionScore") or analytics.get("interruption_score", 0),

        # ── Nested metric objects ─────────────────────────────────────────────
        "airtime": analytics.get("airtime", {}),
        "interruptions": analytics.get("interruptions", {}),
        "logic_score": analytics.get("logicScore") or analytics.get("logic_score", {}),
        "diplomacy_score": analytics.get("diplomacyScore") or analytics.get("diplomacy_score", {}),

        # ── Gemini AI verdict (core + extended) ───────────────────────────────
        "gemini_verdict": analytics.get("geminiVerdict", ""),
        "gemini_strengths": analytics.get("geminiStrengths", []),
        "gemini_weaknesses": analytics.get("geminiWeaknesses", []),
        "gemini_next_steps": analytics.get("geminiNextSteps", []),

        # ── ML-enhanced fields ────────────────────────────────────────────────
        "confidence_level": analytics.get("confidenceLevel", "Medium"),
        "confidence_rationale": analytics.get("confidenceRationale", ""),
        "communication_style": analytics.get("communicationStyle", ""),
        "topic_mastery": analytics.get("topicMastery", ""),
        "key_moments": analytics.get("keyMoments", []),
    }

    return response
