# =============================================================================
# backend/app/graph/graph.py
#
# PURPOSE: Assembles the complete GD state machine.
#
# SIMPLE ANALOGY:
#   nodes.py = all the LEGO pieces
#   edges.py = the instruction manual saying which piece connects where
#   graph.py = YOU snapping them all together into the finished model
#
# After this file, we have a single object: `gd_graph`
# The WebSocket handler calls: gd_graph.ainvoke(initial_state)
# And the ENTIRE GD session runs automatically!
#
# THE FLOW:
#   START → select_topic → decide_initiator
#      ↓ (if AI opens)         ↓ (if user opens)
#   generate_response      wait_for_user
#      ↓                       ↓
#   assess_intent ←←←← evaluate_turn
#      ↓
#   ├── generate_response (AI wants to speak → loops back)
#   ├── prod_user (everyone quiet → nudge user)
#   ├── hush_ai (user interrupted → silence AIs)
#   └── end_session (turn limit hit → game over)
# =============================================================================

from __future__ import annotations

import logging
from langgraph.graph import StateGraph, START, END

from app.graph.state import GDState
from app.graph.nodes import (
    select_topic,
    decide_initiator,
    assess_intent,
    generate_response,
    hush_ai,
    wait_for_user,
    evaluate_turn,
    prod_user,
    end_session,
)
from app.graph.edges import (
    route_after_initiator,
    route_after_intent,
    route_after_response,
    route_after_user,
    route_after_hush,
    route_after_prod,
)

logger = logging.getLogger(__name__)


def build_gd_graph() -> StateGraph:
    """
    Build and compile the GD orchestration graph.

    Returns a compiled StateGraph that can be run with:
        result = await graph.ainvoke(initial_state)

    Step-by-step what this function does:
        1. Create an empty graph with GDState as the shared state type
        2. Add every node (move) to the graph
        3. Connect nodes with edges (arrows) — some fixed, some conditional
        4. Compile the graph (validates all connections, makes it runnable)
    """

    # Step 1: Create the graph blueprint
    # GDState tells LangGraph: "this is the shape of data flowing through"
    graph = StateGraph(GDState)

    # ─────────────────────────────────────────────────────────────────────
    # Step 2: Register every node
    # Think of this as placing all the LEGO pieces on the table
    # ─────────────────────────────────────────────────────────────────────

    graph.add_node("select_topic", select_topic)
    graph.add_node("decide_initiator", decide_initiator)
    graph.add_node("assess_intent", assess_intent)
    graph.add_node("generate_response", generate_response)
    graph.add_node("hush_ai", hush_ai)
    graph.add_node("wait_for_user", wait_for_user)
    graph.add_node("evaluate_turn", evaluate_turn)
    graph.add_node("prod_user", prod_user)
    graph.add_node("end_session", end_session)

    # ─────────────────────────────────────────────────────────────────────
    # Step 3: Connect nodes with edges
    # Fixed edges   = "ALWAYS go here next" (straight arrows)
    # Conditional   = "check the state, then decide" (branching arrows)
    # ─────────────────────────────────────────────────────────────────────

    # ── Fixed edges (always go this way) ──────────────────────────────

    # The session always starts by picking a topic
    graph.add_edge(START, "select_topic")

    # After topic is picked, decide who goes first
    graph.add_edge("select_topic", "decide_initiator")

    # After user speaks, always evaluate their turn
    graph.add_edge("wait_for_user", "evaluate_turn")

    # End session always leads to the END of the graph
    graph.add_edge("end_session", END)

    # ── Conditional edges (depends on the current state) ──────────────

    # After deciding initiator: user opens → wait | AI opens → generate
    graph.add_conditional_edges(
        "decide_initiator",              # FROM this node...
        route_after_initiator,           # ...run this function to decide...
        {                                # ...and these are the possible destinations:
            "wait_for_user": "wait_for_user",
            "generate_response": "generate_response",
        }
    )

    # After intent assessment: generate | prod | hush | end
    graph.add_conditional_edges(
        "assess_intent",
        route_after_intent,
        {
            "generate_response": "generate_response",
            "prod_user": "prod_user",
            "hush_ai": "hush_ai",
            "end_session": "end_session",
        }
    )

    # After AI speaks: loop back to assess | hush (user interrupted) | end
    graph.add_conditional_edges(
        "generate_response",
        route_after_response,
        {
            "assess_intent": "assess_intent",
            "hush_ai": "hush_ai",
            "end_session": "end_session",
        }
    )

    # After evaluating user's turn: loop back to assess | end
    graph.add_conditional_edges(
        "evaluate_turn",
        route_after_user,
        {
            "assess_intent": "assess_intent",
            "end_session": "end_session",
        }
    )

    # After hushing AIs: always wait for user to finish speaking
    graph.add_conditional_edges(
        "hush_ai",
        route_after_hush,
        {"wait_for_user": "wait_for_user"}
    )

    # After prodding user: always wait for their response
    graph.add_conditional_edges(
        "prod_user",
        route_after_prod,
        {"wait_for_user": "wait_for_user"}
    )

    # ─────────────────────────────────────────────────────────────────────
    # Step 4: Compile!
    # This validates all connections and returns a runnable graph.
    # If any node has no outgoing edge, compilation will ERROR.
    # ─────────────────────────────────────────────────────────────────────

    compiled = graph.compile()
    logger.info("✅ GD Graph compiled successfully!")

    return compiled


# Pre-build the graph so it's ready when the WebSocket needs it
gd_graph = build_gd_graph()
