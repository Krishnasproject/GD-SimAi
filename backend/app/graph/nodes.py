# =============================================================================
# backend/app/graph/nodes.py
#
# PURPOSE: Every "move" the GD state machine can make.
#
# THINK OF IT LIKE A BOARD GAME:
#   The GDState is the board. Each function here is one MOVE.
#   A move reads the board → does something → updates the board.
#
#   select_topic()       → "Pick a random topic card"
#   decide_initiator()   → "Roll the dice — who goes first?"
#   assess_intent()      → "Each AI player thinks: should I speak or stay silent?"
#   generate_response()  → "The chosen AI speaks their turn"
#   hush_ai()            → "User raised their hand — everyone stop talking!"
#   wait_for_user()      → "It's the user's turn — wait for them"
#   prod_user()          → "User is quiet — Arjun nudges them"
#   end_session()        → "Game over — calculate results"
#
# EVERY function takes (state: GDState) and returns a dict of updated fields.
# LangGraph automatically merges the returned dict into the state.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from app.agents.aggressor import Aggressor
from app.agents.logical import Logical
from app.agents.diplomat import Diplomat
from app.agents.director import Director
from app.graph.state import GDState
from app.models.transcript import Turn
from app.services.llm import GeminiService
from app.services.chroma import query_topics, init_chroma, get_or_create_collection

logger = logging.getLogger(__name__)

# ── Create shared instances (initialized once, used by all nodes) ────────
# In production, these come from FastAPI dependency injection.
# For the graph runner, we create them here for simplicity.
_llm = GeminiService()
_director = Director()
_agents = {
    "aggressor": Aggressor(llm=_llm),
    "logical": Logical(llm=_llm),
    "diplomat": Diplomat(llm=_llm),
}

VALID_INTENTS = {"INTERRUPT", "OPPOSE", "ACKNOWLEDGE", "YIELD"}


def _normalize_intent(raw: str | None) -> str:
    value = (raw or "").strip().upper()
    return value if value in VALID_INTENTS else "YIELD"


def _extract_json_object(raw_text: str) -> dict:
    """Best-effort parse of JSON from plain text or fenced blocks."""
    text = (raw_text or "").strip()
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}

    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _local_intent_fallback(state: GDState) -> list[dict[str, Any]]:
    """
    Deterministic backup policy so the conversation stays alive without LLM intents.
    """
    transcript = state.get("transcript", [])
    turn_count = state.get("turn_count", 0)
    last_speaker = transcript[-1].speaker_id if transcript else "none"

    # Baseline behavior keeps one challenger and one bridge-builder active.
    intents: dict[str, tuple[str, float]] = {
        "aggressor": ("OPPOSE", 0.78),
        "logical": ("ACKNOWLEDGE", 0.72),
        "diplomat": ("ACKNOWLEDGE", 0.67),
    }

    if last_speaker == "aggressor":
        intents["aggressor"] = ("YIELD", 0.25)
        intents["logical"] = ("OPPOSE", 0.76)
        intents["diplomat"] = ("ACKNOWLEDGE", 0.73)
    elif last_speaker == "logical":
        intents["logical"] = ("YIELD", 0.28)
        intents["aggressor"] = ("OPPOSE", 0.80)
        intents["diplomat"] = ("ACKNOWLEDGE", 0.72)
    elif last_speaker == "diplomat":
        intents["diplomat"] = ("YIELD", 0.26)
        intents["aggressor"] = ("OPPOSE", 0.79)
        intents["logical"] = ("ACKNOWLEDGE", 0.74)
    elif last_speaker == "user":
        intents["aggressor"] = ("OPPOSE", 0.81)
        intents["logical"] = ("ACKNOWLEDGE", 0.75)
        intents["diplomat"] = ("ACKNOWLEDGE", 0.70)

    # Every few turns, let aggressor cut in for a more realistic dynamic.
    if turn_count > 0 and turn_count % 4 == 0:
        intents["aggressor"] = ("INTERRUPT", 0.83)

    return [
        {
            "agent_id": agent_id,
            "intent": intent,
            "confidence": confidence,
        }
        for agent_id, (intent, confidence) in intents.items()
    ]


# =============================================================================
# NODE 1: select_topic
#
# WHAT IT DOES: Picks a random GD topic for this session.
# WHEN IT RUNS: Once, at the very start of every session.
#
# SPLIT INTO TWO PHASES for latency:
#   Phase 1 (instant): Just pick the topic string. No LLM call.
#   Phase 2 (background): Generate topic_context asynchronously.
#
# First tries ChromaDB (for company-specific topics from YouTube data).
# If ChromaDB is empty (Week 1-3), falls back to the hardcoded list.
# =============================================================================

async def select_topic(state: GDState) -> dict[str, Any]:
    """Phase 1: Pick a GD topic instantly — NO LLM call.

    Topic context is generated separately via generate_topic_context()
    as an async background task so session_ready fires immediately.
    """

    company = state.get("target_company", "General")

    # If the topic is already seeded (from Firestore via ws.py), respect it.
    # Only fall through to random selection if no topic was provided.
    existing_topic = (state.get("topic") or "").strip()
    if existing_topic:
        topic = existing_topic
        logger.info(f"📋 Using pre-set topic from session: '{topic}'")
    else:
        # Try ChromaDB first (will have real topics after Week 4 seeding)
        try:
            chroma = init_chroma()
            topics = query_topics(chroma, company=company, n_results=3)
        except Exception:
            topics = []

        topic = _director.select_random_topic(chroma_topics=topics if topics else None)
        logger.info(f"📋 Randomly selected topic: '{topic}' | Company: {company}")

    return {
        "topic": topic,
        "topic_context": "",  # Populated async by generate_topic_context()
    }


async def generate_topic_context(state: dict) -> None:
    """Phase 2: Generate topic context in the background.

    Runs as an asyncio.create_task() after session_ready is sent.
    Injects result directly into the shared state dict.
    """
    topic = state.get("topic", "")
    if not topic:
        return

    try:
        topic_context = await _llm.generate(
            prompt=f"Give 3-4 bullet points of key facts, statistics, and perspectives about this GD topic: '{topic}'. Keep each point to one line.",
            system_instruction="You are a research assistant providing factual context.",
            max_tokens=200,
            timeout=10.0,
        )
        state["topic_context"] = topic_context
        logger.info(f"📚 Topic context generated ({len(topic_context)} chars)")
    except Exception as e:
        logger.error(f"Topic context generation failed: {e}")
        state["topic_context"] = ""  # Personas will work without it


# =============================================================================
# NODE 2: decide_initiator
#
# WHAT IT DOES: Randomly picks who speaks FIRST — the user or one of the AIs.
# WHEN IT RUNS: Once, right after the topic is selected.
#
# In real GDs, there's often an awkward pause, then the boldest person
# starts. We simulate that: 30% chance the user opens, 70% an AI opens.
# =============================================================================

async def decide_initiator(state: GDState) -> dict[str, Any]:
    """Decide who opens the GD — user or a random AI agent."""

    initiator = _director.decide_initiator()

    return {
        "initiator": initiator,
        "current_speaker": initiator,
        "user_last_spoke_at": time.time(),  # Reset silence timer
    }


# =============================================================================
# NODE 3: assess_intent
#
# WHAT IT DOES: Asks ALL 3 AI personas: "What do you want to do next?"
#   Each one reads the last 5 turns and decides:
#     INTERRUPT → "I need to cut in right now!"
#     OPPOSE    → "I disagree and want to counter!"
#     ACKNOWLEDGE → "I agree and want to build on that!"
#     YIELD     → "I have nothing to add, I'll stay quiet."
#
# The key trick: We run all 3 assessments IN PARALLEL using asyncio.gather.
# This means it takes ~200ms total (the slowest single call), not 600ms.
# =============================================================================

def _smart_intent_engine(state: dict) -> list[dict]:
    """
    Determine agent intents using transcript analysis — zero API calls.

    Analyzes:
    - Who just spoke
    - What they said (keywords, tone indicators)
    - Turn patterns (interrupt cycle, silence, etc.)
    - Conversation momentum
    """
    transcript = state.get("transcript", [])
    turn_count = state.get("turn_count", 0)

    if not transcript:
        return [
            {"agent_id": "aggressor", "intent": "OPPOSE", "confidence": 0.82},
            {"agent_id": "logical", "intent": "ACKNOWLEDGE", "confidence": 0.75},
            {"agent_id": "diplomat", "intent": "ACKNOWLEDGE", "confidence": 0.68},
        ]

    last_turn = transcript[-1]
    last_speaker = last_turn.speaker_id
    last_text = last_turn.text.lower()

    # --- Signal detection from last turn's text ---
    has_question = "?" in last_turn.text
    has_data = any(w in last_text for w in [
        "%", "study", "research", "data", "statistic", "report",
        "survey", "according", "shows", "found", "million", "billion"
    ])
    has_agreement = any(w in last_text for w in [
        "agree", "correct", "exactly", "absolutely", "right", "valid", "true"
    ])
    has_strong_claim = any(w in last_text for w in [
        "always", "never", "must", "should", "clearly", "obviously",
        "definitely", "certainly", "best", "worst"
    ])
    has_user_address = any(w in last_text for w in [
        "you", "your", "candidate", "what do you", "what's your"
    ])

    # --- Base intent matrix by last speaker ---
    if last_speaker == "user":
        if has_question:
            # User asked something — aggressor jumps on it
            intents = {
                "aggressor": ("OPPOSE", 0.85),
                "logical": ("ACKNOWLEDGE", 0.78),
                "diplomat": ("ACKNOWLEDGE", 0.72),
            }
        elif has_agreement:
            # User agreed — aggressor disagrees with the agreement
            intents = {
                "aggressor": ("OPPOSE", 0.88),
                "logical": ("OPPOSE", 0.74),
                "diplomat": ("ACKNOWLEDGE", 0.70),
            }
        elif has_data:
            # User cited data — logical wants to fact-check
            intents = {
                "aggressor": ("OPPOSE", 0.80),
                "logical": ("OPPOSE", 0.85),
                "diplomat": ("ACKNOWLEDGE", 0.65),
            }
        else:
            # Default user turn response
            intents = {
                "aggressor": ("OPPOSE", 0.82),
                "logical": ("ACKNOWLEDGE", 0.76),
                "diplomat": ("ACKNOWLEDGE", 0.71),
            }

    elif last_speaker == "aggressor":
        if has_strong_claim:
            # Ravi made a strong claim — Sneha fact-checks
            intents = {
                "aggressor": ("YIELD", 0.20),
                "logical": ("OPPOSE", 0.88),
                "diplomat": ("ACKNOWLEDGE", 0.72),
            }
        else:
            intents = {
                "aggressor": ("YIELD", 0.20),
                "logical": ("OPPOSE", 0.80),
                "diplomat": ("ACKNOWLEDGE", 0.74),
            }

    elif last_speaker == "logical":
        if has_data:
            # Sneha cited data — Ravi challenges it
            intents = {
                "aggressor": ("OPPOSE", 0.86),
                "logical": ("YIELD", 0.22),
                "diplomat": ("ACKNOWLEDGE", 0.70),
            }
        else:
            intents = {
                "aggressor": ("OPPOSE", 0.82),
                "logical": ("YIELD", 0.22),
                "diplomat": ("ACKNOWLEDGE", 0.75),
            }

    elif last_speaker == "diplomat":
        # After Arjun bridges — Ravi re-ignites debate
        intents = {
            "aggressor": ("OPPOSE", 0.84),
            "logical": ("ACKNOWLEDGE", 0.76),
            "diplomat": ("YIELD", 0.20),
        }

    else:
        intents = {
            "aggressor": ("OPPOSE", 0.78),
            "logical": ("ACKNOWLEDGE", 0.72),
            "diplomat": ("ACKNOWLEDGE", 0.67),
        }

    # --- Periodic patterns for realism ---
    # Every 3rd turn: Aggressor interrupts to keep energy high
    if turn_count > 0 and turn_count % 3 == 0 and last_speaker != "aggressor":
        intents["aggressor"] = ("INTERRUPT", 0.87)

    # Every 4th turn: Diplomat MUST speak (bridge/summarize).
    # Override aggressor & logical so Arjun actually wins the turn.
    if turn_count > 0 and turn_count % 4 == 0 and last_speaker != "diplomat":
        intents["diplomat"] = ("ACKNOWLEDGE", 0.92)
        intents["aggressor"] = ("YIELD", 0.20)
        intents["logical"] = ("YIELD", 0.20)

    # If user was directly addressed, diplomat yields to let user respond
    if has_user_address:
        intents["diplomat"] = ("YIELD", 0.30)

    return [
        {"agent_id": agent_id, "intent": intent, "confidence": confidence}
        for agent_id, (intent, confidence) in intents.items()
    ]


async def assess_intent(state: GDState) -> dict[str, Any]:
    """Determine what all 3 agents want to do — zero API calls via rule engine.

    PREDICTIVE PIPELINE: If _precomputed_intents exist for the current turn,
    use them instantly (0ms). Otherwise run the smart rule engine, which is
    also instant (0ms) — no LLM call needed.
    """

    transcript = state.get("transcript", [])
    turn_count = state.get("turn_count", 0)

    # ── Fast path: use precomputed intents if available and fresh ────────
    precomputed = state.get("_precomputed_intents")
    precomputed_for = state.get("_precomputed_intents_for_turn", -1)
    if precomputed is not None and precomputed_for == turn_count:
        state.pop("_precomputed_intents", None)
        state.pop("_precomputed_intents_for_turn", None)
        logger.info(f"⚡ Using precomputed intents for turn {turn_count} (0ms)")
        return {
            "agent_intents": precomputed,
            "_last_assessed_transcript_len": len(transcript),
        }

    # Prevent redundant re-assessment if transcript hasn't changed
    last_len = state.get("_last_assessed_transcript_len", -1)
    if len(transcript) == last_len:
        return {"agent_intents": []}

    # ── Rule engine path: instant, zero API calls ────────────────────────
    intent_list = _smart_intent_engine(state)

    logger.info(f"🧠 Intents (rule-engine): "
                f"{[(i['agent_id'], i['intent'], round(i['confidence'], 2)) for i in intent_list]}")

    return {
        "agent_intents": intent_list,
        "_last_assessed_transcript_len": len(transcript),
    }


async def _precompute_next_intents(state: dict, current_turn: int | None = None) -> None:
    """Pre-warm next turn's intents using rule engine — instant, no API call.

    Stores the result in state as _precomputed_intents with a turn freshness
    key. By the time the current turn finishes and assess_intent fires, intents
    are already cached. On any failure, silently gives up — assess_intent will
    recompute via rule engine anyway, so this is purely opportunistic.
    """
    turn_count = current_turn if current_turn is not None else state.get("turn_count", 0)
    target_turn = turn_count + 1

    try:
        intent_list = _smart_intent_engine(state)
        state["_precomputed_intents"] = intent_list
        state["_precomputed_intents_for_turn"] = target_turn
        logger.info(f"🔮 Precomputed intents for turn {target_turn} (rule-engine, 0ms)")
    except Exception as e:
        logger.debug(f"Precompute failed (non-critical): {e}")


# =============================================================================
# NODE 4: generate_response
#
# WHAT IT DOES: The chosen AI persona speaks their turn.
#   1. Director picks the winner from the 3 intents
#   2. Waits a human-like pause (0.2-1.2s depending on intent)
#   3. Streams the response from Gemini, sentence by sentence
#   4. Each sentence is stored and will be sent via WebSocket
#
# WHEN IT RUNS: After assess_intent, when at least one AI wants to speak.
# =============================================================================

async def generate_response(state: GDState) -> dict[str, Any]:
    """The chosen AI agent generates and streams their spoken turn."""

    intents = state.get("agent_intents", [])
    last_speaker = state.get("current_speaker", None)

    # Director resolves: who speaks next?
    winner = _director.resolve_next_speaker(intents, last_speaker=last_speaker)

    if winner is None:
        # Everyone yielded — this will route to prod_user via edges
        return {"current_speaker": "none"}

    agent_id = winner["agent_id"]
    intent = winner["intent"]
    agent = _agents[agent_id]

    # Human-like pause before speaking (INTERRUPT is quick, ACKNOWLEDGE is slower)
    pause = _director.get_human_pause(intent)
    logger.info(f"⏸️ {agent.display_name} pausing {pause:.1f}s before speaking ({intent})")
    await asyncio.sleep(pause)

    # Stream the response, collecting all sentences
    full_text = ""
    sentences = []

    async for sentence in agent.generate(
        topic=state.get("topic", ""),
        topic_context=state.get("topic_context", ""),
        transcript=state.get("transcript", []),
        intent=intent,
    ):
        full_text += sentence + " "
        sentences.append(sentence)
        logger.info(f"💬 {agent.display_name}: {sentence}")

    # Create the Turn record for this utterance
    new_turn = Turn(
        speaker_id=agent_id,
        text=full_text.strip(),
        start_timestamp_ms=int(time.time() * 1000),
        duration_ms=len(full_text) * 50,  # Rough estimate: 50ms per char
        was_interrupted=False,
        intent=intent,
    )

    return {
        "transcript": [new_turn],           # Appended via operator.add reducer
        "current_speaker": agent_id,
        "last_speaker_intent": intent,
        "turn_count": state.get("turn_count", 0) + 1,
        "current_response_text": full_text.strip(),
    }


# =============================================================================
# NODE 5: hush_ai
#
# WHAT IT DOES: STOPS the current AI mid-sentence because the user started
#               talking (VAD detected speech).
#
# Think of it like someone raising their hand in class — everyone shuts up.
#   1. Cancels the Gemini stream
#   2. Saves whatever the AI said so far as an "interrupted turn"
#   3. Sets is_hushed = True (tells frontend to mute all TTS)
# =============================================================================

async def hush_ai(state: GDState) -> dict[str, Any]:
    """Cancel AI stream and silence all agents — user is speaking."""

    _llm.cancel()  # Stops the Gemini stream at the next chunk

    # Save the partial response as an interrupted turn
    partial_text = state.get("current_response_text", "")
    if partial_text:
        interrupted_turn = Turn(
            speaker_id=state.get("current_speaker", "unknown"),
            text=partial_text + "—",  # Dash indicates cut-off speech
            start_timestamp_ms=int(time.time() * 1000),
            duration_ms=0,
            was_interrupted=True,
            interrupted_by="user",
        )
        logger.info(f"🤫 AI hushed mid-sentence: '{partial_text[:40]}—'")
        return {
            "transcript": [interrupted_turn],
            "is_hushed": True,
            "user_speech_detected": False,
            "should_cancel_stream": False,
        }

    return {
        "is_hushed": True,
        "user_speech_detected": False,
    }


# =============================================================================
# NODE 6: wait_for_user
#
# WHAT IT DOES: Pauses the graph and waits for the user to finish speaking.
#   The actual speech text comes from the WebSocket (frontend sends
#   "user_utterance" event after STT completes).
#
# This is a PLACEHOLDER in the graph — the WebSocket handler will
# inject the user's text into the state externally.
# =============================================================================

async def wait_for_user(state: GDState) -> dict[str, Any]:
    """Mark that we're waiting for user input."""

    logger.info("👂 Waiting for user input...")

    return {
        "is_hushed": False,
        "current_speaker": "user",
    }


# =============================================================================
# NODE 7: evaluate_turn
#
# WHAT IT DOES: After the user speaks, record their turn and update metrics.
#   - Saves user's utterance to transcript
#   - Resets the silence timer
#   - Clears the "hushed" state so AIs can speak again
# =============================================================================

async def evaluate_turn(state: GDState) -> dict[str, Any]:
    """Process the user's turn — record it and prepare for next AI assessment."""

    return {
        "user_last_spoke_at": time.time(),
        "silence_warned": False,        # Reset since user just spoke
        "is_hushed": False,
        "turn_count": state.get("turn_count", 0) + 1,
    }


# =============================================================================
# NODE 8: prod_user
#
# WHAT IT DOES: The user has been quiet too long (>20s).
#   Arjun (the Diplomat) gently invites them to speak.
#   This is NOT aggressive — it's a natural conversation opener.
#
#   Example: "We've had some great points so far. I'm curious what you think?"
# =============================================================================

async def prod_user(state: GDState) -> dict[str, Any]:
    """Diplomat nudges the silent user to participate."""

    transcript = state.get("transcript", [])
    topic = state.get("topic", "")

    prod_prompt = f"""The group discussion topic is: "{topic}"
The user (human participant) has been silent for a while. 
Create a brief, natural invitation for them to speak — like a friendly participant would.
Do NOT say "you haven't spoken" — instead, create an opening.
Example: "We've had some interesting back-and-forth. I'd love to hear a different perspective though—"
Keep it to 1-2 sentences."""

    prod_text = await _llm.generate(
        prompt=prod_prompt,
        system_instruction=_agents["diplomat"].system_prompt,
        max_tokens=80,
    )

    prod_turn = Turn(
        speaker_id="diplomat",
        text=prod_text,
        start_timestamp_ms=int(time.time() * 1000),
        duration_ms=len(prod_text) * 50,
        was_interrupted=False,
        intent="PROD",
    )

    logger.info(f"👋 Arjun prodding user: '{prod_text}'")

    return {
        "transcript": [prod_turn],
        "silence_warned": True,
        "current_speaker": "diplomat",
    }


# =============================================================================
# NODE 9: end_session
#
# WHAT IT DOES: Marks the session as complete. After this:
#   - The WebSocket sends { type: "session_over" }
#   - Frontend redirects to the Analytics page
#   - Week 4's evaluator runs to generate the performance report
# =============================================================================

async def end_session(state: GDState) -> dict[str, Any]:
    """Mark session as complete."""

    turn_count = state.get("turn_count", 0)
    logger.info(f"🏁 Session ended after {turn_count} turns")

    return {
        "session_over": True,
    }
