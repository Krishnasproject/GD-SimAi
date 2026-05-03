# =============================================================================
# backend/app/graph/state.py
#
# PURPOSE: Defines the GDState — the single shared state object that flows
#          through every node in the LangGraph state machine.
#
# HOW IT WORKS:
#   LangGraph operates on a "state" dict. Every node function receives
#   the current state, reads what it needs, and returns updated fields.
#   Think of this as a shared whiteboard:
#
#     select_topic()   →  writes state["topic"], state["topic_context"]
#     decide_initiator() → writes state["initiator"], state["current_speaker"]
#     assess_intent()  →  reads state["transcript"], writes state["agent_intents"]
#     generate_response() → reads intents, writes new turn to state["transcript"]
#
#   The TypedDict below defines EVERY field the whiteboard can contain.
#   If a node tries to read a field that doesn't exist here, you'll get
#   a KeyError — this is intentional. It forces us to be explicit.
#
# IMPORTANT:
#   LangGraph v0.2+ uses "Annotated" reducers. When two nodes both write
#   to the same field (e.g., "transcript"), the reducer decides HOW to
#   merge. We use `operator.add` for lists — meaning new turns are
#   appended, never overwritten.
# =============================================================================

from __future__ import annotations

import operator
from typing import Annotated, TypedDict
from app.models.transcript import Turn


class AgentIntent(TypedDict):
    """
    Represents a single AI agent's decision about what to do next.

    Example:
        { "agent_id": "aggressor", "intent": "OPPOSE", "confidence": 0.85 }

    The Director reads all 3 AgentIntents and picks the highest-priority
    agent to speak next. Priority order: INTERRUPT > OPPOSE > ACKNOWLEDGE > YIELD
    """
    agent_id: str           # "aggressor" | "logical" | "diplomat"
    intent: str             # "INTERRUPT" | "OPPOSE" | "ACKNOWLEDGE" | "YIELD"
    confidence: float       # 0.0 - 1.0, how strongly the agent wants to speak


class GDState(TypedDict):
    """
    The complete state of a live Group Discussion session.
    Every field is explained below with its purpose.
    """

    # ── Session Identity ─────────────────────────────────────────────────
    session_id: str
    """Unique ID for this GD session (matches Firestore document ID)."""

    user_id: str
    """Firebase Auth UID of the human participant."""

    # ── Topic & Context ──────────────────────────────────────────────────
    topic: str
    """The GD topic. e.g., 'Should AI replace human jobs?'
    Set by select_topic node at session start."""

    topic_context: str
    """RAG-retrieved background info about the topic (stats, perspectives).
    Injected into every persona's system prompt so they have "knowledge"."""

    target_company: str
    """Company the user is preparing for: 'TCS' | 'Infosys' | 'Deloitte' | 'Accenture' | 'General'.
    Used to filter ChromaDB topics and subtly adjust persona behavior."""

    # ── Conversation History ─────────────────────────────────────────────
    transcript: Annotated[list[Turn], operator.add]
    """Full ordered list of every utterance in the GD.
    
    Uses `operator.add` reducer — when a node returns {"transcript": [new_turn]},
    LangGraph APPENDS it to the existing list instead of replacing it.
    This is critical: we never want to lose conversation history."""

    # ── Turn Management ──────────────────────────────────────────────────
    initiator: str
    """Who opened the discussion: 'user' | 'aggressor' | 'logical' | 'diplomat'.
    Decided randomly by decide_initiator node."""

    current_speaker: str
    """Who is currently speaking (or about to speak).
    Updated by the Director after reading agent intents."""

    last_speaker_intent: str
    """What the most recent speaker's intent was: 'INTERRUPT' | 'OPPOSE' | 'ACKNOWLEDGE' | 'YIELD'.
    Helps the next speaker decide how to respond."""

    agent_intents: list[AgentIntent]
    """Array of 3 AgentIntent dicts — one per persona.
    Populated by assess_intent node. The Director reads this to pick next speaker."""

    turn_count: int
    """How many turns have been taken so far. Used to enforce session limits."""

    max_turns: int
    """Maximum turns before the session auto-ends (default: 20).
    Prevents infinite loops and controls session length."""

    # ── Voice Activity Detection (VAD) ───────────────────────────────────
    user_speech_detected: bool
    """True when VAD detects the user is speaking mid-AI-turn.
    Triggers the hush_ai node to cancel the current AI stream."""

    is_hushed: bool
    """True when AIs have been silenced because the user started speaking.
    Cleared when the user finishes their utterance."""

    # ── Silence & Prodding ───────────────────────────────────────────────
    user_last_spoke_at: float
    """Epoch timestamp (seconds) of the user's last utterance.
    If (now - user_last_spoke_at) > 20s → prod_user fires."""

    silence_warned: bool
    """True if we've already sent one "prod" to the user.
    Prevents spamming the user with repeated nudges."""

    # ── Session Lifecycle ────────────────────────────────────────────────
    session_over: bool
    """True when the session should end. Triggers the end_session node.
    Set by: turn limit hit, user clicks 'End', or all agents YIELD repeatedly."""

    # ── Streaming Control ────────────────────────────────────────────────
    current_response_text: str
    """Buffer for the AI's current response as it streams in.
    Flushed to WebSocket at sentence boundaries for TTS."""

    should_cancel_stream: bool
    """Set to True when user interrupts (VAD). The generate_response node
    checks this flag and cancels the Gemini stream mid-generation."""

    _last_assessed_transcript_len: int
    """Internal field storing len(transcript) from the last assess_intent run.
    Used to skip duplicate LLM queries and avoid rate limits."""
