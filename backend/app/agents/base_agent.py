# =============================================================================
# backend/app/agents/base_agent.py
#
# PURPOSE: Abstract base class that ALL AI persona agents inherit from.
#
# WHY AN ABSTRACT CLASS?
#   All 3 personas (Aggressor, Logical, Diplomat) do two things:
#     1. assess_intent()  → Read the last few turns, decide: INTERRUPT/OPPOSE/ACKNOWLEDGE/YIELD
#     2. generate()       → Given the topic + transcript + intent, produce a spoken response
#
#   The DIFFERENCES between personas are:
#     - Their system_prompt (personality, speaking style, filler words)
#     - Their intent_weights (Aggressor favors INTERRUPT, Diplomat favors YIELD)
#     - Their voice_config (pitch, rate, voice name for TTS)
#
#   By putting the shared logic in BaseAgent, each persona file only needs
#   to define its unique personality — no duplicated code.
#
# DESIGN PATTERN: Template Method
#   BaseAgent defines the SKELETON of assess_intent() and generate().
#   Subclasses fill in the specifics via properties (system_prompt, etc.)
# =============================================================================

from __future__ import annotations

import json
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator

from app.models.transcript import Turn
from app.services.llm import GeminiService

logger = logging.getLogger(__name__)


@dataclass
class VoiceConfig:
    """
    TTS voice settings for a persona. Used by Edge TTS (or fallback browser TTS).

    Each persona gets a distinct voice so the user can tell them apart
    even without looking at the screen — just like a real GD.

    Attributes:
        voice_name:  Edge TTS voice ID (e.g., "en-IN-PrabhatNeural")
        rate:        Speaking speed. 1.0 = normal, 1.15 = slightly fast
        pitch:       Voice pitch. "+0Hz" = normal, "+5Hz" = slightly higher
        volume:      Voice volume. "+0%" = normal
    """
    voice_name: str = "en-IN-PrabhatNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


# Intent priority — higher number = more urgency = Director picks this first
INTENT_PRIORITY = {
    "INTERRUPT": 4,      # Highest: agent wants to cut in RIGHT NOW
    "OPPOSE": 3,         # High: agent disagrees, wants to counter
    "ACKNOWLEDGE": 2,    # Medium: agent agrees, wants to build on point
    "YIELD": 1,          # Lowest: agent has nothing to add, passes
}

# ── System-level conciseness constraint injected into EVERY persona ──────────
# This is appended to the persona's system_prompt unconditionally so no
# subclass can accidentally produce a monologue and stall the GD pacing.
CONCISENESS_RULE = (
    "\n\nCRITICAL RULE: Keep your response to 2-3 sentences maximum. "
    "This is a fast-paced Group Discussion, not a debate speech. "
    "Be sharp, direct, and concise. No more than 60 words per turn."
)


class BaseAgent(ABC):
    """
    Abstract base class for all GD persona agents.

    To create a new persona:
        1. Subclass BaseAgent
        2. Define the 4 abstract properties: name, system_prompt, intent_weights, voice
        3. That's it! assess_intent() and generate() work automatically.

    Example:
        class Aggressor(BaseAgent):
            @property
            def name(self) -> str:
                return "aggressor"
            @property
            def system_prompt(self) -> str:
                return "You are Ravi, an aggressive debater..."
            ...
    """

    def __init__(self, llm: GeminiService):
        """
        Args:
            llm: Shared GeminiService instance for all Gemini API calls.
                 Injected via FastAPI deps so we reuse the same client.
        """
        self.llm = llm

    # ── Abstract Properties (each persona MUST define these) ─────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier: 'aggressor' | 'logical' | 'diplomat'"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-friendly name shown in UI: 'Ravi' | 'Sneha' | 'Arjun'"""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """
        The full character sheet for this persona.
        This is sent as the `system_instruction` to Gemini Flash.
        
        Must include:
          - Personality description
          - Speaking style (filler words, sentence length, tone)
          - Intent decision guidelines
          - Example phrases for realism
        """
        ...

    @property
    @abstractmethod
    def intent_weights(self) -> dict[str, float]:
        """
        How strongly this persona favors each intent.
        Used to bias the LLM's intent decision.

        Example for Aggressor:
            { "INTERRUPT": 0.35, "OPPOSE": 0.35, "ACKNOWLEDGE": 0.20, "YIELD": 0.10 }
        
        These weights are injected into the intent assessment prompt so
        Gemini knows: "As the Aggressor, you lean towards interrupting."
        """
        ...

    @property
    @abstractmethod
    def voice(self) -> VoiceConfig:
        """TTS voice settings unique to this persona."""
        ...

    # ── Core Methods (shared logic, no need to override) ─────────────────

    async def assess_intent(self, transcript: list[Turn], topic: str) -> dict:
        """
        Read the recent conversation and decide what to do next.

        This is the "brain" of each agent's decision-making. It sends
        the last 5 turns to Gemini with the persona's intent_weights
        and asks: "What would you do next? INTERRUPT / OPPOSE / ACKNOWLEDGE / YIELD?"

        Args:
            transcript: Full conversation history (we slice last 5 turns)
            topic: The GD topic for context

        Returns:
            { "agent_id": "aggressor", "intent": "OPPOSE", "confidence": 0.85 }
        """
        # Only look at recent turns (full history would eat tokens)
        recent_turns = transcript[-5:] if len(transcript) > 5 else transcript

        # Format transcript as readable dialogue
        conversation = self._format_transcript(recent_turns)

        # Build the intent assessment prompt
        prompt = f"""You are {self.display_name} in a group discussion about: "{topic}"

Your personality weights for deciding what to do:
- INTERRUPT: {self.intent_weights.get('INTERRUPT', 0.1)} (cut in mid-speech because you have an urgent point)
- OPPOSE: {self.intent_weights.get('OPPOSE', 0.25)} (directly challenge the last speaker's argument)
- ACKNOWLEDGE: {self.intent_weights.get('ACKNOWLEDGE', 0.25)} (agree and build on the point)
- YIELD: {self.intent_weights.get('YIELD', 0.4)} (stay silent, let others speak)

Recent conversation:
{conversation}

Based on your personality and the conversation flow, what is your intent?
You MUST respond with ONLY a JSON object, nothing else:
{{"intent": "INTERRUPT|OPPOSE|ACKNOWLEDGE|YIELD", "confidence": 0.0-1.0, "reason": "brief reason"}}"""

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_instruction="You are an intent classifier. Respond ONLY with valid JSON.",
                max_tokens=100,  # Keep it short — just a JSON decision
            )

            # Parse the JSON response
            parsed = json.loads(response.strip())
            return {
                "agent_id": self.name,
                "intent": parsed.get("intent", "YIELD"),
                "confidence": float(parsed.get("confidence", 0.5)),
            }

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Intent assessment failed for {self.name}: {e}. Defaulting to YIELD.")
            return {"agent_id": self.name, "intent": "YIELD", "confidence": 0.1}

    async def generate(
        self,
        topic: str,
        topic_context: str,
        transcript: list[Turn],
        intent: str,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a spoken response, streaming token-by-token.

        This is called when the Director picks this agent to speak.
        The response streams from Gemini Flash → backend buffers at
        sentence boundaries → sends tts_chunk events over WebSocket.

        Args:
            topic: GD topic
            topic_context: RAG context (background facts, stats)
            transcript: Full conversation history
            intent: The intent this agent declared ("OPPOSE", "ACKNOWLEDGE", etc.)

        Yields:
            str: Token chunks from Gemini (buffered into sentences by llm.py)
        """
        conversation = self._format_transcript(transcript[-8:])

        # Resolve the opener instruction — subclasses provide character-specific openers
        opener_instruction = self._get_opener_instruction(intent)

        prompt = f"""Topic: "{topic}"
Background context: {topic_context}

Recent discussion:
{conversation}

Your intent for this turn: {intent}
{opener_instruction}

Now speak your turn in the group discussion. Remember:
- Speak naturally like a real Indian college student in a placement GD
- Use filler words occasionally (Well, Look, I mean, Honestly)
- Keep it 2-4 sentences unless you're making a complex argument
- Reference what others said by name when agreeing or disagreeing
- If OPPOSING, provide a specific counter-example or data point"""

        async for chunk in self.llm.stream_generate(
            prompt=prompt,
            system_instruction=self.system_prompt + CONCISENESS_RULE,
            speaker_name=self.display_name,
            intent=intent,
        ):
            yield chunk

    # ── Helper Methods ───────────────────────────────────────────────────

    def _get_opener_instruction(self, intent: str) -> str:
        """
        Return a prompt instruction that tells the LLM which opener to begin with.
        Subclasses OVERRIDE this to inject character-specific, randomly-chosen openers.

        The returned string is injected directly into the generate() prompt so the
        LLM starts its response naturally from the opener — not as a hardcoded prefix.
        """
        defaults = {
            "OPEN": "You are the FIRST speaker. Confidently introduce your stance on the topic.",
            "INTERRUPT": (
                "You are INTERRUPTING the last speaker. Start with urgency. "
                "Begin your response with one of these openers (pick randomly): "
                "\"Wait — \", \"Hold on — \", \"Sorry to cut in but — \""
            ),
            "OPPOSE": (
                "You DISAGREE with the last speaker. "
                "Begin your response with one of these openers (pick randomly): "
                "\"I see your point, but — \", \"That's not quite right — \", \"Actually — \""
            ),
            "ACKNOWLEDGE": (
                "You AGREE and want to BUILD on the point. "
                "Begin your response with one of these openers (pick randomly): "
                "\"Exactly — \", \"Building on that — \", \"That's a great point — \""
            ),
            "YIELD": "Make a brief supportive comment before passing. 1-2 sentences only.",
        }
        return defaults.get(intent, "Contribute meaningfully to the discussion.")

    def _format_transcript(self, turns: list[Turn]) -> str:
        """
        Convert Turn objects into readable dialogue format for the LLM.

        Output looks like:
            [Ravi (aggressor)]: I completely disagree with that premise...
            [User]: Well, actually the data shows a different picture.
            [Sneha (logical)]: Let me add some context here...
        """
        if not turns:
            return "(No conversation yet — this is the opening statement)"

        lines = []
        for turn in turns:
            speaker = turn.speaker_id
            # Map agent IDs to display names for the LLM
            name_map = {
                "aggressor": "Ravi (aggressor)",
                "logical": "Sneha (logical)",
                "diplomat": "Arjun (diplomat)",
                "user": "User",
            }
            display = name_map.get(speaker, speaker)
            lines.append(f"[{display}]: {turn.text}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} display={self.display_name}>"
