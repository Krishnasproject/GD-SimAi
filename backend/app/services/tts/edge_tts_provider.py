# =============================================================================
# backend/app/services/tts/edge_tts_provider.py
#
# PURPOSE: Human-sounding TTS using Microsoft Edge's Neural Voices.
#
# WHY EDGE TTS?
#   - 100% FREE — no API key, no account, no limits
#   - Neural voices that sound genuinely human (not robotic)
#   - Indian English voices available (en-IN-PrabhatNeural, en-IN-NeerjaNeural)
#   - Ultra-fast: ~150ms to get first audio chunk
#   - Supports rate/pitch/volume control per persona
#
# HOW IT WORKS:
#   1. Backend receives a sentence from Gemini (via sentence-boundary flush)
#   2. Edge TTS converts that sentence to MP3 audio bytes
#   3. Audio bytes are sent via WebSocket to the browser
#   4. Browser plays the audio blob directly (no browser speechSynthesis!)
#
# INSTALL: pip install edge-tts
# =============================================================================

from __future__ import annotations

import io
import logging
from typing import AsyncGenerator

import edge_tts  # type: ignore

from app.agents.base_agent import VoiceConfig  # type: ignore
from app.services.tts.base_tts import BaseTTS  # type: ignore

logger = logging.getLogger(__name__)


class EdgeTTSProvider(BaseTTS):
    """
    TTS provider using Microsoft Edge's neural voices.
    Produces natural-sounding Indian English speech for each persona.
    """

    async def synthesize(
        self,
        text: str,
        voice_config: VoiceConfig,
    ) -> bytes:
        """
        Convert text to speech audio bytes.

        Args:
            text: The sentence to speak (e.g., "Look, I completely disagree.")
            voice_config: Persona-specific voice settings (name, rate, pitch)

        Returns:
            MP3 audio bytes ready to send to the browser.
        """
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_config.voice_name,
            rate=voice_config.rate,
            pitch=voice_config.pitch,
            volume=voice_config.volume,
        )

        # Collect all audio chunks into a single bytes buffer
        audio_buffer = io.BytesIO()

        async for chunk in communicate.stream():
            if isinstance(chunk, dict) and chunk.get("type") == "audio":
                audio_buffer.write(chunk.get("data", b""))

        audio_bytes = audio_buffer.getvalue()
        preview = text[:40]  # type: ignore
        logger.debug(
            f"🔊 TTS: {len(audio_bytes)} bytes | "
            f"voice={voice_config.voice_name} | "
            f"text='{preview}...'"
        )
        return audio_bytes

    async def stream_synthesize(
        self,
        text: str,
        voice_config: VoiceConfig,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream audio chunks as they're generated (for ultra-low latency).

        Instead of waiting for the full MP3, yield each audio chunk
        the moment Edge TTS produces it. The browser can start playing
        the first chunk while the rest is still being generated.

        Yields:
            Raw audio chunk bytes (MP3 fragments).
        """
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_config.voice_name,
            rate=voice_config.rate,
            pitch=voice_config.pitch,
            volume=voice_config.volume,
        )

        async for chunk in communicate.stream():
            if isinstance(chunk, dict) and chunk.get("type") == "audio" and chunk.get("data"):
                yield chunk["data"]

    def get_speak_signal(self, text: str, speaker: str) -> dict:
        """
        Return a WS message for browser TTS fallback.
        Used only if Edge TTS is unavailable — falls back to browser speechSynthesis.
        """
        return {
            "type": "tts_fallback",
            "text": text,
            "speaker": speaker,
        }

    async def list_voices(self, language: str = "en-IN") -> list[dict]:
        """
        List available Edge TTS voices for a language.
        Useful for debugging and picking the perfect voice.

        Returns list like:
            [
                {"name": "en-IN-NeerjaNeural", "gender": "Female"},
                {"name": "en-IN-PrabhatNeural", "gender": "Male"},
                ...
            ]
        """
        voices = await edge_tts.list_voices()
        filtered = [
            {"name": v["ShortName"], "gender": v["Gender"]}
            for v in voices
            if v["Locale"].startswith(language)
        ]
        return filtered
