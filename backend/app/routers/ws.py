# =============================================================================
# backend/app/routers/ws.py
#
# PURPOSE: The REAL-TIME nerve centre — connects the browser to the AI brain.
#
# SIMPLE ANALOGY:
#   Imagine a phone call between your browser and the LangGraph state machine.
#   This file IS the phone. It:
#     - Picks up when the browser connects (websocket.accept)
#     - Listens for the browser saying things (user_utterance, user_vad_start)
#     - Tells the browser what the AI said (tts_chunk, ai_turn_start)
#     - Hangs up when the session ends (session_over)
#
# MESSAGE FLOW (what travels through the "phone"):
#
#   Browser → Server:
#     { type: "session_start" }                  ← "Start the GD!"
#     { type: "user_vad_start" }                 ← "I'm speaking!" (from VAD)
#     { type: "user_utterance", text: "..." }    ← "Here's what I said" (from STT)
#     { type: "user_vad_end" }                   ← "I stopped speaking"
#     { type: "end_session" }                    ← "I want to quit"
#
#   Server → Browser:
#     { type: "session_ready", topic, initiator }   ← "GD is ready, here's the topic"
#     { type: "ai_turn_start", speaker: "ravi" }    ← "Ravi is about to speak"
#     { type: "tts_chunk", speaker, text: "..." }   ← "Speak this sentence NOW"
#     { type: "ai_turn_end", speaker: "ravi" }      ← "Ravi finished speaking"
#     { type: "ai_hushed" }                          ← "AIs went silent (you interrupted)"
#     { type: "prod_user", text: "..." }             ← "Arjun is nudging you to speak"
#     { type: "session_over" }                       ← "GD ended, go to analytics"
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.graph.graph import build_gd_graph
from app.graph.state import GDState
from app.graph import nodes as graph_nodes
from app.models.transcript import Turn
from app.services.firebase import init_firebase, COL_ANALYTICS, COL_SESSIONS, COL_TURNS, verify_token
from app.analytics.metrics import compute_metrics
from app.analytics.evaluator import evaluate_transcript

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/{session_id}")
async def gd_room_ws(websocket: WebSocket, session_id: str):
    """
    Main WebSocket handler — runs an entire GD session for one user.

    Lifecycle:
        1. Browser connects → we accept
        2. Browser sends "session_start" → we build the graph + run initial nodes
        3. The graph runs in a loop (assess → generate → assess → ...)
        4. We stream AI responses sentence-by-sentence to the browser
        5. Browser sends user utterances → we inject them into the graph state
        6. Session ends → we send "session_over" → browser redirects to analytics
    """
    await websocket.accept()
    logger.info(f"📡 WS connected: session={session_id}")

    # This dict holds the live state — shared between the graph and WS handler
    live_state: dict = {}
    session_started_at: float | None = None
    session_task: asyncio.Task | None = None
    session_finalized = False

    # Queue for user messages — the graph's wait_for_user node reads from this
    user_input_queue: asyncio.Queue = asyncio.Queue()

    # Rate-limit user_vad_start so ambient noise doesn't spam LLM cancellations
    last_vad_start_at: float = 0.0
    VAD_START_COOLDOWN = 1.5  # seconds

    # Speech consolidation: buffer multiple short STT results into one coherent turn.
    # A 2.5s debounce task fires only after the user stops speaking entirely.
    user_speech_buffer: list[str] = []
    _consolidation_task_holder: list[asyncio.Task | None] = [None]  # mutable ref

    async def _flush_speech_buffer(delay: float = 0.4) -> None:
        """Wait for silence, then merge buffered STT fragments into one user turn."""
        await asyncio.sleep(delay)
        if user_speech_buffer:
            combined = " ".join(user_speech_buffer).strip()
            user_speech_buffer.clear()
            if combined:
                await user_input_queue.put(combined)
                logger.info(f"🗣️ Flushed consolidated speech ({len(combined)} chars): '{combined[:80]}'")

    try:
        while True:
            # ── Listen for browser messages ─────────────────────────────
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            logger.info(f"  ← WS received: {msg_type}")

            # ── HANDLE: session_start ───────────────────────────────────
            # The user clicked "Enter the Arena" — spin up the GD!
            if msg_type == "session_start":
                target_company = message.get("target_company", "General")
                id_token = message.get("id_token")

                if not id_token:
                    await websocket.send_json({"type": "error", "message": "Missing authentication token"})
                    await websocket.close(code=1008)
                    break

                try:
                    decoded = verify_token(id_token)
                except Exception:
                    await websocket.send_json({"type": "error", "message": "Invalid authentication token"})
                    await websocket.close(code=1008)
                    break

                db = init_firebase()
                session_doc = db.collection(COL_SESSIONS).document(session_id).get()
                if not session_doc.exists:
                    await websocket.send_json({"type": "error", "message": "Session not found"})
                    await websocket.close(code=1008)
                    break

                session_data = session_doc.to_dict() or {}
                if session_data.get("userId") != decoded.get("uid"):
                    await websocket.send_json({"type": "error", "message": "Not authorized for this session"})
                    await websocket.close(code=1008)
                    break

                # Rate-limit: max 3 concurrent in_progress sessions per user
                uid = decoded.get("uid")
                active = db.collection(COL_SESSIONS)\
                    .where("userId", "==", uid)\
                    .where("status", "==", "in_progress")\
                    .limit(4).stream()
                if len(list(active)) >= 3:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Too many active sessions. Please end an existing session first.",
                    })
                    await websocket.close(code=4029, reason="Too many active sessions")
                    return

                # Build the initial state (the "blank game board")
                # Seed topic from Firestore so both session creation and runtime agree on the same topic
                firestore_topic = session_data.get("topic", "")
                initial_state: GDState = {
                    "session_id": session_id,
                    "user_id": decoded.get("uid", "anonymous"),
                    "topic": firestore_topic,         # ← honored in nodes.select_topic()
                    "topic_context": "",
                    "target_company": target_company,
                    "transcript": [],
                    "initiator": "",
                    "current_speaker": "",
                    "last_speaker_intent": "",
                    "agent_intents": [],
                    "turn_count": 0,
                    "max_turns": message.get("max_turns", 20),
                    "user_speech_detected": False,
                    "is_hushed": False,
                    "user_last_spoke_at": time.time(),
                    "silence_warned": False,
                    "session_over": False,
                    "current_response_text": "",
                    "should_cancel_stream": False,
                }

                live_state.clear()
                live_state.update(initial_state)
                session_started_at = time.time()

                # Run the GD loop in a background task so we can still
                # listen for user messages (like interruptions) simultaneously
                tts_done_event: asyncio.Event = asyncio.Event()
                session_task = asyncio.create_task(
                    _run_gd_session(websocket, live_state, user_input_queue, tts_done_event)
                )

            # ── HANDLE: user_vad_start ──────────────────────────────────
            # User started speaking — tell the graph to hush AIs
            elif msg_type == "user_vad_start":
                # User resumed speaking — cancel any pending consolidation flush
                old = _consolidation_task_holder[0]
                if old and not old.done():
                    old.cancel()

                now = time.time()
                if now - last_vad_start_at >= VAD_START_COOLDOWN:
                    last_vad_start_at = now
                    graph_nodes._llm.cancel()  # Stop Gemini stream immediately
                    await websocket.send_json({"type": "ai_hushed"})
                    logger.info("🤫 User speaking → AIs hushed")
                else:
                    logger.debug("🔇 user_vad_start debounced (too soon)")

            # ── HANDLE: user_utterance ──────────────────────────────────
            # STT finished — user's complete sentence arrived
            elif msg_type == "user_utterance":
                user_text = message.get("text", "")
                if user_text.strip():
                    normalized = user_text.strip()
                    prev_text = live_state.get("_last_user_text", "")
                    prev_at = float(live_state.get("_last_user_text_at", 0.0))
                    now = time.time()

                    # Ignore duplicate STT emissions from browser stop/start jitter.
                    if normalized == prev_text and (now - prev_at) < 0.8:
                        logger.info("🧹 Ignored duplicate user utterance")
                        continue

                    live_state["_last_user_text"] = normalized
                    live_state["_last_user_text_at"] = now

                    # Push the user's text into the queue —
                    # the background GD loop will pick it up
                    await user_input_queue.put(normalized)
                    logger.info(f"🗣️ User said: '{user_text[:50]}...'")

            # ── HANDLE: user_vad_end ────────────────────────────────────
            elif msg_type == "user_vad_end":
                logger.info("🔇 User stopped speaking")
                
                # If client buffered audio, transcribe it using the configured STT
                audio_b64 = message.get("audio")
                if audio_b64:
                    from app.config import settings
                    if settings.STT_PROVIDER == "groq":
                        import base64
                        from app.services.stt.groq_whisper_stt import GroqWhisperSTT
                        
                        try:
                            audio_bytes = base64.b64decode(audio_b64)
                            stt = GroqWhisperSTT()
                            user_text = await stt.transcribe(audio_bytes)
                            if user_text.strip():
                                # Buffer the fragment — don't push to queue yet
                                user_speech_buffer.append(user_text.strip())
                                logger.info(f"📝 STT buffered: '{user_text.strip()[:60]}...'")

                                # Ack immediately so frontend unlocks for next chunk
                                await websocket.send_json({"type": "stt_ack"})

                                # Smart debounce: fast reply if sentence finished, slower if mid-thought
                                # VAD silenceHoldMs already handles noise — keep these tight.
                                combined_so_far = " ".join(user_speech_buffer).strip()
                                delay = 0.2 if combined_so_far.endswith(('.', '?', '!')) else 0.5

                                old = _consolidation_task_holder[0]
                                if old and not old.done():
                                    old.cancel()
                                    try:
                                        await old
                                    except asyncio.CancelledError:
                                        pass
                                _consolidation_task_holder[0] = asyncio.create_task(
                                    _flush_speech_buffer(delay)
                                )
                        except Exception as e:
                            logger.error(f"Groq STT Error: {e}")

            # ── HANDLE: end_session ─────────────────────────────────────
            elif msg_type == "end_session":
                # Flush any pending speech before shutting down
                old = _consolidation_task_holder[0]
                if old and not old.done():
                    old.cancel()
                    try:
                        await old
                    except asyncio.CancelledError:
                        pass
                if user_speech_buffer:
                    combined = " ".join(user_speech_buffer).strip()
                    user_speech_buffer.clear()
                    if combined:
                        await user_input_queue.put(combined)

                if session_task and not session_task.done():
                    session_task.cancel()
                    try:
                        await session_task
                    except asyncio.CancelledError:
                        pass

                if live_state and not session_finalized:
                    await _finalize_session(live_state, session_started_at or time.time())
                    session_finalized = True

                await websocket.send_json({"type": "session_over"})
                logger.info("🏁 User ended session manually")
                break

            # ── HANDLE: tts_done ────────────────────────────────────────
            # Frontend finished playing audio — signal the session loop
            elif msg_type == "tts_done":
                tts_done_event.set()
                logger.info("🔊 Frontend TTS done — user window opening")

            # ── HANDLE: ping ────────────────────────────────────────────
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        old = _consolidation_task_holder[0]
        if old and not old.done():
            old.cancel()
        if live_state and not session_finalized:
            await _finalize_session(live_state, session_started_at or time.time())
            session_finalized = True
        logger.info(f"📡 WS disconnected: session={session_id}")
    except Exception as e:
        logger.error(f"WS error: {e}")
        old = _consolidation_task_holder[0]
        if old and not old.done():
            old.cancel()
        if live_state and not session_finalized:
            await _finalize_session(live_state, session_started_at or time.time())
            session_finalized = True
        await websocket.close(code=1011)


# =============================================================================
# BACKGROUND GD SESSION RUNNER
#
# This function runs the entire GD as a loop:
#   1. Select topic + decide initiator (one-time setup)
#   2. If AI opens → generate opening → send to browser
#   3. Loop: assess intents → pick speaker → generate → send → repeat
#   4. When waiting for user → pause and read from the input queue
#   5. When session ends → send "session_over"
#
# It runs in a background asyncio task so the main WS loop can still
# receive user messages (interruptions, utterances) simultaneously.
# =============================================================================

async def _run_gd_session(
    ws: WebSocket,
    state: GDState,
    user_queue: asyncio.Queue,
    tts_done_event: asyncio.Event,
):
    """Run the full GD session loop, sending events to the browser."""

    start_epoch = time.time()

    try:
        # ── PHASE 1: Setup (topic + initiator) ──────────────────────────

        # Phase 1a: Select topic INSTANTLY (no LLM call)
        updates = await graph_nodes.select_topic(state)
        state.update(updates)

        # Decide who opens
        updates = await graph_nodes.decide_initiator(state)
        state.update(updates)

        # Tell the browser: "GD is ready!" — IMMEDIATELY, before topic_context
        await ws.send_json({
            "type": "session_ready",
            "topic": state["topic"],
            "initiator": state["initiator"],
            "topic_context": "",  # Will be populated async
        })

        logger.info(f"🚀 GD started: topic='{state['topic']}', initiator={state['initiator']}")

        # Phase 1b: Start topic_context generation in background
        topic_ctx_task = asyncio.create_task(
            graph_nodes.generate_topic_context(state)
        )

        # ── PHASE 2: Opening turn ───────────────────────────────────────

        if state["initiator"] != "user":
            # Give topic_context up to 3s to complete before opening turn
            try:
                await asyncio.wait_for(asyncio.shield(topic_ctx_task), timeout=3.0)
            except asyncio.TimeoutError:
                logger.info("⏱️ Topic context still generating — opening turn proceeds without it")

            # An AI opens — generate their opening statement
            await _run_ai_turn(ws, state, tts_done_event, user_queue, is_opening=True)

            # Non-blocking: capture any speech the user made during the opening turn
            try:
                user_text = user_queue.get_nowait()
                user_turn = Turn(
                    speaker_id="user",
                    text=user_text,
                    start_timestamp_ms=int(time.time() * 1000),
                    duration_ms=len(user_text) * 60,
                    was_interrupted=False,
                )
                state["transcript"] = state.get("transcript", []) + [user_turn]
                state["user_last_spoke_at"] = time.time()
                await ws.send_json({"type": "user_turn_recorded", "text": user_text})
                updates = await graph_nodes.evaluate_turn(state)
                state.update(updates)
                logger.info(f"🗣️ User spoke during opening AI turn: '{user_text[:60]}'")
            except asyncio.QueueEmpty:
                pass  # User didn't speak — continue normally
        else:
            # User opens — wait for topic context first (they need the reading time)
            try:
                await asyncio.wait_for(asyncio.shield(topic_ctx_task), timeout=5.0)
            except asyncio.TimeoutError:
                logger.info("⏱️ Topic context timed out — user opens without it")

            # Tell them to speak
            await ws.send_json({
                "type": "your_turn",
                "message": f"The topic is: {state['topic']}. You've been chosen to start! Go ahead.",
            })
            # Wait for user input
            await _wait_and_process_user(ws, state, user_queue)

        # ── PHASE 3: Main GD loop ──────────────────────────────────────

        while not state.get("session_over", False):

            # Step A: All 3 AIs assess their intent
            updates = await graph_nodes.assess_intent(state)
            state.update(updates)

            # Step B: Check if user has been silent too long
            from app.agents.director import Director
            director = Director()
            if director.should_prod_user(
                state.get("user_last_spoke_at", time.time()),
                state.get("silence_warned", False),
            ):
                # Arjun prods the user
                updates = await graph_nodes.prod_user(state)
                state.update(updates)

                last_turn = state["transcript"][-1] if state["transcript"] else None
                if last_turn:
                    await ws.send_json({
                        "type": "prod_user",
                        "speaker": "diplomat",
                        "speaker_name": "Arjun",
                        "text": last_turn.text,
                    })

                await _wait_and_process_user(ws, state, user_queue)
                continue

            # Step C: Check if session should end
            if director.should_end_session(
                state.get("turn_count", 0),
                state.get("max_turns", 20),
            ):
                updates = await graph_nodes.end_session(state)
                state.update(updates)
                break

            # Step D: AI speaks (includes waiting for TTS + user window)
            turn_before = state.get("turn_count", 0)
            await _run_ai_turn(ws, state, tts_done_event, user_queue)
            turn_after = state.get("turn_count", 0)

            # Non-blocking: capture any speech made during or after the AI turn
            try:
                user_text = user_queue.get_nowait()
                user_turn = Turn(
                    speaker_id="user",
                    text=user_text,
                    start_timestamp_ms=int(time.time() * 1000),
                    duration_ms=len(user_text) * 60,
                    was_interrupted=False,
                )
                state["transcript"] = state.get("transcript", []) + [user_turn]
                state["user_last_spoke_at"] = time.time()
                await ws.send_json({"type": "user_turn_recorded", "text": user_text})
                updates = await graph_nodes.evaluate_turn(state)
                state.update(updates)
                logger.info(f"🗣️ User spoke during/after AI turn: '{user_text[:60]}'")
            except asyncio.QueueEmpty:
                pass  # User didn't speak — continue normally

            # If no turn happened (Director found no speaker), force one
            if turn_after == turn_before:
                last_speaker = state.get("current_speaker", "")
                forced = next(
                    (a for a in ["aggressor", "logical", "diplomat"] if a != last_speaker),
                    "aggressor",
                )
                state["agent_intents"] = [
                    {"agent_id": forced, "intent": "ACKNOWLEDGE", "confidence": 0.85},
                    {"agent_id": "aggressor", "intent": "YIELD", "confidence": 0.2},
                    {"agent_id": "diplomat", "intent": "YIELD", "confidence": 0.2},
                ]
                await _run_ai_turn(ws, state, tts_done_event, user_queue)

                # Non-blocking drain after forced turn too
                try:
                    user_text = user_queue.get_nowait()
                    user_turn = Turn(
                        speaker_id="user",
                        text=user_text,
                        start_timestamp_ms=int(time.time() * 1000),
                        duration_ms=len(user_text) * 60,
                        was_interrupted=False,
                    )
                    state["transcript"] = state.get("transcript", []) + [user_turn]
                    state["user_last_spoke_at"] = time.time()
                    await ws.send_json({"type": "user_turn_recorded", "text": user_text})
                    updates = await graph_nodes.evaluate_turn(state)
                    state.update(updates)
                    logger.info(f"🗣️ User spoke during forced AI turn: '{user_text[:60]}'")
                except asyncio.QueueEmpty:
                    pass  # User didn't speak — continue normally

        # ── PHASE 4: Session over ───────────────────────────────────────
        await _finalize_session(state, start_epoch)

        await ws.send_json({
            "type": "session_over",
            "turn_count": state.get("turn_count", 0),
            "topic": state.get("topic", ""),
        })
        logger.info("🏁 GD session complete!")

    except Exception as e:
        logger.error(f"GD session error: {e}")
        # Socket may already be closed if client disconnected mid-turn.
        return


async def _finalize_session(state: dict, start_epoch: float):
    """Persist transcript + analytics and mark session completed in Firestore."""
    if state.get("_finalized"):
        return

    session_id = state.get("session_id")
    if not session_id:
        return

    db = init_firebase()
    session_ref = db.collection(COL_SESSIONS).document(session_id)

    transcript_raw = state.get("transcript", [])
    turns: list[Turn] = [
        turn if isinstance(turn, Turn) else Turn(**turn)
        for turn in transcript_raw
    ]

    # Persist turns under sessions/{session_id}/turns/{turn_id}
    batch = db.batch()
    for idx, turn in enumerate(turns):
        turn_ref = session_ref.collection(COL_TURNS).document(turn.turn_id)
        payload = {
            "turn_id": turn.turn_id,
            "speaker_id": turn.speaker_id,
            "text": turn.text,
            "intent": turn.intent,
            "audio_url": turn.audio_url,
            "start_timestamp_ms": turn.start_timestamp_ms,
            "duration_ms": turn.duration_ms,
            "was_interrupted": turn.was_interrupted,
            "interrupted_by": turn.interrupted_by,
            "sequence_index": idx,
            # Keep camelCase for compatibility with existing Firestore query ordering.
            "sequenceIndex": idx,
        }
        batch.set(turn_ref, payload, merge=True)

    metrics = compute_metrics(turns)
    verdict = await evaluate_transcript(
        llm=graph_nodes._llm,
        topic=state.get("topic", ""),
        transcript=turns,
        metrics=metrics,
    )

    elapsed_seconds = max(1, int(time.time() - start_epoch))
    analytics_doc = {
        "sessionId": session_id,
        "userId": state.get("user_id", "anonymous"),
        "generatedAt": datetime.now(timezone.utc),
        **metrics,
        **verdict,
    }

    analytics_ref = db.collection(COL_ANALYTICS).document(session_id)
    batch.set(analytics_ref, analytics_doc, merge=True)
    batch.update(
        session_ref,
        {
            "status": "completed",
            "durationSeconds": elapsed_seconds,
            "completedAt": datetime.now(timezone.utc),
        },
    )
    batch.commit()
    state["_finalized"] = True


async def _run_ai_turn(
    ws: WebSocket,
    state: dict,
    tts_done_event: asyncio.Event,
    user_queue: asyncio.Queue,
    is_opening: bool = False,
):
    """
    Run a single AI turn: pick speaker → pause → stream sentences → update state.

    For the opening turn, we skip intent assessment and let the initiator speak.
    """
    tts_done_event.clear()  # Clear any stale signal from a previous turn
    graph_nodes._llm._cancel_flag = False  # Ensure fresh stream is not pre-cancelled

    intents = state.get("agent_intents", [])
    last_speaker = state.get("current_speaker", None)

    from app.agents.director import Director
    director = Director()

    if is_opening:
        # Opening: the initiator speaks directly (no intent needed)
        agent_id = state["initiator"]
        intent = "OPEN"  # Opening statements initiate the discussion
    else:
        # Normal: Director picks from intents
        winner = director.resolve_next_speaker(intents, last_speaker)
        if winner is None:
            return  # Everyone yielded — handled by the caller
        agent_id = winner["agent_id"]
        intent = winner["intent"]

    agent = graph_nodes._agents[agent_id]

    # cancel_flag already reset above; kept comment for context.
    # graph_nodes._llm._cancel_flag = False  ← moved to top of function

    # Tell browser: "This agent is about to speak"
    await ws.send_json({
        "type": "ai_turn_start",
        "speaker": agent_id,
        "speaker_name": agent.display_name,
        "intent": intent,
    })

    # Human-like pause before speaking
    pause = director.get_human_pause(intent)
    await asyncio.sleep(pause)

    # Stream the response sentence-by-sentence
    full_text = ""
    async for sentence in agent.generate(
        topic=state.get("topic", ""),
        topic_context=state.get("topic_context", ""),
        transcript=state.get("transcript", []),
        intent=intent,
    ):
        # Check if user interrupted (cancel flag set by WS handler)
        if graph_nodes._llm.is_cancelled:
            # Hushed! Save partial text
            if full_text:
                interrupted_turn = Turn(
                    speaker_id=agent_id,
                    text=full_text.strip() + "—",
                    start_timestamp_ms=int(time.time() * 1000),
                    duration_ms=0,
                    was_interrupted=True,
                    interrupted_by="user",
                    intent=intent,
                )
                state["transcript"] = state.get("transcript", []) + [interrupted_turn]
            await ws.send_json({"type": "ai_hushed"})
            return

        full_text += sentence + " "

        # Send this complete sentence for TTS immediately
        await ws.send_json({
            "type": "tts_chunk",
            "speaker": agent_id,
            "speaker_name": agent.display_name,
            "text": sentence,
        })

    # Turn finished — save to transcript
    if full_text.strip():
        completed_turn = Turn(
            speaker_id=agent_id,
            text=full_text.strip(),
            start_timestamp_ms=int(time.time() * 1000),
            duration_ms=len(full_text) * 50,
            was_interrupted=False,
            intent=intent,
        )
        state["transcript"] = state.get("transcript", []) + [completed_turn]
        state["current_speaker"] = agent_id
        state["last_speaker_intent"] = intent
        state["turn_count"] = state.get("turn_count", 0) + 1

    # Notify browser that text streaming is done; now wait for its TTS to finish.
    await ws.send_json({
        "type": "ai_turn_end",
        "speaker": agent_id,
        "speaker_name": agent.display_name,
    })
    await ws.send_json({"type": "ready_for_user_input"})

    # Wait for frontend to confirm audio finished (max 8 seconds).
    # This prevents the next AI turn from firing while speech is still playing.
    tts_done_event.clear()
    try:
        await asyncio.wait_for(tts_done_event.wait(), timeout=8.0)
        logger.info("✅ TTS done confirmed by frontend")
    except asyncio.TimeoutError:
        logger.info("⏱️ TTS done timeout — proceeding anyway")

    # Give user a 5-second window to jump in after every AI turn.
    await ws.send_json({"type": "your_turn"})
    try:
        user_text = await asyncio.wait_for(user_queue.get(), timeout=5.0)
        user_turn = Turn(
            speaker_id="user",
            text=user_text,
            start_timestamp_ms=int(time.time() * 1000),
            duration_ms=len(user_text) * 60,
            was_interrupted=False,
        )
        state["transcript"] = state.get("transcript", []) + [user_turn]
        state["user_last_spoke_at"] = time.time()
        await ws.send_json({"type": "user_turn_recorded", "text": user_text})
        updates = await graph_nodes.evaluate_turn(state)
        state.update(updates)
        asyncio.create_task(
            graph_nodes._precompute_next_intents(
                state, current_turn=state.get("turn_count", 0)
            )
        )
        logger.info(f"🗣️ User spoke after AI turn: '{user_text[:60]}'")
    except asyncio.TimeoutError:
        pass  # User didn't speak — AI continues

    # ── PREDICTIVE PIPELINE: precompute next turn's intents ──────────
    # Fire-and-forget background task while user reads/thinks/speaks.
    # By the time assess_intent runs next, intents are already cached.
    asyncio.create_task(
        graph_nodes._precompute_next_intents(state, current_turn=state.get("turn_count", 0))
    )


async def _wait_and_process_user(
    ws: WebSocket,
    state: dict,
    user_queue: asyncio.Queue,
    timeout: float = 30.0,
):
    """
    Wait for the user to speak. If they don't speak within timeout, return.
    The main loop will detect the silence and prod them.
    """
    await ws.send_json({"type": "your_turn"})

    try:
        user_text = await asyncio.wait_for(user_queue.get(), timeout=timeout)

        user_turn = Turn(
            speaker_id="user",
            text=user_text,
            start_timestamp_ms=int(time.time() * 1000),
            duration_ms=len(user_text) * 60,
            was_interrupted=False,
        )
        state["transcript"] = state.get("transcript", []) + [user_turn]
        state["user_last_spoke_at"] = time.time()  # Stop the Director from prodding

        await ws.send_json({
            "type": "user_turn_recorded",
            "text": user_text,
        })

        updates = await graph_nodes.evaluate_turn(state)
        state.update(updates)

        asyncio.create_task(
            graph_nodes._precompute_next_intents(state, current_turn=state.get("turn_count", 0))
        )

    except asyncio.TimeoutError:
        logger.info("⏰ User didn't speak in time")
