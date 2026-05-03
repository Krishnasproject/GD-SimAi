# =============================================================================
# backend/app/services/stt/web_speech_stt.py
#
# PURPOSE: MVP STT via Browser Web Speech API.
#
# HOW IT WORKS:
#   Web Speech API runs ENTIRELY in the browser (Chrome/Edge).
#   The browser does the STT — no audio bytes sent to our server.
#
#   Flow:
#     1. Frontend useSTT.ts starts browser SpeechRecognition
#     2. On final result, frontend sends WS: { type: "user_utterance", text: "…" }
#     3. Backend receives the text — no audio processing needed here!
#
#   Because the actual transcription happens in the browser, this class
#   just signals the frontend to activate its STT and receive the result.
#   It's a "pass-through" pattern.
#
# PROS:  Zero cost, ~200ms latency, no API key needed
# CONS:  Chrome/Edge only; no custom vocabulary; offline mode won't work
# =============================================================================

from app.services.stt.base_stt import BaseSTT


class WebSpeechSTT(BaseSTT):
    """
    STT provider that delegates to the browser's Web Speech API.
    The server side just coordinates — the browser does the heavy lifting.
    """

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Not used for Web Speech API (browser handles it).
        Raises NotImplementedError to flag incorrect usage.
        """
        raise NotImplementedError(
            "Web Speech API transcribes in the browser. "
            "Listen for 'user_utterance' WebSocket events instead."
        )

    async def stream_transcribe(self, audio_chunk: bytes) -> dict:
        """
        Not used for Web Speech API.
        """
        raise NotImplementedError("Use WebSocket 'user_utterance' events.")

    def get_activation_signal(self) -> dict:
        """
        Returns the WS message backend sends to tell frontend:
        'Start your browser STT now.'

        Frontend useSTT.ts listens for this and calls
        SpeechRecognition.start().
        """
        return {"type": "activate_browser_stt"}

    def get_deactivation_signal(self) -> dict:
        """Returns WS message to stop browser STT."""
        return {"type": "deactivate_browser_stt"}
