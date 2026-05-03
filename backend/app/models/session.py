# =============================================================================
# backend/app/models/session.py
#
# PURPOSE: Pydantic data models for GD sessions.
#
# HOW IT WORKS:
#   Pydantic models serve TWO roles:
#     1. REQUEST validation — FastAPI automatically validates incoming JSON.
#        If a required field is missing, it returns a 422 error automatically.
#     2. RESPONSE serialization — FastAPI serializes these to JSON for the
#        frontend. Only the fields defined here are exposed in the API.
#
# FIRESTORE MAPPING:
#   These match the `sessions/{sessionId}` Firestore schema exactly.
#   See implementation_plan.md → Firestore Schema section.
# =============================================================================

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
import uuid


# ── Supported companies for topic filtering ────────────────────────────────────
CompanyMode = Literal["TCS", "Infosys", "Deloitte", "Accenture", "General"]

# ── GD Agent IDs ──────────────────────────────────────────────────────────────
AgentId = Literal["aggressor", "logical", "diplomat", "user"]


class SessionSettings(BaseModel):
    """
    Per-session configuration knobs.
    Frontend can override defaults when creating a session.
    """
    silence_threshold_ms: int = 20_000           # Prod user after 20s silence
    vad_enabled: bool = True                     # Always-listen mode on/off
    tts_provider: Literal["web_speech"] = "web_speech"
    vad_speech_threshold: float = 0.65          # VAD sensitivity (0-1)
    vad_silence_frames: int = 8                 # ~250ms of silence to commit


class CreateSessionRequest(BaseModel):
    """
    Body of POST /api/sessions/create
    Frontend sends this when user clicks "Start GD".
    """
    user_id: str                                # Firebase Auth UID
    target_company: CompanyMode = "General"     # Company-mode filter for topic
    settings: SessionSettings = Field(default_factory=SessionSettings)


class SessionResponse(BaseModel):
    """
    Response returned after creating or fetching a session.
    This is what the frontend stores in Zustand roomStore.
    """
    session_id: str
    user_id: str
    topic: str                                  # Randomly selected by backend
    target_company: CompanyMode
    initiator: AgentId                          # Who speaks first
    status: Literal["in_progress", "completed", "abandoned"]
    agents: List[AgentId] = ["aggressor", "logical", "diplomat"]
    duration_seconds: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    settings: SessionSettings


class UpdateSessionRequest(BaseModel):
    """
    Body of PATCH /api/sessions/{session_id}
    Used to mark a session as completed or abandoned.
    """
    status: Literal["completed", "abandoned"]
    duration_seconds: int
