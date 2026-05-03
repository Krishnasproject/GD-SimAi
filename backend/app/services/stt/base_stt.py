# =============================================================================
# backend/app/services/stt/base_stt.py
#
# PURPOSE: Abstract interface for Speech-to-Text providers.
#
# WHY AN ABSTRACT CLASS?
#   We want to swap STT providers without changing any other code.
#   The WebSocket router calls `stt.transcribe()` — it doesn't care whether
#   the implementation uses Web Speech API signals or Groq Whisper.
#   This is the "Strategy" design pattern.
#
#   To add a new STT provider (e.g., AssemblyAI):
#     1. Create assemblyai_stt.py
#     2. Subclass BaseSTT
#     3. Implement transcribe()
#     4. Change STT_PROVIDER in config.py
# =============================================================================

from abc import ABC, abstractmethod


class BaseSTT(ABC):
    """
    Abstract base class for all STT providers.
    Any provider must implement the `transcribe` method.
    """

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Convert audio bytes to text.

        Args:
            audio_bytes: Raw PCM/WAV audio data.

        Returns:
            Transcribed text string.
        """
        ...

    @abstractmethod
    async def stream_transcribe(self, audio_chunk: bytes) -> dict:
        """
        Stream transcription (for live VAD-triggered capture).

        Returns dict with:
            { "is_final": bool, "text": str, "confidence": float }
        """
        ...
