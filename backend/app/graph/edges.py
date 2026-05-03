# =============================================================================
# backend/app/graph/edges.py
#
# PURPOSE: The "traffic signals" between nodes.
#
# SIMPLE ANALOGY:
#   Imagine a flowchart with boxes (nodes) connected by arrows (edges).
#   Some arrows go straight: "After select_topic, ALWAYS go to decide_initiator."
#   Some arrows are conditional: "After assess_intent, go to generate_response
#   IF an AI wants to speak, OR go to prod_user IF everyone yielded."
#
#   This file contains the CONDITIONAL arrows — the decisions that
#   make the flowchart dynamic instead of a fixed loop.
#
# EACH FUNCTION:
#   - Takes the current state
#   - Returns a STRING — the name of the next node to run
#   - LangGraph uses this string to route the flow
# =============================================================================

from __future__ import annotations

import time
import logging

from app.graph.state import GDState
from app.agents.director import Director

logger = logging.getLogger(__name__)

_director = Director()


def route_after_initiator(state: GDState) -> str:
    """
    DECISION: After we know who starts, where do we go?

    Flowchart:
        decide_initiator
            ├── initiator is "user"  → go to "wait_for_user" (let them open)
            └── initiator is an AI   → go to "generate_response" (AI opens)
    """
    initiator = state.get("initiator", "user")

    if initiator == "user":
        logger.info("➡️ User opens the GD → waiting for their input")
        return "wait_for_user"
    else:
        logger.info(f"➡️ {initiator} opens the GD → generating opening statement")
        return "generate_response"


def route_after_intent(state: GDState) -> str:
    """
    DECISION: After all 3 AIs declared their intent, what happens next?

    This is the MOST IMPORTANT routing decision. Flowchart:

        assess_intent
            ├── Session turn limit reached?    → "end_session"
            ├── User silent > 20 seconds?      → "prod_user"
            ├── User VAD detected (speaking)?   → "hush_ai"
            ├── At least 1 AI wants to speak?   → "generate_response"
            └── ALL AIs yielded?                → "prod_user"
    """
    # Check 1: Should the session end?
    turn_count = state.get("turn_count", 0)
    max_turns = state.get("max_turns", 20)
    if _director.should_end_session(turn_count, max_turns):
        return "end_session"

    # Check 2: Is the user currently speaking? (VAD fired)
    if state.get("user_speech_detected", False):
        return "hush_ai"

    # Check 3: Has the user been silent too long?
    user_last_spoke = state.get("user_last_spoke_at", time.time())
    silence_warned = state.get("silence_warned", False)
    if _director.should_prod_user(user_last_spoke, silence_warned):
        return "prod_user"

    # Check 4: Did any AI want to speak (non-YIELD)?
    intents = state.get("agent_intents", [])
    active_intents = [i for i in intents if i.get("intent") != "YIELD"]

    if active_intents:
        return "generate_response"
    else:
        # Everyone yielded — prod the user to keep the discussion alive
        return "prod_user"


def route_after_response(state: GDState) -> str:
    """
    DECISION: After an AI finishes speaking, what's next?

    Flowchart:
        generate_response
            ├── User interrupted mid-speech?  → "hush_ai"
            ├── Session limit reached?        → "end_session"
            └── Normal flow?                  → "assess_intent" (loop back)

    This creates the main loop:
        assess_intent → generate_response → assess_intent → generate_response ...
    """
    if state.get("user_speech_detected", False):
        return "hush_ai"

    turn_count = state.get("turn_count", 0)
    max_turns = state.get("max_turns", 20)
    if _director.should_end_session(turn_count, max_turns):
        return "end_session"

    # Normal: go back to intent assessment for the next turn
    return "assess_intent"


def route_after_user(state: GDState) -> str:
    """
    DECISION: After the user finishes speaking, what happens?

    Flowchart:
        evaluate_turn (user's turn recorded)
            ├── Session limit?  → "end_session"
            └── Normal?         → "assess_intent" (AIs decide who responds)
    """
    turn_count = state.get("turn_count", 0)
    max_turns = state.get("max_turns", 20)
    if _director.should_end_session(turn_count, max_turns):
        return "end_session"

    return "assess_intent"


def route_after_hush(state: GDState) -> str:
    """
    DECISION: After AIs are hushed (user interrupted), where next?

    Always → "wait_for_user" (let the user finish their thought)
    """
    return "wait_for_user"


def route_after_prod(state: GDState) -> str:
    """
    DECISION: After Arjun prods the user, where next?

    Always → "wait_for_user" (wait for the user to speak up)
    """
    return "wait_for_user"
