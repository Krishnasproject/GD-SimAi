# =============================================================================
# backend/app/services/stt/groq_whisper_stt.py
#
# PURPOSE: Production STT via Groq's hosted Whisper-large-v3.
#
# WHY GROQ?
#   Groq runs Whisper on custom LPU hardware — fastest Whisper inference
#   available. Free tier: 6,000 audio minutes/day (plenty for dev + testing).
#   Get your free API key at: https://console.groq.com
#
# UPGRADE PATH:
#   Change STT_PROVIDER="groq" in .env → this class is used automatically.
#   No other code changes needed (Base interface is the same).
# =============================================================================

import httpx
import io
from app.services.stt.base_stt import BaseSTT
from app.config import settings


class GroqWhisperSTT(BaseSTT):
    """
    STT provider using Groq's Whisper-large-v3 API.
    Works on all browsers (audio sent server-side to Groq).
    """

    GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Send audio to Groq Whisper → return transcript.
        Latency: ~200-300ms for typical GD utterance (5-15 seconds).

        Args:
            audio_bytes: WAV/MP3 audio data from browser MediaRecorder.

        Returns:
            Transcribed text string.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GROQ_API_URL,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                files={
                    "file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav"),
                    "model": (None, "whisper-large-v3"),
                    "language": (None, "en"),
                    "response_format": (None, "json"),
                },
                timeout=10.0,   # fail fast if Groq is slow
            )
            response.raise_for_status()
            return response.json()["text"].strip()

    async def stream_transcribe(self, audio_chunk: bytes) -> dict:
        """
        Groq Whisper doesn't support streaming yet.
        We buffer audio chunks and call transcribe() on VAD end-of-speech.
        """
        # Audio should be buffered client-side and sent on vad_end.
        raise NotImplementedError("Buffer audio client-side, call transcribe on vad_end in ws.py.")
