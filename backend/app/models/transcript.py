# =============================================================================
# backend/app/models/transcript.py
#
# PURPOSE: Pydantic models for GD conversation turns.
#
# HOW IT WORKS:
#   Every spoken utterance (by AI or user) is a "Turn".
#   Turns are stored in Firestore:
#     sessions/{sessionId}/turns/{turnId}
#
#   The analytics engine reads all turns at session end to compute:
#     - Airtime % per speaker
#     - Interruption count + recovery rate
#     - Logic score (Point-Reason-Example structure)
# =============================================================================

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid


# ── Who can speak in a GD room ────────────────────────────────────────────────
SpeakerId = Literal["aggressor", "logical", "diplomat", "user"]

# ── What intent did the speaker have ─────────────────────────────────────────
SpeakerIntent = Literal["OPPOSE", "ACKNOWLEDGE", "INTERRUPT", "YIELD", "OPEN", "PROD"]


class Turn(BaseModel):
    """
    A single spoken utterance in the GD session.
    Created every time someone (AI or user) finishes speaking.
    """
    turn_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    speaker_id: SpeakerId
    text: str                                    # Full transcribed text
    intent: SpeakerIntent = "ACKNOWLEDGE"       # Why this agent spoke
    audio_url: Optional[str] = None             # Future: cloud storage URL

    # ── Timing ────────────────────────────────────────────────────────────────
    start_timestamp_ms: int                     # Unix ms when speaking started
    duration_ms: Optional[int] = None          # How long they spoke

    # ── Interruption tracking ─────────────────────────────────────────────────
    was_interrupted: bool = False               # Was this turn cut short?
    interrupted_by: Optional[SpeakerId] = None # Who interrupted them?

    # ── Ordering ──────────────────────────────────────────────────────────────
    sequence_index: int = 0                     # Position in session (0, 1, 2…)


class TurnCreate(BaseModel):
    """
    Minimal data needed to record a new turn (from WebSocket events).
    Backend fills in the rest (turn_id, sequence_index, etc.)
    """
    speaker_id: SpeakerId
    text: str
    intent: SpeakerIntent = "ACKNOWLEDGE"
    start_timestamp_ms: int
    duration_ms: Optional[int] = None
    was_interrupted: bool = False
    interrupted_by: Optional[SpeakerId] = None


class TranscriptResponse(BaseModel):
    """
    Full transcript for a completed session.
    Returned by GET /api/sessions/{session_id}/transcript
    """
    session_id: str
    turns: list[Turn]
    total_turns: int
