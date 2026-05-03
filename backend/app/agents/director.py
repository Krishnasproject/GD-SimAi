# =============================================================================
# backend/app/agents/director.py
#
# PURPOSE: The hidden "Moderator" — never speaks, but decides EVERYTHING.
#
# HOW IT WORKS:
#   After every turn, the 3 persona agents each declare their intent:
#     Ravi:  { intent: "OPPOSE", confidence: 0.85 }
#     Sneha: { intent: "ACKNOWLEDGE", confidence: 0.70 }
#     Arjun: { intent: "YIELD", confidence: 0.60 }
#
#   The Director resolves this:
#     1. Applies priority ranking: INTERRUPT > OPPOSE > ACKNOWLEDGE > YIELD
#     2. If two agents tie on intent, the one with higher confidence wins
#     3. Ensures no agent speaks back-to-back (prevents monologues)
#     4. Tracks user silence — if >20s, tells Arjun to prod the user
#     5. Checks turn limit (max 20) — ends session when hit
#
# DESIGN PHILOSOPHY:
#   In real GDs, there's no visible moderator — but there IS an implicit
#   social protocol. The Director encodes that protocol as rules.
# =============================================================================

from __future__ import annotations

import logging
import random
import time

from app.graph.state import AgentIntent
from app.agents.base_agent import INTENT_PRIORITY

logger = logging.getLogger(__name__)

# These topics are the fallback pool when ChromaDB is empty (Week 4 seeds real ones)
TOPIC_POOL = [
    "Should artificial intelligence replace human jobs?",
    "Is work from home the future of corporate India?",
    "Should social media be regulated by the government?",
    "Is higher education necessary for success?",
    "Should India prioritize economic growth over environmental protection?",
    "Are startups better career options than established MNCs?",
    "Is digital currency the future of the Indian economy?",
    "Should coding be mandatory in school education?",
    "Is capitalism the best economic system for India?",
    "Are group discussions an effective way to evaluate candidates?",
    # Technology
    "The impact of the 5G rollout on India's digital economy.",
    "Should ethical hacking be part of the formal computer science curriculum?",
    "The role of data privacy in the age of big data and analytics.",
    "Is low-code/no-code the future of software development?",
    "The impact of quantum computing on traditional encryption methods.",
    "Should there be universal standards for AI ethics?",
    "The growth of Agritech and its potential to transform Indian farming.",
    "Is the semiconductor shortage a threat to India's 'Atmanirbhar Bharat' vision?",
    # Business
    "The rise of D2C (Direct-to-Consumer) brands in India.",
    "Should startups prioritize profitability over rapid scaling?",
    "The impact of UPI on the global perception of India's fintech sector.",
    "Is the 'Hustle Culture' in corporate India doing more harm than good?",
    "The role of emotional intelligence vs. technical skills in leadership.",
    "Should internships be mandatory and paid for all college students?",
    "The future of traditional banking in the age of Neobanks.",
    "Impact of the 'Great Resignation' on the Indian IT industry.",
    # Society
    "The role of social media influencers in shaping consumer behavior.",
    "Is the reservation system still the best way to ensure social justice in India?",
    "The impact of Westernization on Indian traditional values.",
    "Should mental health be treated with the same importance as physical health in workplaces?",
    "The role of women in the Indian armed forces: Opportunities and challenges.",
    "Is the education system in India producing 'employable' graduates?",
    "The impact of fake news on the democratic process.",
    "Should there be a cap on the maximum salary an individual can earn?",
    # Environment
    "Is India's plan to reach Net Zero by 2070 realistic?",
    "The impact of river linking projects on India's ecology.",
    "Should green buildings be mandatory for all new urban constructions?",
    "The role of individual lifestyle changes vs. systemic policy changes in fighting climate change.",
    "Is solar energy the most viable solution for India's rural electrification?",
    "The impact of tourism on the fragile ecosystem of the Himalayas.",
    "Should companies be taxed based on their carbon footprint?",
    "The ethics of space exploration vs. solving problems on Earth.",
    # Current Affairs
    "The impact of India-Middle East-Europe Economic Corridor (IMEC).",
    "Should India adopt a Uniform Civil Code (UCC)?",
    "The role of the BRICS alliance in a multipolar world.",
    "Is the privatization of Air India a successful model for other PSUs?",
    "The impact of the 'China Plus One' strategy on Indian manufacturing.",
    "Should the legal age of marriage be the same for both men and women?",
    "The role of digital public infrastructure (DPI) in global governance.",
    "Is the sports culture in India shifting beyond Cricket?",
]


class Director:
    """
    The invisible orchestrator that controls turn flow in the GD.

    Not an AI agent — it's a rule-based engine. No LLM calls needed.
    This keeps it FAST (~0ms) and deterministic.
    """

    def __init__(self, agent_names: list[str] | None = None):
        """
        Args:
            agent_names: List of agent IDs in the room.
                         Default: ["aggressor", "logical", "diplomat"]
        """
        self.agent_names = agent_names or ["aggressor", "logical", "diplomat"]
        self.last_speaker: str | None = None
        self.consecutive_yields: int = 0    # Track if all agents keep yielding

    # ── Topic Selection ──────────────────────────────────────────────────

    def select_random_topic(self, chroma_topics: list[str] | None = None) -> str:
        """
        Pick a random GD topic.

        Priority:
            1. If ChromaDB returned company-specific topics → pick from those
            2. Otherwise → pick from the hardcoded TOPIC_POOL

        Args:
            chroma_topics: Topics retrieved from ChromaDB (may be empty)

        Returns:
            A topic string like "Should AI replace human jobs?"
        """
        pool = chroma_topics if chroma_topics else TOPIC_POOL
        topic = random.choice(pool)
        logger.info(f"🎲 Topic selected: '{topic}'")
        return topic

    # ── Initiator Decision ───────────────────────────────────────────────

    def decide_initiator(self) -> str:
        """
        Randomly pick who opens the GD — the user or one of the AI agents.

        In real GDs, anyone can start. We weight it:
            - 30% chance: User opens (gives them practice initiating)
            - 70% chance: A random AI opens (more realistic — usually
              the confident person jumps in first)

        Returns:
            "user" | "aggressor" | "logical" | "diplomat"
        """
        if random.random() < 0.3:
            initiator = "user"
        else:
            initiator = random.choice(self.agent_names)

        logger.info(f"🎤 Initiator decided: {initiator}")
        return initiator

    # ── Intent Resolution ────────────────────────────────────────────────

    def resolve_next_speaker(
        self,
        intents: list[AgentIntent],
        last_speaker: str | None = None,
    ) -> AgentIntent | None:
        """
        Given all 3 agents' intents, pick WHO speaks next.

        Resolution algorithm:
            1. Filter out the last speaker (prevent back-to-back monologues)
            2. Filter out YIELDs (they chose to stay silent)
            3. Sort remaining by: intent_priority DESC, then confidence DESC
            4. Return the winner (or None if everyone yielded)

        This is the BRAIN of turn-taking.

        Args:
            intents: List of 3 AgentIntent dicts
            last_speaker: Who just finished speaking (excluded from next)

        Returns:
            The winning AgentIntent, or None if all agents YIELD.
        """
        # Step 1: Remove the last speaker to prevent monologues
        candidates = [i for i in intents if i["agent_id"] != last_speaker]

        # Step 2: Remove YIELDs (they don't want to speak)
        active = [i for i in candidates if i["intent"] != "YIELD"]

        if not active:
            # Everyone yielded! Track this.
            self.consecutive_yields += 1
            logger.info(f"🤫 All agents YIELD (streak: {self.consecutive_yields})")
            return None

        # Reset yield streak since someone wants to speak
        self.consecutive_yields = 0

        # Step 3: Sort by priority (INTERRUPT > OPPOSE > ACKNOWLEDGE),
        #         then by confidence as tiebreaker
        active.sort(
            key=lambda i: (
                INTENT_PRIORITY.get(i["intent"], 0),   # Primary: intent priority
                i["confidence"],                         # Secondary: confidence
            ),
            reverse=True,   # Highest first
        )

        winner = active[0]
        logger.info(
            f"🗣️ Next speaker: {winner['agent_id']} "
            f"(intent={winner['intent']}, confidence={winner['confidence']:.2f})"
        )
        self.last_speaker = winner["agent_id"]
        return winner

    # ── Silence Detection ────────────────────────────────────────────────

    def should_prod_user(
        self,
        user_last_spoke_at: float,
        silence_warned: bool,
        threshold_seconds: float = 20.0,
    ) -> bool:
        """
        Check if the user has been silent too long and needs a nudge.

        In real GDs, if you're quiet the whole time you get a LOW score.
        The Diplomat (Arjun) will naturally invite the user in.

        Args:
            user_last_spoke_at: Epoch timestamp of user's last utterance
            silence_warned: Whether we've already warned once
            threshold_seconds: How long before prodding (default: 20s)

        Returns:
            True if we should prod the user
        """
        if silence_warned:
            return False    # Don't spam — only prod once per silence window

        elapsed = time.time() - user_last_spoke_at
        should_prod = elapsed > threshold_seconds

        if should_prod:
            logger.info(f"⏰ User silent for {elapsed:.0f}s — prodding via Diplomat")

        return should_prod

    # ── Session End Checks ───────────────────────────────────────────────

    def should_end_session(
        self,
        turn_count: int,
        max_turns: int = 20,
    ) -> bool:
        """
        Check if the session should end.

        Ends when:
            - Turn limit reached (prevents infinite discussions)
            - All agents yielded 3 times in a row (discussion exhausted)

        Args:
            turn_count: Current number of turns taken
            max_turns: Maximum allowed turns

        Returns:
            True if session should end
        """
        if turn_count >= max_turns:
            logger.info(f"🏁 Session ending: turn limit ({max_turns}) reached")
            return True

        if self.consecutive_yields >= 3:
            logger.info("🏁 Session ending: all agents yielded 3x in a row")
            return True

        return False

    # ── Inter-Turn Pause ─────────────────────────────────────────────────

    def get_human_pause(self, intent: str) -> float:
        """
        Return a realistic pause duration (seconds) before the next AI speaks.

        In real GDs, people don't respond INSTANTLY. There's always a
        brief gap. This pause makes the simulation feel natural:
            - INTERRUPT: Very short (0.2-0.5s) — they're cutting in urgently
            - OPPOSE: Medium (0.5-1.0s) — thinking of counter-argument
            - ACKNOWLEDGE: Medium (0.6-1.2s) — processing and building
            - YIELD: N/A (they don't speak)

        Returns:
            Float seconds to wait before starting the next AI turn
        """
        pause_ranges = {
            "INTERRUPT": (0.1, 0.25),   # Was (0.2, 0.5)  — urgent cut-in
            "OPPOSE":    (0.25, 0.55),  # Was (0.5, 1.0)  — quick counter
            "ACKNOWLEDGE": (0.3, 0.65), # Was (0.6, 1.2)  — brief processing
            "YIELD": (0.0, 0.0),
        }
        low, high = pause_ranges.get(intent, (0.4, 1.0))
        return random.uniform(low, high)
